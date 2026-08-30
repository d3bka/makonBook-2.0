from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import os
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.base.models import UserProfile
from apps.integrations.models import HollihopAttendance, HollihopSyncConflict, HollihopSyncLog, HollihopSyncState
from apps.sat.models import Classroom, ClassroomMembership

from .client import HollihopClient, HollihopError
from .credentials import can_deliver_temporary_access, deliver_new_temporary_access
from .normalization import normalize_email, normalize_phone, safe_text

User = get_user_model()


class HollihopSyncAlreadyRunning(RuntimeError):
    pass


@dataclass
class SyncSummary:
    students_found: int = 0
    students_matched: int = 0
    students_created: int = 0
    students_updated: int = 0
    students_inactive_skipped: int = 0
    teachers_found: int = 0
    teachers_matched: int = 0
    teachers_created: int = 0
    teachers_updated: int = 0
    managers_found: int = 0
    managers_matched: int = 0
    managers_created: int = 0
    managers_updated: int = 0
    classrooms_found: int = 0
    classrooms_created: int = 0
    classrooms_updated: int = 0
    memberships_added: int = 0
    memberships_updated: int = 0
    memberships_removed: int = 0
    attendance_created: int = 0
    attendance_updated: int = 0
    conflicts: int = 0
    errors: int = 0
    conflict_details: list[dict] = field(default_factory=list)

    def as_dict(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__ if name != "conflict_details"}


class HollihopSyncEngine:
    def __init__(self, *, client=None, dry_run=False, send_credentials=False):
        self.client = client or HollihopClient()
        self.dry_run = bool(dry_run)
        self.send_credentials = bool(send_credentials) and not self.dry_run
        self.summary = SyncSummary()
        self._lock_token = None
        # Dry-run must model objects that *would* be created by earlier stages.
        # Without this virtual state, a new teacher is intentionally not written
        # to the DB, then the Classroom stage falsely reports that the EdUnit has
        # no synced teacher. The same issue cascades into membership/attendance
        # counts. These containers never touch persistent storage.
        self._dry_run_teacher_ids: set[int] = set()
        self._dry_run_student_ids: set[int] = set()
        self._dry_run_classroom_ids: set[int] = set()
        # Cache teacher payloads fetched by the bulk GetTeachers call. This is
        # especially important in dry-run: because teachers are not persisted,
        # later classroom processing must not re-fetch/re-count the same teacher
        # once per EdUnit.
        self._teacher_payload_cache_by_id: dict[int, dict] = {}
        # Initial/full reconciliation caches. GetEdUnitStudents is the expensive
        # Hollihop endpoint, so one relation-only payload is reused by students,
        # classrooms and memberships instead of downloading it repeatedly.
        self._selected_edunits_cache: list[dict] | None = None
        self._selected_relations_cache: list[dict] | None = None
        self._active_edunits_cache: list[dict] | None = None
        self._all_students_cache: list[dict] | None = None
        self._allowed_edunit_ids_cache: set[int] | None = None

    @property
    def mode(self):
        return settings.HOLLIHOP_MODE

    @property
    def corporative_filter(self):
        if self.mode == "users":
            return False
        if self.mode == "corporative":
            return True
        return None

    @property
    def allowed_learning_types(self) -> tuple[str, ...]:
        values = getattr(settings, "HOLLIHOP_ALLOWED_LEARNING_TYPES", ()) or ()
        if isinstance(values, str):
            values = [item.strip() for item in values.split(",")]
        return tuple(str(item).strip() for item in values if str(item).strip())

    @property
    def _allowed_learning_type_keys(self) -> set[str]:
        return {item.casefold() for item in self.allowed_learning_types}

    def _learning_type_allowed(self, value) -> bool:
        allowed = self._allowed_learning_type_keys
        if not allowed:
            return True
        return safe_text(value, 150).casefold() in allowed

    def _filter_edunits_by_learning_type(self, rows):
        if not self._allowed_learning_type_keys:
            return list(rows)
        # Fail closed: an EdUnit with a missing/unknown LearningType must not be
        # imported when an allow-list is configured.
        return [row for row in rows if self._learning_type_allowed(row.get("LearningType"))]

    def _filter_relations_by_learning_type(self, rows):
        rows = list(rows)
        if not self._allowed_learning_type_keys:
            return rows
        selected_edunit_ids = None
        result = []
        for row in rows:
            learning_type = safe_text(row.get("EdUnitLearningType"), 150)
            if learning_type:
                if self._learning_type_allowed(learning_type):
                    result.append(row)
                continue
            # Current Hollihop API returns EdUnitLearningType, but if an older
            # tenant omits it we still fail safely by checking the EdUnit itself.
            if selected_edunit_ids is None:
                # Avoid calling _selected_edunits() here: selected EdUnits are
                # derived from memberships and would recurse on older tenants
                # that omit EdUnitLearningType. A plain GROUP catalog is enough
                # for the compatibility fallback.
                selected_edunit_ids = self._allowed_edunit_ids()
            try:
                edunit_id = int(row.get("EdUnitId"))
            except (TypeError, ValueError):
                continue
            if edunit_id in selected_edunit_ids:
                result.append(row)
        return result

    def _log(self, event_type, *, entity_type="", external_id="", user=None, classroom=None, details=None):
        if self.dry_run:
            return
        HollihopSyncLog.objects.create(
            event_type=event_type,
            entity_type=entity_type,
            external_id=str(external_id or ""),
            user=user,
            classroom=classroom,
            details=details or {},
        )

    def _conflict(self, *, external_type, external_id, display_name="", email="", phone="", reason, candidate_ids=None):
        self.summary.conflicts += 1
        item = {
            "external_type": external_type,
            "external_id": str(external_id),
            "display_name": safe_text(display_name, 255),
            "email": normalize_email(email),
            "phone": normalize_phone(phone),
            "reason": safe_text(reason, 500),
            "candidate_user_ids": sorted({int(x) for x in (candidate_ids or [])}),
        }
        self.summary.conflict_details.append(item)
        if self.dry_run:
            return
        conflict, created = HollihopSyncConflict.objects.get_or_create(
            external_type=external_type,
            external_id=str(external_id),
            defaults={
                "display_name": item["display_name"],
                "normalized_email": item["email"],
                "normalized_phone": item["phone"],
                "reason": item["reason"],
                "candidate_user_ids": item["candidate_user_ids"],
                "status": HollihopSyncConflict.STATUS_PENDING,
            },
        )
        if not created:
            conflict.display_name = item["display_name"]
            conflict.normalized_email = item["email"]
            conflict.normalized_phone = item["phone"]
            conflict.reason = item["reason"]
            conflict.candidate_user_ids = item["candidate_user_ids"]
            # Ignore is sticky. Classroom teacher mappings are also sticky:
            # Hollihop does not expose teacher IDs for some EdUnits, so a manager
            # may resolve that relationship once with resolved_user. User identity
            # conflicts normally disappear after their external ID is linked.
            keep_classroom_mapping = (
                external_type == "classroom"
                and conflict.status == HollihopSyncConflict.STATUS_RESOLVED
                and conflict.resolved_user_id is not None
            )
            if conflict.status != HollihopSyncConflict.STATUS_IGNORED and not keep_classroom_mapping:
                conflict.status = HollihopSyncConflict.STATUS_PENDING
                conflict.resolved_user = None
            conflict.save()
        self._log("sync_conflict", entity_type=external_type, external_id=external_id, details={"conflict_id": conflict.id, "reason": item["reason"]})

    def acquire_lock(self):
        if self.dry_run:
            return
        now = timezone.now()
        with transaction.atomic():
            state, _ = HollihopSyncState.objects.select_for_update().get_or_create(provider="hollihop")
            if state.lock_token and state.lock_expires_at and state.lock_expires_at > now:
                raise HollihopSyncAlreadyRunning("A Hollihop synchronization is already running.")
            self._lock_token = uuid.uuid4()
            state.lock_token = self._lock_token
            state.lock_expires_at = now + timedelta(minutes=settings.HOLLIHOP_SYNC_LOCK_MINUTES)
            state.last_attempt = now
            state.last_status = HollihopSyncState.STATUS_SYNCING
            state.last_error_safe = ""
            state.save()

    def release_lock(self, *, success=True, partial=False, error=""):
        if self.dry_run or not self._lock_token:
            return
        with transaction.atomic():
            state = HollihopSyncState.objects.select_for_update().get(provider="hollihop")
            if state.lock_token != self._lock_token:
                return
            state.lock_token = None
            state.lock_expires_at = None
            state.last_status = (
                HollihopSyncState.STATUS_PARTIAL if partial else HollihopSyncState.STATUS_SUCCESS if success else HollihopSyncState.STATUS_ERROR
            )
            state.last_error_safe = safe_text(error, 500)
            if success:
                state.last_successful_sync = timezone.now()
            state.students_synced = self.summary.students_found
            state.teachers_synced = self.summary.teachers_found
            state.managers_synced = self.summary.managers_found
            state.classrooms_synced = self.summary.classrooms_found
            state.memberships_synced = self.summary.memberships_added + self.summary.memberships_updated
            state.attendance_synced = self.summary.attendance_created + self.summary.attendance_updated
            state.save()
        self._lock_token = None

    def run(self, *, stages, date_from=None, date_to=None):
        self.acquire_lock()
        error_message = ""
        try:
            if "managers" in stages:
                self.sync_managers()
            if "teachers" in stages:
                self.sync_teachers()
            if "students" in stages:
                self.sync_students()
            if "classrooms" in stages:
                self.sync_classrooms()
            if "memberships" in stages:
                self.sync_memberships()
            if "attendance" in stages:
                self.sync_attendance(date_from=date_from, date_to=date_to)
            self.release_lock(success=self.summary.errors == 0, partial=self.summary.errors > 0)
            return self.summary
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {safe_text(exc, 400)}"
            self.summary.errors += 1
            self._log("sync_error", entity_type="sync", details={"error": error_message})
            self.release_lock(success=False, error=error_message)
            raise

    def _all_students(self):
        if self._all_students_cache is None:
            self._all_students_cache = list(self.client.get_students())
        return list(self._all_students_cache)

    def _allowed_edunit_ids(self):
        if self._allowed_edunit_ids_cache is None:
            rows = self._filter_edunits_by_learning_type(
                self.client.get_ed_units(
                    corporative=self.corporative_filter,
                    learning_types=self.allowed_learning_types,
                )
            )
            values = set()
            for row in rows:
                try:
                    values.add(int(row.get("Id")))
                except (TypeError, ValueError):
                    continue
            self._allowed_edunit_ids_cache = values
        return set(self._allowed_edunit_ids_cache)

    def _active_edunits(self):
        if self._active_edunits_cache is None:
            rows = self.client.get_ed_units(
                corporative=self.corporative_filter,
                statuses="Reserve,Forming,Working",
                learning_types=self.allowed_learning_types,
            )
            self._active_edunits_cache = self._filter_edunits_by_learning_type(rows)
        return list(self._active_edunits_cache)

    def _active_edunit_ids(self):
        values = set()
        for row in self._active_edunits():
            try:
                values.add(int(row.get("Id")))
            except (TypeError, ValueError):
                continue
        return values

    def _active_student_ids(self):
        values = set()
        for row in self._all_students():
            try:
                client_id = int(row.get("ClientId"))
            except (TypeError, ValueError):
                continue
            # Unknown/blank statuses are kept fail-safe; only explicitly inactive
            # students are excluded from the current initial-import graph.
            if self._student_active_state(row.get("Status")) is not False:
                values.add(client_id)
        return values

    @staticmethod
    def _relation_is_current(row):
        return safe_text(row.get("Status"), 40).casefold() != "stopped"

    def _filter_relations_to_active_edunits(self, rows, *, require_active_student=False):
        active_edunit_ids = self._active_edunit_ids()
        active_student_ids = self._active_student_ids() if require_active_student else None
        result = []
        for row in self._filter_relations_by_learning_type(rows):
            try:
                edunit_id = int(row.get("EdUnitId"))
                client_id = int(row.get("StudentClientId"))
            except (TypeError, ValueError):
                continue
            if edunit_id not in active_edunit_ids or not self._relation_is_current(row):
                continue
            if active_student_ids is not None and client_id not in active_student_ids:
                continue
            result.append(row)
        return result

    def _selected_relations(self):
        if self._selected_relations_cache is None:
            rows = self.client.get_ed_unit_students(
                corporative=self.corporative_filter,
                query_days=False,
            )
            # Initial/full imports represent the current MakonBook state, not the
            # whole Hollihop history. Historical EdUnits and explicitly inactive
            # students stay in Hollihop and are not materialized as new classes.
            self._selected_relations_cache = self._filter_relations_to_active_edunits(
                rows, require_active_student=True
            )
        return list(self._selected_relations_cache)

    def _selected_edunits(self):
        if self._selected_edunits_cache is None:
            relevant_ids = set()
            for row in self._selected_relations():
                try:
                    relevant_ids.add(int(row.get("EdUnitId")))
                except (TypeError, ValueError):
                    continue
            self._selected_edunits_cache = [
                row for row in self._active_edunits()
                if row.get("Id") is not None and int(row.get("Id")) in relevant_ids
            ]
        return list(self._selected_edunits_cache)

    def _selected_teacher_ids(self):
        # Historical `all` mode used to bypass relationship scoping entirely.
        # Preserve that behaviour only when no LearningType allow-list exists.
        if self.mode == "all" and not self._allowed_learning_type_keys:
            return None
        ids = set()
        for edunit in self._selected_edunits():
            ids.update(self._teacher_ids_for_edunit(edunit))
        return ids

    def _selected_student_ids(self):
        if self.mode == "all" and not self._allowed_learning_type_keys:
            return None
        ids = set()
        for rel in self._selected_relations():
            try:
                ids.add(int(rel.get("StudentClientId")))
            except (TypeError, ValueError):
                continue
        return ids

    def _student_is_selected(self, client_id: int) -> bool:
        if self.mode == "all" and not self._allowed_learning_type_keys:
            return True
        relations = self.client.get_ed_unit_students(
            student_client_id=client_id,
            corporative=self.corporative_filter,
            query_days=False,
        )
        return bool(self._filter_relations_to_active_edunits(relations, require_active_student=False))

    def _teacher_is_selected(self, teacher_id: int) -> bool:
        if self.mode == "all" and not self._allowed_learning_type_keys:
            return True
        selected_ids = {int(row.get("Id")) for row in self._selected_edunits() if row.get("Id") is not None}
        rows = self.client.get_ed_units(
            corporative=self.corporative_filter,
            statuses="Reserve,Forming,Working",
            learning_types=self.allowed_learning_types,
            teacher_id=teacher_id,
        )
        return any(
            row.get("Id") is not None and int(row.get("Id")) in selected_ids
            for row in self._filter_edunits_by_learning_type(rows)
        )

    @staticmethod
    def _student_active_state(status):
        status_key = (status or "").strip().casefold()
        if not status_key:
            return None
        if status_key in settings.HOLLIHOP_ACTIVE_STUDENT_STATUSES:
            return True
        if status_key in settings.HOLLIHOP_INACTIVE_STUDENT_STATUSES:
            return False
        return None

    def _match_user(self, *, external_kind, external_id, email, phone, display_name):
        profile_fields = {
            "student": "hollihop_client_id",
            "teacher": "hollihop_teacher_id",
            "manager": "hollihop_employee_id",
        }
        profile_field = profile_fields.get(external_kind)
        if not profile_field:
            raise ValueError(f"Unsupported Hollihop external kind: {external_kind}")
        linked = UserProfile.objects.select_related("user").filter(**{profile_field: external_id}).first()
        if linked:
            return linked.user, "external_id"

        candidate_ids = set()
        email = normalize_email(email)
        phone = normalize_phone(phone)
        if email:
            candidate_ids.update(User.objects.filter(email__iexact=email).values_list("id", flat=True))
        if phone:
            candidate_ids.update(UserProfile.objects.filter(phone_number=phone).values_list("user_id", flat=True))

        # Keep Hollihop Student identities separate from staff identities. A former
        # student can later appear in Hollihop as an Employee/Manager with the same
        # email or phone, but those are distinct Hollihop records and must not be
        # silently merged into one MakonBook user. Teacher <-> Manager multi-role
        # remains allowed. Explicit external-ID links still win above this block.
        if candidate_ids:
            linked_profiles = UserProfile.objects.filter(user_id__in=candidate_ids)
            if external_kind == "student":
                staff_linked_ids = linked_profiles.filter(
                    Q(hollihop_teacher_id__isnull=False) | Q(hollihop_employee_id__isnull=False)
                ).values_list("user_id", flat=True)
                candidate_ids.difference_update(staff_linked_ids)
            elif external_kind in {"teacher", "manager"}:
                student_linked_ids = linked_profiles.filter(
                    hollihop_client_id__isnull=False
                ).values_list("user_id", flat=True)
                candidate_ids.difference_update(student_linked_ids)

        if len(candidate_ids) == 1:
            return User.objects.get(id=next(iter(candidate_ids))), "contact"
        if len(candidate_ids) > 1:
            self._conflict(
                external_type=external_kind,
                external_id=external_id,
                display_name=display_name,
                email=email,
                phone=phone,
                reason="Email/phone resolve to multiple MakonBook users. Automatic linking was refused.",
                candidate_ids=candidate_ids,
            )
            return None, "conflict"
        return None, "new"

    @staticmethod
    def _contact_collision_is_cross_identity_only(*, external_kind, other_user_ids):
        """Return True when a contact collision is only Student <-> staff.

        Hollihop can contain separate records for the same human (for example an
        old StudentClient plus a later Employee/CEO). Those records must stay
        separate in MakonBook. Teacher <-> Manager remains a supported multi-role
        identity and therefore is not treated as an allowed duplicate contact.
        """
        ids = {int(value) for value in other_user_ids if value}
        if not ids:
            return False
        profiles = UserProfile.objects.filter(user_id__in=ids)
        if profiles.count() != len(ids):
            return False
        if external_kind == "student":
            return not profiles.filter(
                hollihop_teacher_id__isnull=True,
                hollihop_employee_id__isnull=True,
            ).exists()
        if external_kind in {"teacher", "manager"}:
            return not profiles.filter(hollihop_client_id__isnull=True).exists()
        return False

    def _safe_contact_update(self, *, user, profile, external_kind, external_id, email, phone, display_name):
        changed = []
        email = normalize_email(email)
        phone = normalize_phone(phone)
        if email and email != normalize_email(user.email):
            other = User.objects.filter(email__iexact=email).exclude(id=user.id)
            other_ids = list(other.values_list("id", flat=True))
            if other_ids:
                if self._contact_collision_is_cross_identity_only(
                    external_kind=external_kind, other_user_ids=other_ids
                ):
                    self._log(
                        "contact_shared_identity_skipped",
                        entity_type=external_kind, external_id=external_id, user=user,
                        details={"field": "email", "other_user_ids": other_ids},
                    )
                else:
                    self._conflict(
                        external_type=external_kind, external_id=external_id, display_name=display_name,
                        email=email, phone=phone,
                        reason="Hollihop email already belongs to another MakonBook user; email was not overwritten.",
                        candidate_ids=other_ids + [user.id],
                    )
            else:
                user.email = email
                changed.append("email")
        if phone and phone != (profile.phone_number or ""):
            other = UserProfile.objects.filter(phone_number=phone).exclude(user_id=user.id)
            other_ids = list(other.values_list("user_id", flat=True))
            if other_ids:
                if self._contact_collision_is_cross_identity_only(
                    external_kind=external_kind, other_user_ids=other_ids
                ):
                    self._log(
                        "contact_shared_identity_skipped",
                        entity_type=external_kind, external_id=external_id, user=user,
                        details={"field": "phone", "other_user_ids": other_ids},
                    )
                else:
                    self._conflict(
                        external_type=external_kind, external_id=external_id, display_name=display_name,
                        email=email, phone=phone,
                        reason="Hollihop phone already belongs to another MakonBook user; phone was not overwritten.",
                        candidate_ids=other_ids + [user.id],
                    )
            else:
                profile.phone_number = phone
                # phone_number belongs to UserProfile, not auth.User. The profile
                # is saved by the caller after all Hollihop fields are applied.
        return changed

    def _new_username(self, prefix, external_id):
        base = f"{prefix}_{external_id}"
        value = base
        counter = 1
        while User.objects.filter(username=value).exists():
            counter += 1
            value = f"{base}_{counter}"
        return value

    def _maybe_send_credentials(self, user):
        profile = user.profile
        if not self.send_credentials or not profile.hollihop_created:
            return
        # Closed/inactive Hollihop students must never receive fresh credentials.
        # If they resume studying, the next sync reactivates the same account and
        # credentials can then be delivered explicitly.
        if not user.is_active:
            return
        # Initial sync sends access only once. Failed/partial/no-contact
        # deliveries require the explicit Manager "Reset & resend" action;
        # later sync runs must never silently rotate the user's password.
        if profile.credentials_delivery_status != "pending":
            return
        if not can_deliver_temporary_access(user):
            return
        deliver_new_temporary_access(user)

    @staticmethod
    def _employee_role_values(data):
        """Yield role-like Hollihop employee labels without trusting names.

        Hollihop's public GetEmployees schema documents employee identity/contact
        fields and Position, but deployments may also expose role/type fields.
        We intentionally inspect only explicit role/type/position fields and
        never infer Manager access from a person's name.
        """
        keys = (
            "Type", "UserType", "EmployeeType", "AccountType",
            "Role", "RoleName", "Position", "PositionName",
        )
        values = []
        for key in keys:
            value = safe_text(data.get(key), 200).strip()
            if value:
                values.append(value.casefold())
        return values

    @staticmethod
    def _manager_employee_ids():
        """Return explicit Hollihop Employee IDs allowed to become Managers.

        Hollihop's public GetEmployees response does not reliably expose the CRM
        account role (for example CEO).  An explicit Employee-ID allowlist is
        therefore the authoritative fallback and is safer than promoting all
        employees.  Read the Django setting when present, otherwise read the
        environment directly so the hotfix does not require editing settings.py.
        """
        configured = getattr(settings, "HOLLIHOP_MANAGER_EMPLOYEE_IDS", None)
        if configured is None:
            configured = os.getenv("HOLLIHOP_MANAGER_EMPLOYEE_IDS", "")

        if isinstance(configured, str):
            values = [part.strip() for part in configured.split(",")]
        elif isinstance(configured, (list, tuple, set, frozenset)):
            values = list(configured)
        else:
            values = [configured] if configured not in (None, "") else []

        result = set()
        for value in values:
            try:
                employee_id = int(str(value).strip())
            except (TypeError, ValueError):
                continue
            if employee_id > 0:
                result.add(employee_id)
        return result

    @classmethod
    def _employee_is_manager(cls, data):
        try:
            employee_id = int(data.get("Id") or 0)
        except (TypeError, ValueError):
            employee_id = 0
        if employee_id and employee_id in cls._manager_employee_ids():
            return True
        if data.get("IsAdmin") is True or data.get("IsAdministrator") is True:
            return True
        # Some Hollihop deployments expose role/type fields even though the
        # public schema does not guarantee them. Keep supporting those explicit
        # markers, but never infer Manager access from a person's name.
        markers = set(settings.HOLLIHOP_MANAGER_TYPES) | {"ceo", "chief executive officer"}
        for value in cls._employee_role_values(data):
            if value in markers:
                return True
            # Accept compound labels such as "School Administrator" while
            # avoiding arbitrary substring matches inside unrelated words.
            tokens = {token.strip(".,;:/\\()[]{}-_ ") for token in value.replace("/", " ").split()}
            if tokens.intersection(markers):
                return True
        return False

    def sync_managers(self, *, only_employee_id=None):
        employees = self.client.get_employees(
            employee_id=only_employee_id,
            corporative=None if only_employee_id is not None else self.corporative_filter,
        )
        manager_rows = []
        non_manager_linked_rows = []
        for data in employees:
            try:
                employee_id = int(data.get("Id") or 0)
            except (TypeError, ValueError):
                employee_id = 0
            if not employee_id:
                continue
            if self._employee_is_manager(data):
                manager_rows.append(data)
            elif UserProfile.objects.filter(hollihop_employee_id=employee_id).exists():
                # The employee was previously linked as an admin but no longer
                # has an admin marker. Revoke only the Manager role.
                non_manager_linked_rows.append(data)

        self.summary.managers_found += len(manager_rows)
        for data in manager_rows:
            try:
                with transaction.atomic():
                    self._sync_manager(data)
            except Exception as exc:
                self.summary.errors += 1
                self._log("sync_error", entity_type="manager", external_id=data.get("Id"), details={"error": type(exc).__name__})

        if not self.dry_run:
            for data in non_manager_linked_rows:
                try:
                    with transaction.atomic():
                        self._revoke_manager_role(data, reason="Hollihop employee no longer has an admin type/role.")
                except Exception as exc:
                    self.summary.errors += 1
                    self._log("sync_error", entity_type="manager", external_id=data.get("Id"), details={"error": type(exc).__name__})
        else:
            self.summary.managers_updated += len(non_manager_linked_rows)
        return self.summary

    def _sync_manager(self, data):
        employee_id = int(data["Id"])
        first = safe_text(data.get("FirstName"), 150)
        last = safe_text(data.get("LastName"), 150)
        middle = safe_text(data.get("MiddleName"), 150)
        display = " ".join(x for x in [last, first, middle] if x) or f"Manager {employee_id}"
        email = normalize_email(data.get("EMail"))
        phone = normalize_phone(data.get("Mobile") or data.get("Phone"))
        status = safe_text(data.get("Status"), 150)
        active = not bool(data.get("Fired"))
        user, match = self._match_user(
            external_kind="manager", external_id=employee_id,
            email=email, phone=phone, display_name=display,
        )
        if match == "conflict":
            return
        if self.dry_run:
            if user:
                self.summary.managers_matched += 1
                self.summary.managers_updated += 1
            else:
                self.summary.managers_created += 1
            return

        created = False
        if user is None:
            user = User(
                username=self._new_username("hmanager", employee_id),
                first_name=first,
                last_name=last,
                email="",
                is_active=active,
            )
            user.set_unusable_password()
            user.save()
            created = True
            profile = user.profile
            profile.hollihop_created = True
            profile.credentials_delivery_status = "pending"
        else:
            profile = user.profile
            self.summary.managers_matched += 1

        manager_group, _ = Group.objects.get_or_create(name="Manager")
        if active:
            user.groups.add(manager_group)
            if not user.is_active:
                user.is_active = True
        else:
            user.groups.remove(manager_group)
            # A Hollihop Manager can simultaneously be a Teacher or another
            # MakonBook role. Never disable those roles just because the
            # administrative role was fired/revoked in Hollihop.
            has_other_role = user.groups.exclude(name="Manager").exists() or user.is_staff or user.is_superuser
            if profile.hollihop_created and not has_other_role:
                user.is_active = False

        contact_changed = self._safe_contact_update(
            user=user, profile=profile, external_kind="manager", external_id=employee_id,
            email=email, phone=phone, display_name=display,
        )
        if first:
            user.first_name = first
        if last:
            user.last_name = last
        user.save()

        profile.hollihop_employee_id = employee_id
        profile.middle_name = middle
        profile.hollihop_status = status
        profile.hollihop_last_synced_at = timezone.now()
        profile.save()
        if created:
            self.summary.managers_created += 1
            self._log("manager_created", entity_type="manager", external_id=employee_id, user=user)
        else:
            self.summary.managers_updated += 1
            self._log("manager_reactivated" if active else "manager_deactivated", entity_type="manager", external_id=employee_id, user=user)
        self._maybe_send_credentials(user)

    def _revoke_manager_role(self, data, *, reason):
        employee_id = int(data["Id"])
        profile = UserProfile.objects.select_related("user").filter(hollihop_employee_id=employee_id).first()
        if not profile:
            return
        user = profile.user
        manager_group = Group.objects.filter(name="Manager").first()
        if manager_group:
            user.groups.remove(manager_group)
        has_other_role = user.groups.exists() or user.is_staff or user.is_superuser
        if profile.hollihop_created and not has_other_role:
            user.is_active = False
            user.save(update_fields=["is_active"])
        profile.hollihop_status = safe_text(data.get("Status"), 150)
        profile.hollihop_last_synced_at = timezone.now()
        profile.save(update_fields=["hollihop_status", "hollihop_last_synced_at", "updated_at"])
        self.summary.managers_updated += 1
        self._log(
            "manager_deactivated", entity_type="manager", external_id=employee_id, user=user,
            details={"reason": safe_text(reason, 300)},
        )

    def resolve_manager_employee_id_by_phone(self, phone):
        """Resolve exactly one manager-eligible Hollihop employee by phone.

        This is a read-only pilot lookup. A former StudentClient may legitimately
        use the same phone; that does not make the lookup ambiguous because the
        employee identity lives in a separate Hollihop namespace.
        """
        target_phone = normalize_phone(phone)
        if not target_phone:
            raise ValueError("--pilot-manager-phone is not a valid phone number.")

        employees = self.client.get_employees(corporative=None)
        matches = []
        for data in employees:
            current = normalize_phone(data.get("Mobile") or data.get("Phone"))
            if current == target_phone and self._employee_is_manager(data):
                matches.append(data)

        if not matches:
            raise ValueError(
                "No manager-eligible Hollihop employee was found with that normalized phone number. "
                "Add the Employee ID to HOLLIHOP_MANAGER_EMPLOYEE_IDS, or expose an Admin/CEO role marker, then retry."
            )
        if len(matches) > 1:
            ids = sorted(str(row.get("Id")) for row in matches if row.get("Id") is not None)
            raise ValueError(
                "Multiple manager-eligible Hollihop employees use that phone number; pilot sync was refused. "
                f"Employee IDs: {', '.join(ids) or 'unknown'}. Use --pilot-manager-id instead."
            )
        try:
            employee_id = int(matches[0].get("Id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Matched Hollihop employee has an invalid Id.") from exc
        return employee_id

    def run_pilot_manager(self, *, employee_id):
        """Synchronize one manager-eligible Hollihop employee only.

        This is intentionally allowed while SCHOOL_DATA_PROVIDER remains local.
        If the employee's email/phone matches an existing former Student user,
        the same MakonBook User is reused, Manager is added, and the active
        employee role reactivates the account without deleting student history.
        """
        try:
            employee_id = int(employee_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Pilot Hollihop Employee ID must be an integer.") from exc
        if employee_id <= 0:
            raise ValueError("Pilot Hollihop Employee ID must be a positive integer.")

        employees = self.client.get_employees(
            employee_id=employee_id,
            corporative=None,
        )
        if len(employees) != 1:
            if not employees:
                raise ValueError(f"Hollihop employee #{employee_id} was not found.")
            raise ValueError(f"Hollihop returned multiple employee records for ID #{employee_id}.")
        if not self._employee_is_manager(employees[0]):
            role_values = ", ".join(self._employee_role_values(employees[0])) or "none"
            raise ValueError(
                f"Hollihop employee #{employee_id} is not manager-eligible. "
                f"Role/type/position values: {role_values}. Add this Employee ID to HOLLIHOP_MANAGER_EMPLOYEE_IDS if it is an approved manager."
            )

        self.acquire_lock()
        try:
            self.sync_managers(only_employee_id=employee_id)
            self.release_lock(success=self.summary.errors == 0, partial=self.summary.errors > 0)
            return self.summary
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {safe_text(exc, 400)}"
            self.summary.errors += 1
            self._log("sync_error", entity_type="pilot_manager", external_id=employee_id, details={"error": error_message})
            self.release_lock(success=False, error=error_message)
            raise

    def resolve_student_client_id_by_phone(self, phone):
        """Resolve exactly one Hollihop student by normalized phone.

        This is intentionally a read-only lookup used by the local pilot
        command. Full names are never used for identity resolution.
        """
        target_phone = normalize_phone(phone)
        if not target_phone:
            raise ValueError("--pilot-student-phone is not a valid phone number.")

        students = self.client.get_students()
        matches = []
        for data in students:
            current = normalize_phone(data.get("Mobile") or data.get("Phone"))
            if current == target_phone:
                matches.append(data)

        if not matches:
            raise ValueError("No Hollihop student was found with that normalized phone number.")
        if len(matches) > 1:
            ids = sorted(
                str(row.get("ClientId"))
                for row in matches
                if row.get("ClientId") is not None
            )
            raise ValueError(
                "Multiple Hollihop students use that phone number; pilot sync was refused. "
                f"Client IDs: {', '.join(ids) or 'unknown'}. Use --pilot-student-id instead."
            )

        try:
            client_id = int(matches[0].get("ClientId"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Matched Hollihop student has an invalid ClientId.") from exc
        return client_id

    def run_pilot_student(self, *, client_id, date_from=None, date_to=None):
        """Synchronize one student and only the objects needed by that student.

        The pilot intentionally does NOT synchronize managers, unrelated
        students, unrelated teachers, or unrelated classrooms. It is designed
        for a first local end-to-end test while SCHOOL_DATA_PROVIDER remains
        ``local``. All Hollihop API operations used here are read-only.
        """
        try:
            client_id = int(client_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Pilot Hollihop Client ID must be an integer.") from exc
        if client_id <= 0:
            raise ValueError("Pilot Hollihop Client ID must be a positive integer.")

        students = self.client.get_students(client_id=client_id)
        if len(students) != 1:
            if not students:
                raise ValueError(f"Hollihop student #{client_id} was not found.")
            raise ValueError(f"Hollihop returned multiple records for Client ID #{client_id}.")

        self.acquire_lock()
        try:
            # Find only this student's current group relationships.
            relations = self._filter_relations_to_active_edunits(
                self.client.get_ed_unit_students(
                    student_client_id=client_id,
                    corporative=self.corporative_filter,
                    query_days=False,
                ),
                require_active_student=False,
            )
            edunit_ids = sorted({
                int(row.get("EdUnitId"))
                for row in relations
                if str(row.get("EdUnitId") or "").isdigit()
            })

            # A Classroom requires a teacher in the existing MakonBook model,
            # so first synchronize only teachers referenced by this student's
            # EdUnits, then only those EdUnits.
            teacher_ids = set()
            for edunit_id in edunit_ids:
                rows = self._filter_edunits_by_learning_type(
                    self.client.get_ed_units(
                        edunit_id=edunit_id,
                        corporative=self.corporative_filter,
                        learning_types=self.allowed_learning_types,
                    )
                )
                for row in rows:
                    teacher_ids.update(self._teacher_ids_for_edunit(row))

            for teacher_id in sorted(teacher_ids):
                self.sync_teachers(only_teacher_id=teacher_id)
            for edunit_id in edunit_ids:
                self.sync_classrooms(only_edunit_id=edunit_id)

            self.sync_students(only_client_id=client_id)
            self.sync_memberships(only_student_client_id=client_id)
            self.sync_attendance(
                date_from=date_from,
                date_to=date_to,
                only_student_client_id=client_id,
            )

            self.release_lock(success=self.summary.errors == 0, partial=self.summary.errors > 0)
            return self.summary
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {safe_text(exc, 400)}"
            self.summary.errors += 1
            self._log("sync_error", entity_type="pilot_student", external_id=client_id, details={"error": error_message})
            self.release_lock(success=False, error=error_message)
            raise

    def sync_students(self, *, only_client_id=None):
        selected = None if only_client_id else self._selected_student_ids()
        students = self.client.get_students(client_id=only_client_id) if only_client_id is not None else self._all_students()
        if only_client_id is not None and not self._student_is_selected(int(only_client_id)):
            students = []
        elif selected is not None:
            students = [s for s in students if int(s.get("ClientId") or 0) in selected]
        self.summary.students_found += len(students)
        for data in students:
            try:
                with transaction.atomic():
                    self._sync_student(data)
            except Exception as exc:
                self.summary.errors += 1
                self._log("sync_error", entity_type="student", external_id=data.get("ClientId"), details={"error": type(exc).__name__})
        return self.summary

    def _sync_student(self, data):
        client_id = int(data["ClientId"])
        first = safe_text(data.get("FirstName"), 150)
        last = safe_text(data.get("LastName"), 150)
        middle = safe_text(data.get("MiddleName"), 150)
        display = " ".join(x for x in [last, first, middle] if x) or f"Student {client_id}"
        email = normalize_email(data.get("EMail"))
        phone = normalize_phone(data.get("Mobile") or data.get("Phone"))
        status = safe_text(data.get("Status"), 150)
        user, match = self._match_user(external_kind="student", external_id=client_id, email=email, phone=phone, display_name=display)
        if match == "conflict":
            return

        active_state = self._student_active_state(status)

        # Initial import rule: historical/inactive Hollihop students should not
        # create thousands of brand-new closed MakonBook accounts. If a matching
        # MakonBook account already exists, we still link/deactivate it and keep
        # all history. If no account exists yet, skip creation until Hollihop
        # marks the student active again.
        if user is None and active_state is False:
            self.summary.students_inactive_skipped += 1
            self._log(
                "student_inactive_skipped",
                entity_type="student",
                external_id=client_id,
                details={"status": status, "reason": "inactive_without_existing_makonbook_account"},
            )
            return

        if self.dry_run:
            self._dry_run_student_ids.add(client_id)
            if user:
                self.summary.students_matched += 1
                self.summary.students_updated += 1
            else:
                self.summary.students_created += 1
            return

        created = False
        if user is None:
            user = User(username=self._new_username("hstu", client_id), first_name=first, last_name=last, email="")
            user.is_active = True if active_state is None else active_state
            user.set_unusable_password()
            user.save()
            created = True
            profile = user.profile
            profile.hollihop_created = True
            profile.credentials_delivery_status = "pending"
        else:
            profile = user.profile
            self.summary.students_matched += 1

        contact_changed = self._safe_contact_update(
            user=user, profile=profile, external_kind="student", external_id=client_id,
            email=email, phone=phone, display_name=display,
        )
        user_changed = list(contact_changed)
        if first and user.first_name != first:
            user.first_name = first; user_changed.append("first_name")
        if last and user.last_name != last:
            user.last_name = last; user_changed.append("last_name")

        staff_role = user.groups.filter(name__in=["Teacher", "Manager", "Admin", "Support Teacher"]).exists() or user.is_staff or user.is_superuser
        if active_state is not None and not staff_role and user.is_active != active_state:
            user.is_active = active_state; user_changed.append("is_active")
        if user_changed:
            user.save(update_fields=sorted(set(user_changed)))

        profile.hollihop_client_id = client_id
        profile.middle_name = middle
        profile.hollihop_status = status
        profile.hollihop_last_synced_at = timezone.now()
        profile.save()
        if created:
            self.summary.students_created += 1
            self._log("student_created", entity_type="student", external_id=client_id, user=user)
        else:
            self.summary.students_updated += 1
            event = "student_reactivated" if active_state is True else "student_deactivated" if active_state is False else "student_updated"
            self._log(event, entity_type="student", external_id=client_id, user=user)
        self._maybe_send_credentials(user)

    def sync_teachers(self, *, only_teacher_id=None):
        selected = None if only_teacher_id else self._selected_teacher_ids()

        # A dry-run deliberately does not persist teachers in UserProfile.
        # If a targeted dependency was already processed earlier in this run,
        # treat the virtual teacher as present instead of fetching/counting it
        # again. This keeps dry-run counts and API traffic representative of live
        # behaviour.
        if only_teacher_id is not None:
            only_teacher_id = int(only_teacher_id)
            if self.dry_run and only_teacher_id in self._dry_run_teacher_ids:
                return self.summary
            cached = self._teacher_payload_cache_by_id.get(only_teacher_id)
            teachers = [cached] if cached is not None else self.client.get_teachers(teacher_id=only_teacher_id)
        else:
            teachers = self.client.get_teachers()

        # Keep the bulk/targeted payload available for dependency resolution later
        # in the same run. Hollihop support warns against uncontrolled repeated API
        # requests; a cached teacher is enough for classroom dependency sync.
        for row in teachers:
            try:
                self._teacher_payload_cache_by_id[int(row.get("Id"))] = row
            except (TypeError, ValueError):
                continue
        if only_teacher_id is not None and not self._teacher_is_selected(only_teacher_id):
            teachers = []
        elif selected is not None:
            teachers = [t for t in teachers if int(t.get("Id") or 0) in selected]
        self.summary.teachers_found += len(teachers)
        for data in teachers:
            try:
                with transaction.atomic():
                    self._sync_teacher(data)
            except Exception as exc:
                self.summary.errors += 1
                self._log("sync_error", entity_type="teacher", external_id=data.get("Id"), details={"error": type(exc).__name__})
        return self.summary

    def _sync_teacher(self, data):
        teacher_id = int(data["Id"])
        first = safe_text(data.get("FirstName"), 150)
        last = safe_text(data.get("LastName"), 150)
        middle = safe_text(data.get("MiddleName"), 150)
        display = " ".join(x for x in [last, first, middle] if x) or f"Teacher {teacher_id}"
        email = normalize_email(data.get("EMail"))
        phone = normalize_phone(data.get("Mobile") or data.get("Phone"))
        status = safe_text(data.get("Status"), 150)
        active = not bool(data.get("Fired"))
        user, match = self._match_user(external_kind="teacher", external_id=teacher_id, email=email, phone=phone, display_name=display)
        if match == "conflict":
            return
        if self.dry_run:
            self._dry_run_teacher_ids.add(teacher_id)
            if user:
                self.summary.teachers_matched += 1
                self.summary.teachers_updated += 1
            else:
                self.summary.teachers_created += 1
            return

        created = False
        if user is None:
            user = User(username=self._new_username("hteach", teacher_id), first_name=first, last_name=last, email="", is_active=active)
            user.set_unusable_password()
            user.save()
            created = True
            profile = user.profile
            profile.hollihop_created = True
            profile.credentials_delivery_status = "pending"
        else:
            profile = user.profile
            self.summary.teachers_matched += 1

        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        if active:
            user.groups.add(teacher_group)
            if not user.is_active:
                user.is_active = True
        else:
            user.groups.remove(teacher_group)
            has_other_staff_role = user.groups.filter(name__in=["Manager", "Admin", "Support Teacher"]).exists() or user.is_staff or user.is_superuser
            if not has_other_staff_role:
                user.is_active = False

        contact_changed = self._safe_contact_update(
            user=user, profile=profile, external_kind="teacher", external_id=teacher_id,
            email=email, phone=phone, display_name=display,
        )
        if first:
            user.first_name = first
        if last:
            user.last_name = last
        user.save()
        profile.hollihop_teacher_id = teacher_id
        profile.middle_name = middle
        profile.hollihop_status = status
        profile.hollihop_last_synced_at = timezone.now()
        profile.save()
        if created:
            self.summary.teachers_created += 1
            self._log("teacher_created", entity_type="teacher", external_id=teacher_id, user=user)
        else:
            self.summary.teachers_updated += 1
            self._log("teacher_reactivated" if active else "teacher_deactivated", entity_type="teacher", external_id=teacher_id, user=user)
        self._maybe_send_credentials(user)

    @staticmethod
    def _teacher_ids_for_edunit(edunit):
        result = []
        for item in edunit.get("ScheduleItems") or []:
            for raw in item.get("TeacherIds") or []:
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    continue
                if value not in result:
                    result.append(value)
        return result

    def _edunit_is_active(self, data):
        # GetEdUnits rows in this Hollihop tenant do not expose a Status field;
        # activity is expressed by the statuses=Reserve,Forming,Working filter.
        # Never infer inactive merely because data["Status"] is absent.
        try:
            edunit_id = int(data.get("Id"))
        except (TypeError, ValueError):
            return False
        return edunit_id in self._active_edunit_ids()

    def _resolved_classroom_teacher(self, edunit_id: int):
        conflict = (
            HollihopSyncConflict.objects
            .select_related("resolved_user")
            .filter(
                external_type="classroom",
                external_id=str(int(edunit_id)),
                status=HollihopSyncConflict.STATUS_RESOLVED,
                resolved_user__isnull=False,
            )
            .first()
        )
        return conflict.resolved_user if conflict else None

    def ensure_teacher(self, teacher_id: int):
        """Create/link a missing teacher only when an allowed classroom needs it.

        Smart reconciliation uses this dependency fetch instead of repeatedly
        importing every Hollihop teacher before every classroom change. During
        dry-run, successfully processed teachers live only in the in-memory
        virtual set, so dependency checks must consult that set before the DB.
        """
        teacher_id = int(teacher_id)
        existing = User.objects.filter(profile__hollihop_teacher_id=teacher_id).first()
        if existing:
            return existing

        # In dry-run there is intentionally no UserProfile row to find. Without
        # this guard every classroom referencing the same teacher re-fetches and
        # re-counts that teacher.
        if self.dry_run and teacher_id in self._dry_run_teacher_ids:
            return None

        cached = self._teacher_payload_cache_by_id.get(teacher_id)
        rows = [cached] if cached is not None else self.client.get_teachers(teacher_id=teacher_id)
        if not rows:
            return None
        self.summary.teachers_found += 1
        data = rows[0]
        self._teacher_payload_cache_by_id[teacher_id] = data
        try:
            with transaction.atomic():
                self._sync_teacher(data)
        except Exception as exc:
            self.summary.errors += 1
            self._log("sync_error", entity_type="teacher", external_id=teacher_id, details={"error": type(exc).__name__})
            return None
        return User.objects.filter(profile__hollihop_teacher_id=teacher_id).first()

    def ensure_classroom(self, edunit_id: int):
        """Fetch and create one allowed Hollihop EdUnit plus missing teachers."""
        edunit_id = int(edunit_id)
        existing = Classroom.objects.filter(hollihop_edunit_id=edunit_id).first()
        if existing:
            return existing
        rows = self._filter_edunits_by_learning_type(
            self.client.get_ed_units(
                edunit_id=edunit_id,
                corporative=self.corporative_filter,
                learning_types=self.allowed_learning_types,
            )
        )
        if not rows:
            return None
        data = rows[0]
        # A relation can remain in Hollihop long after a class ended. Historical
        # memberships must not recreate old classrooms during a safety sweep.
        if not self._edunit_is_active(data):
            return None
        for teacher_id in self._teacher_ids_for_edunit(data):
            if not UserProfile.objects.filter(hollihop_teacher_id=teacher_id).exists():
                self.ensure_teacher(teacher_id)
        self.summary.classrooms_found += 1
        active_ids = {edunit_id} if self._edunit_is_active(data) else set()
        with transaction.atomic():
            self._sync_classroom(data, active_ids=active_ids)
        return Classroom.objects.filter(hollihop_edunit_id=edunit_id).first()

    def sync_classroom_rows(self, rows):
        """Update already-known EdUnits from a delta/catalog response.

        Unknown classrooms are intentionally NOT created from the catalog alone.
        The caller follows with a targeted relation check; ensure_classroom() then
        creates the class only when an actual current student membership exists.
        This keeps empty/historical Hollihop groups out of MakonBook.
        """
        rows = self._filter_edunits_by_learning_type(rows)
        for data in rows:
            try:
                edunit_id = int(data.get("Id"))
            except (TypeError, ValueError):
                continue
            if not Classroom.objects.filter(hollihop_edunit_id=edunit_id).exists():
                continue
            self.summary.classrooms_found += 1
            try:
                for teacher_id in self._teacher_ids_for_edunit(data):
                    if not UserProfile.objects.filter(hollihop_teacher_id=teacher_id).exists():
                        self.ensure_teacher(teacher_id)
                with transaction.atomic():
                    self._sync_classroom(
                        data,
                        active_ids={edunit_id} if self._edunit_is_active(data) else set(),
                    )
            except Exception as exc:
                self.summary.errors += 1
                self._log("sync_error", entity_type="classroom", external_id=edunit_id, details={"error": type(exc).__name__})
        return self.summary

    def sync_classrooms(self, *, only_edunit_id=None):
        if only_edunit_id is None:
            # Initial/full reconciliation imports only active GROUP classrooms
            # that have at least one current, non-inactive student relation.
            # Hollihop remains the archive for historical/empty EdUnits.
            edunits = self._selected_edunits()
            active_ids = {int(row["Id"]) for row in edunits if row.get("Id") is not None}
        else:
            try:
                target_id = int(only_edunit_id)
            except (TypeError, ValueError):
                return self.summary
            relations = self.client.get_ed_unit_students(
                edunit_id=target_id,
                corporative=self.corporative_filter,
                query_days=False,
            )
            relevant = self._filter_relations_to_active_edunits(relations, require_active_student=True)
            existing = Classroom.objects.filter(hollihop_edunit_id=target_id).exists()
            if not relevant and not existing:
                return self.summary
            edunits = self._filter_edunits_by_learning_type(
                self.client.get_ed_units(
                    edunit_id=target_id,
                    corporative=self.corporative_filter,
                    learning_types=self.allowed_learning_types,
                )
            )
            active_ids = {target_id} if target_id in self._active_edunit_ids() else set()

        self.summary.classrooms_found += len(edunits)
        seen_edunit_ids = set()
        for data in edunits:
            try:
                edunit_id = int(data.get("Id"))
                seen_edunit_ids.add(edunit_id)
                for teacher_id in self._teacher_ids_for_edunit(data):
                    if not UserProfile.objects.filter(hollihop_teacher_id=teacher_id).exists():
                        self.ensure_teacher(teacher_id)
                with transaction.atomic():
                    self._sync_classroom(data, active_ids=active_ids)
            except Exception as exc:
                self.summary.errors += 1
                self._log("sync_error", entity_type="classroom", external_id=data.get("Id"), details={"error": type(exc).__name__})

        # Full reconciliation deactivates old Hollihop-managed classrooms but
        # never deletes their MakonBook history. Only the current relevant graph
        # remains active. Targeted checks must not touch unrelated classrooms.
        if only_edunit_id is None:
            stale = Classroom.objects.filter(
                hollihop_managed=True,
                hollihop_edunit_id__isnull=False,
                is_active=True,
            )
            if self.corporative_filter is not None:
                stale = stale.filter(hollihop_corporative=self.corporative_filter)
            stale = stale.exclude(hollihop_edunit_id__in=seen_edunit_ids)
            stale_count = stale.count()
            if self.dry_run:
                self.summary.classrooms_updated += stale_count
            elif stale_count:
                now = timezone.now()
                for classroom in stale.iterator(chunk_size=200):
                    classroom.is_active = False
                    classroom.hollihop_last_synced_at = now
                    classroom.save(update_fields=["is_active", "hollihop_last_synced_at"])
                    self.summary.classrooms_updated += 1
                    self._log(
                        "classroom_updated", entity_type="classroom",
                        external_id=classroom.hollihop_edunit_id, classroom=classroom,
                        details={"change": "deactivated_not_current_relevant_edunit"},
                    )
        return self.summary

    def _sync_classroom(self, data, *, active_ids):
        if not self._learning_type_allowed(data.get("LearningType")):
            return
        edunit_id = int(data["Id"])
        name = safe_text(data.get("Name"), 255) or f"Hollihop Group {edunit_id}"
        teacher_ids = self._teacher_ids_for_edunit(data)
        teachers = list(User.objects.filter(profile__hollihop_teacher_id__in=teacher_ids).select_related("profile")) if teacher_ids else []
        teacher_map = {u.profile.hollihop_teacher_id: u for u in teachers}
        ordered_teachers = [teacher_map[x] for x in teacher_ids if x in teacher_map]
        fallback = None
        if settings.HOLLIHOP_FALLBACK_TEACHER_USERNAME:
            fallback = User.objects.filter(username=settings.HOLLIHOP_FALLBACK_TEACHER_USERNAME).first()
        manual_teacher = self._resolved_classroom_teacher(edunit_id)

        classroom = Classroom.objects.filter(hollihop_edunit_id=edunit_id).first()
        if classroom is None:
            by_name = list(Classroom.objects.filter(name__iexact=name)[:3])
            if len(by_name) == 1:
                classroom = by_name[0]
            elif len(by_name) > 1:
                self._conflict(
                    external_type="classroom", external_id=edunit_id, display_name=name,
                    reason="Multiple MakonBook classrooms have the same name; automatic EdUnit linking was refused.",
                )
                return

        # During dry-run a newly matched/created teacher is deliberately not in
        # UserProfile yet. Treat teacher IDs successfully processed by the
        # teacher stage as available virtual teachers, so the preview reflects
        # what a live run will actually do.
        virtual_teacher_ids = [x for x in teacher_ids if x in self._dry_run_teacher_ids]
        primary_teacher = (
            ordered_teachers[0]
            if ordered_teachers
            else manual_teacher
            or (classroom.teacher if classroom else fallback)
        )
        if primary_teacher is None and not (self.dry_run and virtual_teacher_ids):
            self._conflict(
                external_type="classroom", external_id=edunit_id, display_name=name,
                reason=(
                    "Hollihop API exposes no teacher for this current EdUnit. "
                    "Choose the correct MakonBook Teacher User ID once in Hollihop Integration; "
                    "the mapping is then reused automatically."
                ),
            )
            return

        if self.dry_run:
            self._dry_run_classroom_ids.add(edunit_id)
            if classroom is None:
                self.summary.classrooms_created += 1
            else:
                self.summary.classrooms_updated += 1
            return

        now = timezone.now()
        created = classroom is None
        classroom_changed = created
        desired_description = safe_text(data.get("Description"), 2000)
        desired_active = edunit_id in active_ids
        desired_corporative = bool(data.get("Corporative"))
        if created:
            classroom = Classroom.objects.create(
                teacher=primary_teacher,
                name=name,
                description=desired_description,
                classroom_type=settings.HOLLIHOP_CLASSROOM_TYPE,
                is_active=desired_active,
                hollihop_edunit_id=edunit_id,
                hollihop_corporative=desired_corporative,
                hollihop_managed=True,
                hollihop_last_synced_at=now,
            )
        else:
            changed_fields = []
            desired_values = {
                "teacher": primary_teacher,
                "name": name,
                "description": desired_description,
                "is_active": desired_active,
                "hollihop_edunit_id": edunit_id,
                "hollihop_corporative": desired_corporative,
                "hollihop_managed": True,
            }
            for field_name, desired_value in desired_values.items():
                current_value = getattr(classroom, field_name)
                if field_name == "teacher":
                    current_value = classroom.teacher_id
                    desired_value = desired_value.id if desired_value else None
                    if current_value == desired_value:
                        continue
                    classroom.teacher = primary_teacher
                else:
                    if current_value == desired_value:
                        continue
                    setattr(classroom, field_name, desired_value)
                changed_fields.append(field_name)
            if changed_fields:
                classroom.hollihop_last_synced_at = now
                changed_fields.append("hollihop_last_synced_at")
                classroom.save(update_fields=sorted(set(changed_fields)))
                classroom_changed = True

        desired_teacher_ids = {u.id for u in ordered_teachers}
        if primary_teacher:
            desired_teacher_ids.add(primary_teacher.id)
        teacher_membership_changed = False
        teacher_candidates = [u for u in ordered_teachers + [primary_teacher] if u is not None]
        for teacher in {u.id: u for u in teacher_candidates}.values():
            membership = ClassroomMembership.objects.filter(classroom=classroom, user=teacher).first()
            if membership and membership.role != "teacher":
                self._conflict(
                    external_type="classroom", external_id=edunit_id, display_name=name,
                    reason=f"User #{teacher.id} is already a student member of this classroom; teacher link was not overwritten.",
                    candidate_ids=[teacher.id],
                )
                continue
            if membership is None:
                ClassroomMembership.objects.create(
                    classroom=classroom, user=teacher, role="teacher", status="approved", approved_at=now,
                    hollihop_managed=True, hollihop_status="teacher", hollihop_last_synced_at=now,
                )
                teacher_membership_changed = True
            else:
                fields = []
                if membership.status != "approved":
                    membership.status = "approved"; fields.append("status")
                if not membership.hollihop_managed:
                    membership.hollihop_managed = True; fields.append("hollihop_managed")
                if membership.hollihop_status != "teacher":
                    membership.hollihop_status = "teacher"; fields.append("hollihop_status")
                if membership.removed_at is not None:
                    membership.removed_at = None; fields.append("removed_at")
                if not membership.approved_at:
                    membership.approved_at = now; fields.append("approved_at")
                if fields:
                    membership.hollihop_last_synced_at = now
                    fields.append("hollihop_last_synced_at")
                    membership.save(update_fields=sorted(set(fields)))
                    teacher_membership_changed = True
        stale_teachers = ClassroomMembership.objects.filter(
            classroom=classroom, role="teacher", hollihop_managed=True
        ).exclude(user_id__in=desired_teacher_ids).exclude(status="removed")
        if stale_teachers.exists():
            stale_teachers.update(status="removed", removed_at=now, hollihop_last_synced_at=now)
            teacher_membership_changed = True

        if created:
            self.summary.classrooms_created += 1
            self._log("classroom_created", entity_type="classroom", external_id=edunit_id, classroom=classroom)
        elif classroom_changed or teacher_membership_changed:
            self.summary.classrooms_updated += 1
            self._log("classroom_updated", entity_type="classroom", external_id=edunit_id, classroom=classroom)

    @staticmethod
    def _membership_status(hollihop_status):
        status = (hollihop_status or "").strip().casefold()
        if status == "stopped":
            return "removed"
        if status == "reserve":
            return "pending"
        return "approved"

    def sync_memberships(
        self,
        *,
        only_student_client_id=None,
        only_edunit_id=None,
        relations=None,
        ensure_dependencies=False,
    ):
        """Reconcile StudentClient <-> EdUnit links.

        `queryDays` is intentionally never requested here. Hollihop support
        identifies GetEdUnitStudents with day/payment payloads as a heavy call.
        Smart reconciliation can pass a targeted student/EdUnit or a preloaded
        relation-only full sweep.
        """
        if only_student_client_id is not None and only_edunit_id is not None:
            raise ValueError("Use only one membership scope: student or EdUnit.")
        if relations is None:
            if only_student_client_id is None and only_edunit_id is None:
                # Reuse the one expensive relation-only payload already used by
                # initial student/classroom selection. Do not download it twice.
                relations = self._selected_relations()
            else:
                relations = self.client.get_ed_unit_students(
                    edunit_id=only_edunit_id,
                    student_client_id=only_student_client_id,
                    corporative=self.corporative_filter,
                    query_days=False,
                )
        # Historical/ended EdUnits can keep Normal relations indefinitely in
        # Hollihop. They must never recreate old classes during reconciliation.
        relations = self._filter_relations_to_active_edunits(
            relations,
            require_active_student=False,
        )
        seen = set()

        for data in relations:
            try:
                edunit_id = int(data.get("EdUnitId"))
                client_id = int(data.get("StudentClientId"))
            except (TypeError, ValueError):
                continue

            classroom = Classroom.objects.filter(hollihop_edunit_id=edunit_id).first()
            if classroom is None and ensure_dependencies:
                classroom = self.ensure_classroom(edunit_id)

            profile = UserProfile.objects.select_related("user").filter(hollihop_client_id=client_id).first()
            virtual_classroom = self.dry_run and edunit_id in self._dry_run_classroom_ids
            virtual_student = self.dry_run and client_id in self._dry_run_student_ids
            if not classroom and not virtual_classroom:
                continue
            if not profile and not virtual_student:
                # During a full initial import students are created before this
                # stage. During smart sync an unknown relation may precede a
                # Student delta, so fetch just that student instead of scanning
                # the whole student catalog.
                if ensure_dependencies and not self.dry_run:
                    rows = self.client.get_students(client_id=client_id)
                    if rows:
                        self.summary.students_found += len(rows)
                        with transaction.atomic():
                            self._sync_student(rows[0])
                        profile = UserProfile.objects.select_related("user").filter(hollihop_client_id=client_id).first()
                if not profile and not virtual_student:
                    continue

            if classroom and profile:
                seen.add((classroom.id, profile.user_id))
            desired_status = self._membership_status(data.get("Status"))
            desired_holli_status = safe_text(data.get("Status"), 30)
            membership = (
                ClassroomMembership.objects.filter(classroom=classroom, user=profile.user).first()
                if classroom and profile else None
            )
            if membership and membership.role != "student":
                self._conflict(
                    external_type="student", external_id=client_id, display_name=data.get("StudentName", ""),
                    email=data.get("StudentEMail", ""), phone=data.get("StudentMobile") or data.get("StudentPhone"),
                    reason=f"User #{profile.user_id} already has a teacher membership in EdUnit #{edunit_id}; student membership was not overwritten.",
                    candidate_ids=[profile.user_id],
                )
                continue
            if self.dry_run:
                if membership is None:
                    self.summary.memberships_added += 1
                elif membership.status != desired_status or not membership.hollihop_managed or membership.hollihop_status != desired_holli_status:
                    self.summary.memberships_updated += 1
                continue

            now = timezone.now()
            if membership is None:
                membership = ClassroomMembership.objects.create(
                    classroom=classroom, user=profile.user, role="student", status=desired_status,
                    approved_at=now if desired_status == "approved" else None,
                    removed_at=now if desired_status == "removed" else None,
                    hollihop_managed=True, hollihop_status=desired_holli_status, hollihop_last_synced_at=now,
                )
                self.summary.memberships_added += 1
                self._log("membership_added", entity_type="student", external_id=client_id, user=profile.user, classroom=classroom)
            else:
                changed_fields = []
                if membership.status != desired_status:
                    membership.status = desired_status; changed_fields.append("status")
                if not membership.hollihop_managed:
                    membership.hollihop_managed = True; changed_fields.append("hollihop_managed")
                if membership.hollihop_status != desired_holli_status:
                    membership.hollihop_status = desired_holli_status; changed_fields.append("hollihop_status")
                if desired_status == "approved" and not membership.approved_at:
                    membership.approved_at = now; changed_fields.append("approved_at")
                if desired_status == "removed" and not membership.removed_at:
                    membership.removed_at = now; changed_fields.append("removed_at")
                elif desired_status != "removed" and membership.removed_at is not None:
                    membership.removed_at = None; changed_fields.append("removed_at")
                if changed_fields:
                    membership.hollihop_last_synced_at = now
                    changed_fields.append("hollihop_last_synced_at")
                    membership.save(update_fields=sorted(set(changed_fields)))
                    self.summary.memberships_updated += 1

        # Reconcile missing links only inside the exact scope represented by the
        # API response. This prevents a targeted student/EdUnit check from
        # removing unrelated memberships. Manual memberships are never touched.
        managed = ClassroomMembership.objects.filter(
            role="student",
            hollihop_managed=True,
            classroom__hollihop_managed=True,
            classroom__hollihop_edunit_id__isnull=False,
        ).select_related("user__profile", "classroom")
        if self.corporative_filter is not None:
            managed = managed.filter(classroom__hollihop_corporative=self.corporative_filter)
        if only_student_client_id is not None:
            managed = managed.filter(user__profile__hollihop_client_id=only_student_client_id)
        if only_edunit_id is not None:
            managed = managed.filter(classroom__hollihop_edunit_id=only_edunit_id)

        for membership in managed:
            if (membership.classroom_id, membership.user_id) in seen or membership.status == "removed":
                continue
            if self.dry_run:
                self.summary.memberships_removed += 1
                continue
            membership.status = "removed"
            membership.removed_at = timezone.now()
            membership.hollihop_last_synced_at = timezone.now()
            membership.save(update_fields=["status", "removed_at", "hollihop_last_synced_at"])
            self.summary.memberships_removed += 1
            self._log(
                "membership_removed", entity_type="student",
                external_id=membership.user.profile.hollihop_client_id,
                user=membership.user, classroom=membership.classroom,
            )
        return self.summary

    def sync_attendance(self, *, date_from=None, date_to=None, only_student_client_id=None, only_edunit_id=None):
        date_to = date_to or timezone.localdate()
        date_from = date_from or (date_to - timedelta(days=settings.HOLLIHOP_RECENT_ATTENDANCE_DAYS - 1))
        if isinstance(date_from, str):
            date_from = parse_date(date_from)
        if isinstance(date_to, str):
            date_to = parse_date(date_to)
        if not date_from or not date_to or date_from > date_to:
            raise ValueError("Invalid Hollihop attendance date range.")
        chunk_days = max(1, settings.HOLLIHOP_ATTENDANCE_CHUNK_DAYS)
        cursor = date_from
        while cursor <= date_to:
            end = min(date_to, cursor + timedelta(days=chunk_days - 1))
            relations = self._filter_relations_by_learning_type(
                self.client.get_ed_unit_students(
                    edunit_id=only_edunit_id,
                    student_client_id=only_student_client_id,
                    corporative=self.corporative_filter,
                    date_from=cursor,
                    date_to=end,
                    query_days=True,
                )
            )
            for rel in relations:
                self._sync_attendance_relation(rel)
            cursor = end + timedelta(days=1)
        return self.summary

    def _sync_attendance_relation(self, rel):
        learning_type = safe_text(rel.get("EdUnitLearningType"), 150)
        if learning_type and not self._learning_type_allowed(learning_type):
            return
        try:
            edunit_id = int(rel.get("EdUnitId"))
            client_id = int(rel.get("StudentClientId"))
        except (TypeError, ValueError):
            return
        classroom = Classroom.objects.filter(hollihop_edunit_id=edunit_id).first()
        profile = UserProfile.objects.select_related("user").filter(hollihop_client_id=client_id).first()
        virtual_classroom = self.dry_run and edunit_id in self._dry_run_classroom_ids
        virtual_student = self.dry_run and client_id in self._dry_run_student_ids
        if not classroom and not virtual_classroom:
            return
        if not profile and not virtual_student:
            return
        for day in rel.get("Days") or []:
            day_date = parse_date(str(day.get("Date") or "")[:10])
            if not day_date:
                continue
            schedule_ids = day.get("ScheduleItemIds") or []
            schedule_key = ",".join(str(x) for x in sorted(schedule_ids, key=lambda x: str(x)))
            external_key = f"hollihop:{client_id}:{edunit_id}:{day_date.isoformat()}:{schedule_key}"
            desired = {
                "student": profile.user if profile else None,
                "classroom": classroom,
                "date": day_date,
                "status": HollihopAttendance.STATUS_ABSENT if bool(day.get("Pass")) else HollihopAttendance.STATUS_PRESENT,
                "description": safe_text(day.get("Description"), 1000),
                "accepted": day.get("Accepted") if isinstance(day.get("Accepted"), bool) else None,
                "schedule_key": schedule_key,
                "source": "hollihop",
            }
            existing = HollihopAttendance.objects.filter(external_key=external_key).first()
            if self.dry_run:
                # If either dependency is virtual, no matching attendance row
                # can already exist for the future MakonBook objects.
                if existing is None:
                    self.summary.attendance_created += 1
                elif any(getattr(existing, key) != value for key, value in desired.items() if key not in {"student", "classroom"}):
                    self.summary.attendance_updated += 1
                continue
            record, created = HollihopAttendance.objects.update_or_create(external_key=external_key, defaults=desired)
            if created:
                self.summary.attendance_created += 1
                self._log("attendance_created", entity_type="attendance", external_id=external_key, user=profile.user, classroom=classroom)
            elif existing and any(getattr(existing, key) != value for key, value in desired.items() if key not in {"student", "classroom"}):
                self.summary.attendance_updated += 1
                self._log("attendance_updated", entity_type="attendance", external_id=external_key, user=profile.user, classroom=classroom)


def full_stage_set():
    return {"managers", "teachers", "students", "classrooms", "memberships", "attendance"}
