from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.base.models import UserProfile
from apps.integrations.models import HollihopSyncLog, HollihopSyncState
from apps.sat.models import Classroom

from .normalization import normalize_email, normalize_phone, safe_text
from .sync import HollihopSyncAlreadyRunning, HollihopSyncEngine

User = get_user_model()


@dataclass
class SmartSyncReport:
    status: str = "ok"
    student_delta_rows: int = 0
    edunit_delta_rows: int = 0
    teacher_rows_checked: int = 0
    manager_poll_ran: bool = False
    membership_sweep_ran: bool = False
    student_profile_sweep_ran: bool = False
    edunit_catalog_sweep_ran: bool = False
    unknown_classrooms_created: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "status": self.status,
            "student_delta_rows": self.student_delta_rows,
            "edunit_delta_rows": self.edunit_delta_rows,
            "teacher_rows_checked": self.teacher_rows_checked,
            "manager_poll_ran": self.manager_poll_ran,
            "membership_sweep_ran": self.membership_sweep_ran,
            "student_profile_sweep_ran": self.student_profile_sweep_ran,
            "edunit_catalog_sweep_ran": self.edunit_catalog_sweep_ran,
            "unknown_classrooms_created": self.unknown_classrooms_created,
            "notes": list(self.notes),
        }


def _parse_cursor(value):
    if not value:
        return None
    if hasattr(value, "tzinfo"):
        dt = value
    else:
        dt = parse_datetime(str(value))
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _cursor_iso(dt):
    if dt is None:
        return ""
    return timezone.localtime(dt).isoformat(timespec="seconds")


def _due(cursor: dict, key: str, *, minutes: int, now) -> bool:
    previous = _parse_cursor(cursor.get(key))
    return previous is None or now - previous >= timedelta(minutes=minutes)


def _existing_student(client_id: int):
    profile = UserProfile.objects.select_related("user").filter(hollihop_client_id=client_id).first()
    return profile.user if profile else None


def _student_needs_update(engine: HollihopSyncEngine, data: dict, user) -> bool:
    if user is None:
        return True
    profile = user.profile
    first = safe_text(data.get("FirstName"), 150)
    last = safe_text(data.get("LastName"), 150)
    middle = safe_text(data.get("MiddleName"), 150)
    email = normalize_email(data.get("EMail"))
    phone = normalize_phone(data.get("Mobile") or data.get("Phone"))
    status = safe_text(data.get("Status"), 150)
    if first and user.first_name != first:
        return True
    if last and user.last_name != last:
        return True
    if profile.middle_name != middle or profile.hollihop_status != status:
        return True
    if email and normalize_email(user.email) != email:
        return True
    if phone and (profile.phone_number or "") != phone:
        return True
    active_state = engine._student_active_state(status)
    staff_role = user.groups.filter(name__in=["Teacher", "Manager", "Admin", "Support Teacher"]).exists() or user.is_staff or user.is_superuser
    if active_state is not None and not staff_role and user.is_active != active_state:
        return True
    return False


def _teacher_needs_update(data: dict, user) -> bool:
    if user is None:
        return True
    profile = user.profile
    first = safe_text(data.get("FirstName"), 150)
    last = safe_text(data.get("LastName"), 150)
    middle = safe_text(data.get("MiddleName"), 150)
    email = normalize_email(data.get("EMail"))
    phone = normalize_phone(data.get("Mobile") or data.get("Phone"))
    status = safe_text(data.get("Status"), 150)
    active = not bool(data.get("Fired"))
    if first and user.first_name != first:
        return True
    if last and user.last_name != last:
        return True
    if profile.middle_name != middle or profile.hollihop_status != status:
        return True
    if email and normalize_email(user.email) != email:
        return True
    if phone and (profile.phone_number or "") != phone:
        return True
    has_teacher_group = user.groups.filter(name="Teacher").exists()
    if has_teacher_group != active:
        return True
    if active and not user.is_active:
        return True
    return False


class HollihopSmartReconciler:
    """Low-load Hollihop -> MakonBook reconciliation.

    Design constraints come directly from Hollihop support:
      * hard burst limit: 600 requests / 30 seconds;
      * GetEdUnitStudents is heavy with Days/payments;
      * full account exports should run only several times per day;
      * EdUnit.lastUpdated does NOT change when a student is added/removed.

    Therefore the 5-minute cycle uses Student/EdUnit deltas plus small catalog
    checks. The relation-only GetEdUnitStudents full sweep is deliberately much
    less frequent (default every 4 hours), while webhooks and targeted relation
    fetches cover many changes immediately/quickly.
    """

    def __init__(self, *, send_credentials=None):
        if send_credentials is None:
            send_credentials = settings.HOLLIHOP_AUTO_SEND_CREDENTIALS
        self.engine = HollihopSyncEngine(send_credentials=bool(send_credentials))
        self.client = self.engine.client
        self.report = SmartSyncReport()

    def _state(self):
        return HollihopSyncState.objects.get_or_create(provider="hollihop")[0]

    def _save_cursor(self, state, cursor, *, last_incremental=None):
        state.cursor_state = cursor
        fields = ["cursor_state", "updated_at"]
        if last_incremental is not None:
            state.last_incremental_sync = last_incremental
            fields.append("last_incremental_sync")
        state.save(update_fields=fields)

    def _sync_one_student_row(self, data):
        try:
            client_id = int(data.get("ClientId"))
        except (TypeError, ValueError):
            return

        # One targeted relation query tells us both eligibility (GROUP-only) and
        # the current memberships. Reuse the same payload; do not request it twice.
        relations = self.client.get_ed_unit_students(
            student_client_id=client_id,
            corporative=self.engine.corporative_filter,
            query_days=False,
        )
        allowed_relations = self.engine._filter_relations_to_active_edunits(
            relations, require_active_student=False
        )
        existing = _existing_student(client_id)

        if allowed_relations:
            self.engine.summary.students_found += 1
            if _student_needs_update(self.engine, data, existing):
                with transaction.atomic():
                    self.engine._sync_student(data)
        elif existing is None:
            # Student exists only in ONLINE/IV units (or no allowed unit): do not
            # create a MakonBook account.
            return

        # Even an empty allowed relation set is meaningful for an existing user:
        # it removes stale Hollihop-managed GROUP memberships after a transfer out.
        self.engine.sync_memberships(
            only_student_client_id=client_id,
            relations=allowed_relations,
            ensure_dependencies=True,
        )

    def _student_delta(self, state, cursor, cycle_started):
        fallback = state.initial_sync_completed_at or state.last_successful_sync or cycle_started
        since = _parse_cursor(cursor.get("students_delta_at")) or fallback
        since = since - timedelta(seconds=settings.HOLLIHOP_CHECKPOINT_OVERLAP_SECONDS)
        rows = self.client.get_students(last_updated_from=_cursor_iso(since))
        self.report.student_delta_rows = len(rows)
        for data in rows:
            self._sync_one_student_row(data)
        cursor["students_delta_at"] = _cursor_iso(cycle_started)

    def _edunit_delta(self, state, cursor, cycle_started):
        fallback = state.initial_sync_completed_at or state.last_successful_sync or cycle_started
        since = _parse_cursor(cursor.get("edunits_delta_at")) or fallback
        since = since - timedelta(seconds=settings.HOLLIHOP_CHECKPOINT_OVERLAP_SECONDS)
        rows = self.engine._filter_edunits_by_learning_type(
            self.client.get_ed_units(
                corporative=self.engine.corporative_filter,
                last_updated_from=_cursor_iso(since),
                learning_types=self.engine.allowed_learning_types,
            )
        )
        self.report.edunit_delta_rows = len(rows)
        errors_before = self.engine.summary.errors
        if rows:
            # Catalog/delta rows alone never create an empty classroom. Existing
            # classes are refreshed first; a targeted relation check below creates
            # an unknown class only when a current student actually belongs to it.
            self.engine.sync_classroom_rows(rows)
            before = self.engine.summary.classrooms_created
            for row in rows:
                try:
                    edunit_id = int(row.get("Id"))
                except (TypeError, ValueError):
                    continue
                self.engine.sync_memberships(
                    only_edunit_id=edunit_id,
                    ensure_dependencies=True,
                )
            self.report.unknown_classrooms_created += self.engine.summary.classrooms_created - before
        if self.engine.summary.errors == errors_before:
            cursor["edunits_delta_at"] = _cursor_iso(cycle_started)
        else:
            self.report.notes.append("EdUnit delta had row errors; its checkpoint was not advanced and will be retried.")

    def _teacher_poll(self, cursor, now):
        if not _due(cursor, "teachers_checked_at", minutes=settings.HOLLIHOP_TEACHER_POLL_MINUTES, now=now):
            return
        rows = self.client.get_teachers()
        local = {
            p.hollihop_teacher_id: p.user
            for p in UserProfile.objects.select_related("user").filter(hollihop_teacher_id__isnull=False)
        }
        self.report.teacher_rows_checked = len(rows)
        for data in rows:
            try:
                teacher_id = int(data.get("Id"))
            except (TypeError, ValueError):
                continue
            user = local.get(teacher_id)
            if user is None:
                # New unassigned teachers do not need a MakonBook account yet.
                # If an EdUnit references one, ensure_teacher() imports it instantly.
                continue
            if _teacher_needs_update(data, user):
                with transaction.atomic():
                    self.engine._sync_teacher(data)
        cursor["teachers_checked_at"] = _cursor_iso(now)

    def _manager_poll(self, cursor, now):
        if not _due(cursor, "managers_checked_at", minutes=settings.HOLLIHOP_MANAGER_POLL_MINUTES, now=now):
            return
        errors_before = self.engine.summary.errors
        self.engine.sync_managers()
        self.report.manager_poll_ran = True
        if self.engine.summary.errors == errors_before:
            cursor["managers_checked_at"] = _cursor_iso(now)
        else:
            self.report.notes.append("Manager poll had row errors; it will retry on the next cycle.")

    def _student_profile_sweep(self, cursor, now):
        if not _due(
            cursor,
            "student_profile_sweep_at",
            minutes=settings.HOLLIHOP_STUDENT_PROFILE_SWEEP_MINUTES,
            now=now,
        ):
            return
        local_ids = set(
            UserProfile.objects.filter(hollihop_client_id__isnull=False).values_list("hollihop_client_id", flat=True)
        )
        if local_ids:
            rows = self.client.get_students()
            for data in rows:
                try:
                    client_id = int(data.get("ClientId"))
                except (TypeError, ValueError):
                    continue
                if client_id not in local_ids:
                    continue
                user = _existing_student(client_id)
                if _student_needs_update(self.engine, data, user):
                    self.engine.summary.students_found += 1
                    with transaction.atomic():
                        self.engine._sync_student(data)
        self.report.student_profile_sweep_ran = True
        cursor["student_profile_sweep_at"] = _cursor_iso(now)

    def _edunit_catalog_sweep(self, cursor, now):
        if not _due(
            cursor,
            "edunit_catalog_sweep_at",
            minutes=settings.HOLLIHOP_EDUNIT_CATALOG_SWEEP_MINUTES,
            now=now,
        ):
            return
        errors_before = self.engine.summary.errors
        # This safety sweep is an ACTIVE catalog, not a historical catalog.
        # Ended Hollihop EdUnits must deactivate locally rather than being kept
        # alive merely because the API still returns their history.
        rows = self.engine._filter_edunits_by_learning_type(
            self.client.get_ed_units(
                corporative=self.engine.corporative_filter,
                statuses="Reserve,Forming,Working",
                learning_types=self.engine.allowed_learning_types,
            )
        )
        remote = {}
        for row in rows:
            try:
                remote[int(row.get("Id"))] = row
            except (TypeError, ValueError):
                continue
        local_qs = Classroom.objects.filter(hollihop_managed=True, hollihop_edunit_id__isnull=False)
        if self.engine.corporative_filter is not None:
            local_qs = local_qs.filter(hollihop_corporative=self.engine.corporative_filter)
        local_ids = set(local_qs.values_list("hollihop_edunit_id", flat=True))
        unknown = [row for edunit_id, row in remote.items() if edunit_id not in local_ids]
        if unknown:
            self.engine.sync_classroom_rows(unknown)
            before = self.engine.summary.classrooms_created
            for row in unknown:
                try:
                    edunit_id = int(row.get("Id"))
                except (TypeError, ValueError):
                    continue
                self.engine.sync_memberships(only_edunit_id=edunit_id, ensure_dependencies=True)
            self.report.unknown_classrooms_created += self.engine.summary.classrooms_created - before

        # Full catalog checks are rare, so they are also the safe place to mark
        # Hollihop-managed classes that no longer exist in the allowed catalog inactive.
        missing_ids = local_ids - set(remote)
        if missing_ids:
            Classroom.objects.filter(hollihop_edunit_id__in=missing_ids, is_active=True).update(
                is_active=False,
                hollihop_last_synced_at=now,
            )
        self.report.edunit_catalog_sweep_ran = True
        if self.engine.summary.errors == errors_before:
            cursor["edunit_catalog_sweep_at"] = _cursor_iso(now)
        else:
            self.report.notes.append("EdUnit catalog sweep had row errors; it will retry on the next cycle.")

    def _membership_sweep(self, cursor, now):
        if not _due(
            cursor,
            "membership_sweep_at",
            minutes=settings.HOLLIHOP_MEMBERSHIP_SWEEP_MINUTES,
            now=now,
        ):
            return
        # This is the only automatic full GetEdUnitStudents sweep. It explicitly
        # excludes Days/payments and defaults to every 4 hours (6 times/day), in
        # line with Hollihop support's warning against frequent full exports.
        errors_before = self.engine.summary.errors
        relations = self.client.get_ed_unit_students(
            corporative=self.engine.corporative_filter,
            query_days=False,
        )
        self.engine.sync_memberships(relations=relations, ensure_dependencies=True)
        self.report.membership_sweep_ran = True
        if self.engine.summary.errors == errors_before:
            cursor["membership_sweep_at"] = _cursor_iso(now)
        else:
            self.report.notes.append("Membership sweep had row errors; it will retry on the next cycle.")

    def run(self, *, require_initial=True):
        state = self._state()
        if require_initial and not state.initial_sync_completed:
            self.report.status = "awaiting_initial_sync"
            self.report.notes.append("Initial full sync has not been run for this database.")
            return self.report, self.engine.summary

        try:
            self.engine.acquire_lock()
        except HollihopSyncAlreadyRunning:
            self.report.status = "busy"
            return self.report, self.engine.summary

        cycle_started = timezone.now()
        cursor = dict(state.cursor_state or {})
        try:
            # Always-light 5-minute delta checks.
            self._student_delta(state, cursor, cycle_started)
            self._edunit_delta(state, cursor, cycle_started)

            # Bounded lower-frequency checks. These timestamps persist in DB, so
            # restarts do not cause an immediate burst of all expensive endpoints.
            self._teacher_poll(cursor, cycle_started)
            self._manager_poll(cursor, cycle_started)
            self._student_profile_sweep(cursor, cycle_started)
            self._edunit_catalog_sweep(cursor, cycle_started)
            self._membership_sweep(cursor, cycle_started)

            state = self._state()
            self._save_cursor(state, cursor, last_incremental=timezone.now())
            HollihopSyncLog.objects.create(
                event_type="smart_sync",
                entity_type="sync",
                details={**self.report.as_dict(), **self.engine.summary.as_dict()},
            )
            self.engine.release_lock(
                success=self.engine.summary.errors == 0,
                partial=self.engine.summary.errors > 0,
            )
            return self.report, self.engine.summary
        except Exception as exc:
            self.engine.summary.errors += 1
            self.engine.release_lock(success=False, error=f"{type(exc).__name__}: {safe_text(exc, 400)}")
            raise


def mark_initial_sync_completed(*, at=None):
    """Enable periodic smart sync only after an explicit successful full import."""
    at = at or timezone.now()
    state, _ = HollihopSyncState.objects.get_or_create(provider="hollihop")
    state.initial_sync_completed = True
    state.initial_sync_completed_at = at
    state.last_incremental_sync = None
    state.cursor_state = {
        "students_delta_at": _cursor_iso(at),
        "edunits_delta_at": _cursor_iso(at),
        # Set low-frequency sweep timestamps to the initial import time. This
        # prevents Celery Beat from immediately re-downloading the same data.
        "teachers_checked_at": _cursor_iso(at),
        "managers_checked_at": _cursor_iso(at),
        "student_profile_sweep_at": _cursor_iso(at),
        "edunit_catalog_sweep_at": _cursor_iso(at),
        "membership_sweep_at": _cursor_iso(at),
    }
    state.save(
        update_fields=[
            "initial_sync_completed",
            "initial_sync_completed_at",
            "last_incremental_sync",
            "cursor_state",
            "updated_at",
        ]
    )
    return state
