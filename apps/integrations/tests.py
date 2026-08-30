from __future__ import annotations

from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth.models import Group, User
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.integrations.hollihop.credentials import deliver_new_temporary_access
from apps.integrations.hollihop.client import HollihopClient, HollihopConfigurationError
from apps.integrations.hollihop.sync import HollihopSyncEngine, SyncSummary
from apps.integrations.models import (
    HollihopAttendance, HollihopCredentialDelivery, HollihopSyncConflict,
    HollihopSyncLog,
)
from apps.sat.models import Classroom, ClassroomMembership
from apps.base.middleware import TemporaryPasswordChangeMiddleware


class FakeHollihopClient:
    def __init__(self):
        self.students = []
        self.employees = []
        self.teachers = []
        self.edunits = []
        self.relations = []

    def get_students(self, *, client_id=None, last_updated_from=None):
        rows = self.students
        if client_id is not None:
            rows = [r for r in rows if int(r["ClientId"]) == int(client_id)]
        return [dict(r) for r in rows]

    def get_employees(self, *, employee_id=None, corporative=None):
        rows = self.employees
        if employee_id is not None:
            rows = [r for r in rows if int(r["Id"]) == int(employee_id)]
        if corporative is not None:
            rows = [r for r in rows if bool(r.get("Corporative")) is bool(corporative)]
        return [dict(r) for r in rows]

    def get_teachers(self, *, teacher_id=None):
        rows = self.teachers
        if teacher_id is not None:
            rows = [r for r in rows if int(r["Id"]) == int(teacher_id)]
        return [dict(r) for r in rows]

    def get_ed_units(
        self,
        *,
        edunit_id=None,
        corporative=None,
        statuses=None,
        last_updated_from=None,
        learning_types=None,
        teacher_id=None,
    ):
        rows = self.edunits
        if edunit_id is not None:
            rows = [r for r in rows if int(r["Id"]) == int(edunit_id)]
        if corporative is not None:
            rows = [r for r in rows if bool(r.get("Corporative")) is bool(corporative)]
        if statuses:
            active = {"Reserve", "Forming", "Working"}
            rows = [r for r in rows if r.get("_status", "Working") in active]
        if learning_types:
            if isinstance(learning_types, str):
                allowed_learning_types = {item.strip().casefold() for item in learning_types.split(",") if item.strip()}
            else:
                allowed_learning_types = {str(item).strip().casefold() for item in learning_types if str(item).strip()}
            rows = [
                r for r in rows
                if str(r.get("LearningType") or "").strip().casefold() in allowed_learning_types
            ]
        if teacher_id is not None:
            teacher_id = int(teacher_id)

            def has_teacher(row):
                direct_ids = row.get("TeacherIds") or []
                schedule_ids = [
                    item
                    for schedule in (row.get("ScheduleItems") or [])
                    for item in (schedule.get("TeacherIds") or [])
                ]
                return teacher_id in {int(item) for item in [*direct_ids, *schedule_ids]}

            rows = [r for r in rows if has_teacher(r)]
        return [dict(r) for r in rows]

    def get_ed_unit_students(self, *, edunit_id=None, student_client_id=None, corporative=None, date_from=None, date_to=None, query_days=False):
        rows = self.relations
        if edunit_id is not None:
            rows = [r for r in rows if int(r["EdUnitId"]) == int(edunit_id)]
        if student_client_id is not None:
            rows = [r for r in rows if int(r["StudentClientId"]) == int(student_client_id)]
        if corporative is not None:
            rows = [r for r in rows if bool(r.get("EdUnitCorporative")) is bool(corporative)]
        result = []
        for row in rows:
            copy = dict(row)
            if not query_days:
                copy.pop("Days", None)
            result.append(copy)
        return result


BASE_SETTINGS = dict(
    HOLLIHOP_MODE="all",
    # These are generic sync-behaviour tests. LearningType scoping has its own
    # production path and must not silently change the legacy fixtures, most of
    # which intentionally omit LearningType/relationship metadata.
    HOLLIHOP_ALLOWED_LEARNING_TYPES=(),
    HOLLIHOP_ACTIVE_STUDENT_STATUSES={"active"},
    HOLLIHOP_INACTIVE_STUDENT_STATUSES={"inactive"},
    HOLLIHOP_FALLBACK_TEACHER_USERNAME="",
    HOLLIHOP_CLASSROOM_TYPE="sat",
    HOLLIHOP_MANAGER_TYPES={"admin", "administrator", "ceo", "chief executive officer", "админ", "администратор"},
    HOLLIHOP_MANAGER_EMPLOYEE_IDS=set(),
    HOLLIHOP_ATTENDANCE_CHUNK_DAYS=30,
    HOLLIHOP_RECENT_ATTENDANCE_DAYS=30,
)


@override_settings(**BASE_SETTINGS)
class HollihopSyncTests(TestCase):
    def setUp(self):
        self.api = FakeHollihopClient()

    @staticmethod
    def student(client_id, *, first="Aziz", last="Aliyev", email="", phone="", status="Active"):
        return {
            "ClientId": client_id, "FirstName": first, "LastName": last, "MiddleName": "",
            "EMail": email, "Mobile": phone, "Status": status,
        }

    @staticmethod
    def teacher(teacher_id, *, email="teacher@example.com", fired=False):
        return {
            "Id": teacher_id, "FirstName": "Tina", "LastName": "Teacher", "MiddleName": "",
            "EMail": email, "Mobile": "+998901111111", "Status": "Works", "Fired": fired,
        }

    @staticmethod
    def employee(employee_id, *, email="admin@example.com", role="Admin", fired=False, corporative=False):
        return {
            "Id": employee_id, "FirstName": "Maya", "LastName": "Admin", "MiddleName": "",
            "EMail": email, "Mobile": "+998902222222", "Status": "Works", "Fired": fired,
            "Type": role, "Corporative": corporative,
        }

    def test_hollihop_admin_employee_becomes_manager(self):
        self.api.employees = [self.employee(700, email="boss@example.com", role="Admin")]
        HollihopSyncEngine(client=self.api).sync_managers()
        user = User.objects.get(profile__hollihop_employee_id=700)
        self.assertTrue(user.groups.filter(name="Manager").exists())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())

    def test_hollihop_admin_position_also_becomes_manager(self):
        row = self.employee(707, email="position-admin@example.com", role="")
        row.pop("Type", None)
        row["Position"] = "Administrator"
        self.api.employees = [row]
        HollihopSyncEngine(client=self.api).sync_managers()
        user = User.objects.get(profile__hollihop_employee_id=707)
        self.assertTrue(user.groups.filter(name="Manager").exists())

    def test_non_admin_employee_is_not_imported_as_manager(self):
        self.api.employees = [self.employee(701, email="accountant@example.com", role="Accountant")]
        HollihopSyncEngine(client=self.api).sync_managers()
        self.assertFalse(User.objects.filter(profile__hollihop_employee_id=701).exists())

    def test_existing_teacher_admin_keeps_teacher_and_gains_manager_role(self):
        user = User.objects.create_user("multi-role-admin", email="multi@example.com", password="KeepPass123!")
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        user.groups.add(teacher_group)
        old_hash = user.password
        self.api.employees = [self.employee(702, email="multi@example.com", role="Administrator")]
        HollihopSyncEngine(client=self.api).sync_managers()
        user.refresh_from_db()
        self.assertTrue(user.groups.filter(name="Teacher").exists())
        self.assertTrue(user.groups.filter(name="Manager").exists())
        self.assertEqual(user.profile.hollihop_employee_id, 702)
        self.assertEqual(user.password, old_hash)

    def test_fired_hollihop_admin_loses_manager_but_keeps_teacher_role(self):
        user = User.objects.create_user("fired-admin-teacher", email="fired@example.com", password="x")
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        user.groups.add(manager_group, teacher_group)
        user.profile.hollihop_employee_id = 703
        user.profile.save()
        self.api.employees = [self.employee(703, email="fired@example.com", role="Admin", fired=True)]
        HollihopSyncEngine(client=self.api).sync_managers()
        user.refresh_from_db()
        self.assertFalse(user.groups.filter(name="Manager").exists())
        self.assertTrue(user.groups.filter(name="Teacher").exists())
        self.assertTrue(user.is_active)

    def test_employee_no_longer_admin_revokes_only_manager_role(self):
        user = User.objects.create_user("former-admin", email="former@example.com", password="x")
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        support_group, _ = Group.objects.get_or_create(name="Support Teacher")
        user.groups.add(manager_group, support_group)
        user.profile.hollihop_employee_id = 704
        user.profile.save()
        self.api.employees = [self.employee(704, email="former@example.com", role="Accountant")]
        HollihopSyncEngine(client=self.api).sync_managers()
        user.refresh_from_db()
        self.assertFalse(user.groups.filter(name="Manager").exists())
        self.assertTrue(user.groups.filter(name="Support Teacher").exists())
        self.assertTrue(user.is_active)

    @override_settings(HOLLIHOP_MODE="corporative")
    def test_corporative_mode_filters_manager_employees(self):
        self.api.employees = [
            self.employee(705, email="regular-admin@example.com", role="Admin", corporative=False),
            self.employee(706, email="corp-admin@example.com", role="Admin", corporative=True),
        ]
        HollihopSyncEngine(client=self.api).sync_managers()
        self.assertFalse(User.objects.filter(profile__hollihop_employee_id=705).exists())
        self.assertTrue(User.objects.filter(profile__hollihop_employee_id=706).exists())


    def test_manager_pilot_phone_resolves_ceo_employee(self):
        self.api.employees = [
            self.employee(700, email="ceo@example.com", role="CEO", fired=False),
        ]
        self.api.employees[0]["Mobile"] = "+998971975838"
        engine = HollihopSyncEngine(client=self.api, dry_run=True)
        self.assertEqual(engine.resolve_manager_employee_id_by_phone("+998 97 197 58 38"), 700)

    @override_settings(HOLLIHOP_MANAGER_EMPLOYEE_IDS={12557})
    def test_manager_allowlist_accepts_employee_when_api_role_is_missing(self):
        employee = self.employee(12557, email="", role="", fired=False)
        employee.pop("Type", None)
        employee["Position"] = None
        employee["Mobile"] = "+998971975838"
        self.api.employees = [employee]

        engine = HollihopSyncEngine(client=self.api, dry_run=True)
        self.assertEqual(engine.resolve_manager_employee_id_by_phone("+998 97 197 58 38"), 12557)
        summary = engine.run_pilot_manager(employee_id=12557)
        self.assertEqual(summary.managers_found, 1)
        self.assertEqual(summary.managers_created, 1)

    @override_settings(HOLLIHOP_MANAGER_EMPLOYEE_IDS={12557})
    def test_allowlisted_manager_does_not_reuse_hollihop_student_account(self):
        former_student = User.objects.create_user("former-student", password="student-pass")
        former_student.is_active = False
        former_student.save(update_fields=["is_active"])
        former_student.profile.hollihop_client_id = 15
        former_student.profile.phone_number = "+998971975838"
        former_student.profile.hollihop_status = "Inactive"
        former_student.profile.save()

        employee = self.employee(12557, email="", role="", fired=False)
        employee.pop("Type", None)
        employee["Position"] = None
        employee["Mobile"] = "+998971975838"
        self.api.employees = [employee]

        summary = HollihopSyncEngine(client=self.api).run_pilot_manager(employee_id=12557)
        former_student.refresh_from_db()
        manager = User.objects.get(profile__hollihop_employee_id=12557)

        self.assertNotEqual(manager.id, former_student.id)
        self.assertEqual(former_student.profile.hollihop_client_id, 15)
        self.assertIsNone(former_student.profile.hollihop_employee_id)
        self.assertFalse(former_student.is_active)
        self.assertTrue(manager.groups.filter(name="Manager").exists())
        self.assertTrue(manager.is_active)
        self.assertFalse(bool(manager.profile.phone_number))
        self.assertEqual(summary.managers_created, 1)
        self.assertEqual(summary.conflicts, 0)

    @override_settings(HOLLIHOP_MANAGER_EMPLOYEE_IDS={12557})
    def test_manager_prefers_existing_unlinked_user_over_student_phone_collision(self):
        existing = User.objects.create_user(
            "existing-manager",
            email="ceo@example.com",
            password="existing-pass",
        )
        former_student = User.objects.create_user("former-student-2", password="student-pass")
        former_student.is_active = False
        former_student.save(update_fields=["is_active"])
        former_student.profile.hollihop_client_id = 15
        former_student.profile.phone_number = "+998971975838"
        former_student.profile.hollihop_status = "Inactive"
        former_student.profile.save()

        employee = self.employee(12557, email="ceo@example.com", role="", fired=False)
        employee.pop("Type", None)
        employee["Position"] = None
        employee["Mobile"] = "+998971975838"
        self.api.employees = [employee]

        summary = HollihopSyncEngine(client=self.api).run_pilot_manager(employee_id=12557)
        existing.refresh_from_db()
        existing.profile.refresh_from_db()
        former_student.refresh_from_db()
        former_student.profile.refresh_from_db()

        self.assertEqual(existing.profile.hollihop_employee_id, 12557)
        self.assertIsNone(existing.profile.hollihop_client_id)
        self.assertTrue(existing.groups.filter(name="Manager").exists())
        self.assertTrue(existing.is_active)
        self.assertEqual(former_student.profile.hollihop_client_id, 15)
        self.assertIsNone(former_student.profile.hollihop_employee_id)
        self.assertFalse(former_student.is_active)
        # The shared phone stays on the Student account because phone login is
        # unique; the Manager keeps the already-valid email login.
        self.assertFalse(bool(existing.profile.phone_number))
        self.assertEqual(former_student.profile.phone_number, "+998971975838")
        self.assertEqual(summary.managers_matched, 1)
        self.assertEqual(summary.conflicts, 0)
        self.assertFalse(HollihopSyncConflict.objects.exists())

    def test_manager_pilot_refuses_non_manager_employee(self):
        employee = self.employee(702, email="staff@example.com", role="Accountant", fired=False)
        employee["Mobile"] = "+998971975838"
        self.api.employees = [employee]
        engine = HollihopSyncEngine(client=self.api, dry_run=True)
        with self.assertRaisesMessage(ValueError, "No manager-eligible Hollihop employee"):
            engine.resolve_manager_employee_id_by_phone("+998971975838")
        with self.assertRaisesMessage(ValueError, "is not manager-eligible"):
            engine.run_pilot_manager(employee_id=702)

    def test_pilot_phone_resolves_exact_normalized_student(self):
        self.api.students = [
            self.student(236, phone="+998 90 123-45-67"),
            self.student(237, phone="+998 91 000-00-00"),
        ]
        engine = HollihopSyncEngine(client=self.api, dry_run=True)
        self.assertEqual(engine.resolve_student_client_id_by_phone("90 123 45 67"), 236)

    def test_pilot_phone_refuses_ambiguous_shared_number(self):
        self.api.students = [
            self.student(236, email="one@example.com", phone="+998901234567"),
            self.student(237, email="two@example.com", phone="90 123 45 67"),
        ]
        engine = HollihopSyncEngine(client=self.api, dry_run=True)
        with self.assertRaisesMessage(ValueError, "Multiple Hollihop students use that phone number"):
            engine.resolve_student_client_id_by_phone("998901234567")

    def test_pilot_student_sync_imports_only_target_and_related_objects(self):
        self.api.students = [
            self.student(236, email="pilot@example.com", phone="+998901234567"),
            self.student(999, email="other@example.com", phone="+998909999999"),
        ]
        self.api.teachers = [self.teacher(10, email="pilot-teacher@example.com"), self.teacher(11, email="other-teacher@example.com")]
        self.api.edunits = [
            {"Id": 14, "Name": "Pilot Group", "Corporative": False, "ScheduleItems": [{"TeacherIds": [10]}]},
            {"Id": 15, "Name": "Other Group", "Corporative": False, "ScheduleItems": [{"TeacherIds": [11]}]},
        ]
        self.api.relations = [
            {
                "EdUnitId": 14, "StudentClientId": 236, "EdUnitCorporative": False, "Status": "Normal",
                "Days": [{"Date": "2026-08-20", "Pass": False, "Description": "", "Accepted": True}],
            },
            {"EdUnitId": 15, "StudentClientId": 999, "EdUnitCorporative": False, "Status": "Normal"},
        ]

        summary = HollihopSyncEngine(client=self.api).run_pilot_student(
            client_id=236, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20)
        )

        pilot = User.objects.get(profile__hollihop_client_id=236)
        self.assertFalse(User.objects.filter(profile__hollihop_client_id=999).exists())
        self.assertTrue(User.objects.filter(profile__hollihop_teacher_id=10).exists())
        self.assertFalse(User.objects.filter(profile__hollihop_teacher_id=11).exists())
        classroom = Classroom.objects.get(hollihop_edunit_id=14)
        self.assertFalse(Classroom.objects.filter(hollihop_edunit_id=15).exists())
        self.assertEqual(ClassroomMembership.objects.get(classroom=classroom, user=pilot).status, "approved")
        self.assertEqual(HollihopAttendance.objects.filter(student=pilot, classroom=classroom).count(), 1)
        self.assertEqual(summary.students_found, 1)
        self.assertEqual(summary.teachers_found, 1)
        self.assertEqual(summary.classrooms_found, 1)


    def test_pilot_dry_run_models_new_dependencies_without_false_conflicts(self):
        self.api.students = [self.student(236, email="pilot@example.com", phone="+998901234567")]
        self.api.teachers = [self.teacher(10, email="pilot-teacher@example.com")]
        self.api.edunits = [
            {"Id": 14, "Name": "Pilot Group", "Corporative": False, "ScheduleItems": [{"TeacherIds": [10]}]},
        ]
        self.api.relations = [
            {
                "EdUnitId": 14, "StudentClientId": 236, "EdUnitCorporative": False, "Status": "Normal",
                "Days": [{"Date": "2026-08-20", "Pass": False, "Description": "", "Accepted": True}],
            },
        ]

        summary = HollihopSyncEngine(client=self.api, dry_run=True).run_pilot_student(
            client_id=236, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20)
        )

        self.assertEqual(summary.students_created, 1)
        self.assertEqual(summary.teachers_created, 1)
        self.assertEqual(summary.classrooms_created, 1)
        self.assertEqual(summary.memberships_added, 1)
        self.assertEqual(summary.attendance_created, 1)
        self.assertEqual(summary.conflicts, 0)
        self.assertFalse(User.objects.filter(profile__hollihop_client_id=236).exists())
        self.assertFalse(User.objects.filter(profile__hollihop_teacher_id=10).exists())
        self.assertFalse(Classroom.objects.filter(hollihop_edunit_id=14).exists())

    @override_settings(
        HOLLIHOP_AUTH_KEY="x" * 64,
        HOLLIHOP_TIMEOUT_SECONDS=20,
        HOLLIHOP_MAX_RETRIES=0,
        HOLLIHOP_MIN_REQUEST_INTERVAL=0,
    )
    def test_client_rejects_function_url_instead_of_api_base(self):
        with self.assertRaises(HollihopConfigurationError):
            HollihopClient(api_url="https://satmakon.t8s.ru/Api/V2/AddStudyRequest")
        client = HollihopClient(api_url="https://satmakon.t8s.ru/Api/V2")
        self.assertEqual(client.api_url, "https://satmakon.t8s.ru/Api/V2")

    def test_new_student_and_duplicate_sync_create_one_user(self):
        self.api.students = [self.student(236, email="aziz@example.com", phone="90 123 45 67")]
        engine = HollihopSyncEngine(client=self.api)
        engine.sync_students()
        user = User.objects.get(profile__hollihop_client_id=236)
        self.assertEqual(user.email, "aziz@example.com")
        self.assertEqual(user.profile.phone_number, "+998901234567")
        self.assertFalse(user.has_usable_password())
        HollihopSyncEngine(client=self.api).sync_students()
        self.assertEqual(User.objects.filter(profile__hollihop_client_id=236).count(), 1)

    def test_existing_email_links_and_keeps_password(self):
        existing = User.objects.create_user("legacy", email="same@example.com", password="KeepThis123!")
        old_hash = existing.password
        self.api.students = [self.student(99, email="same@example.com")]
        HollihopSyncEngine(client=self.api).sync_students()
        existing.refresh_from_db()
        self.assertEqual(existing.profile.hollihop_client_id, 99)
        self.assertEqual(existing.password, old_hash)
        self.assertFalse(existing.profile.hollihop_created)

    def test_same_name_different_students_never_merge(self):
        self.api.students = [
            self.student(1, email="one@example.com"),
            self.student(2, email="two@example.com"),
        ]
        HollihopSyncEngine(client=self.api).sync_students()
        self.assertEqual(User.objects.filter(profile__hollihop_client_id__in=[1, 2]).count(), 2)

    def test_student_deactivation_and_reactivation_preserve_same_user(self):
        self.api.students = [self.student(10, email="student@example.com", status="Active")]
        HollihopSyncEngine(client=self.api).sync_students()
        user = User.objects.get(profile__hollihop_client_id=10)
        self.api.students[0]["Status"] = "Inactive"
        HollihopSyncEngine(client=self.api).sync_students()
        user.refresh_from_db(); self.assertFalse(user.is_active)
        self.api.students[0]["Status"] = "Active"
        HollihopSyncEngine(client=self.api).sync_students()
        user.refresh_from_db(); self.assertTrue(user.is_active)
        self.assertEqual(User.objects.filter(profile__hollihop_client_id=10).count(), 1)

    def test_new_inactive_student_is_not_created_until_they_resume(self):
        self.api.students = [self.student(11, email="former@example.com", status="Inactive")]

        summary = HollihopSyncEngine(client=self.api).sync_students()

        self.assertFalse(User.objects.filter(profile__hollihop_client_id=11).exists())
        self.assertEqual(summary.students_created, 0)
        self.assertEqual(summary.students_inactive_skipped, 1)

        # If the same Hollihop student resumes, a normal active account is
        # created instead of resurrecting a guessed/duplicate record.
        self.api.students[0]["Status"] = "Active"
        summary = HollihopSyncEngine(client=self.api).sync_students()
        user = User.objects.get(profile__hollihop_client_id=11)
        self.assertTrue(user.is_active)
        self.assertEqual(summary.students_created, 1)

    def test_existing_makonbook_user_links_then_closes_for_inactive_student(self):
        existing = User.objects.create_user(
            "legacy-former-student",
            email="former@example.com",
            password="KeepThis123!",
        )
        old_password = existing.password
        self.api.students = [self.student(12, email="former@example.com", status="Inactive")]

        HollihopSyncEngine(client=self.api).sync_students()

        existing.refresh_from_db()
        existing.profile.refresh_from_db()
        self.assertEqual(existing.profile.hollihop_client_id, 12)
        self.assertFalse(existing.is_active)
        self.assertEqual(existing.password, old_password)
        self.assertTrue(User.objects.filter(pk=existing.pk).exists())

    @patch("apps.integrations.hollihop.sync.deliver_new_temporary_access")
    def test_inactive_student_never_receives_credentials(self, mocked_delivery):
        user = User.objects.create_user("inactive-linked", email="inactive@example.com")
        user.profile.hollihop_client_id = 13
        user.profile.hollihop_created = True
        user.profile.credentials_delivery_status = "pending"
        user.profile.save()
        self.api.students = [self.student(13, email="inactive@example.com", status="Inactive")]

        HollihopSyncEngine(client=self.api, send_credentials=True).sync_students()

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        mocked_delivery.assert_not_called()

    def test_manager_teacher_deactivation_keeps_manager_access(self):
        manager = User.objects.create_user("hollihop-manager-test", email="m@example.com", password="x")
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        manager.groups.add(manager_group, teacher_group)
        manager.profile.hollihop_teacher_id = 5
        manager.profile.save()
        self.api.teachers = [self.teacher(5, email="m@example.com", fired=True)]
        HollihopSyncEngine(client=self.api).sync_teachers()
        manager.refresh_from_db()
        self.assertTrue(manager.is_active)
        self.assertTrue(manager.groups.filter(name="Manager").exists())
        self.assertFalse(manager.groups.filter(name="Teacher").exists())

    def _prepare_teacher_and_two_classes(self):
        self.api.teachers = [self.teacher(50)]
        self.api.edunits = [
            {"Id": 14, "Name": "Class A", "Corporative": False, "ScheduleItems": [{"TeacherIds": [50]}], "_status": "Working"},
            {"Id": 15, "Name": "Class B", "Corporative": False, "ScheduleItems": [{"TeacherIds": [50]}], "_status": "Working"},
        ]
        # Full classroom reconciliation intentionally materializes only the
        # current Hollihop graph: an active EdUnit must have at least one
        # current, non-inactive student relation. Seed that graph here instead
        # of relying on the pre-v48 behaviour that imported empty EdUnits.
        self.api.students = [
            self.student(9014, email="fixture14@example.com"),
            self.student(9015, email="fixture15@example.com"),
        ]
        self.api.relations = [
            {"EdUnitId": 14, "StudentClientId": 9014, "Status": "Normal", "EdUnitCorporative": False},
            {"EdUnitId": 15, "StudentClientId": 9015, "Status": "Normal", "EdUnitCorporative": False},
        ]
        HollihopSyncEngine(client=self.api).sync_teachers()
        HollihopSyncEngine(client=self.api).sync_classrooms()

    def test_classroom_transfer_marks_old_membership_removed(self):
        self._prepare_teacher_and_two_classes()
        self.api.students = [self.student(20, email="transfer@example.com")]
        HollihopSyncEngine(client=self.api).sync_students()
        self.api.relations = [{"EdUnitId": 14, "StudentClientId": 20, "Status": "Normal", "EdUnitCorporative": False}]
        HollihopSyncEngine(client=self.api).sync_memberships()
        user = User.objects.get(profile__hollihop_client_id=20)
        a = Classroom.objects.get(hollihop_edunit_id=14); b = Classroom.objects.get(hollihop_edunit_id=15)
        self.assertEqual(ClassroomMembership.objects.get(classroom=a, user=user).status, "approved")
        self.api.relations = [{"EdUnitId": 15, "StudentClientId": 20, "Status": "Normal", "EdUnitCorporative": False}]
        HollihopSyncEngine(client=self.api).sync_memberships()
        self.assertEqual(ClassroomMembership.objects.get(classroom=a, user=user).status, "removed")
        self.assertEqual(ClassroomMembership.objects.get(classroom=b, user=user).status, "approved")

    def test_attendance_absent_to_present_updates_not_duplicates(self):
        self._prepare_teacher_and_two_classes()
        self.api.students = [self.student(30, email="att@example.com")]
        HollihopSyncEngine(client=self.api).sync_students()
        self.api.relations = [{
            "EdUnitId": 14, "StudentClientId": 30, "Status": "Normal", "EdUnitCorporative": False,
            "Days": [{"Date": "2026-08-20", "Pass": True, "Description": "Sick", "Accepted": True}],
        }]
        HollihopSyncEngine(client=self.api).sync_attendance(date_from=date(2026, 8, 20), date_to=date(2026, 8, 20))
        self.assertEqual(HollihopAttendance.objects.count(), 1)
        self.assertEqual(HollihopAttendance.objects.get().status, "absent")
        self.api.relations[0]["Days"][0].update({"Pass": False, "Description": ""})
        HollihopSyncEngine(client=self.api).sync_attendance(date_from=date(2026, 8, 20), date_to=date(2026, 8, 20))
        self.assertEqual(HollihopAttendance.objects.count(), 1)
        self.assertEqual(HollihopAttendance.objects.get().status, "present")

    def test_missing_contacts_records_no_contact_without_plaintext_password(self):
        self.api.students = [self.student(40)]
        HollihopSyncEngine(client=self.api).sync_students()
        user = User.objects.get(profile__hollihop_client_id=40)
        delivery = deliver_new_temporary_access(user)
        user.refresh_from_db()
        self.assertEqual(delivery.overall_status, "no_contact")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(hasattr(delivery, "password"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MAKONBOOK_SMS_PROVIDER="disabled")
    def test_email_delivery_sets_hashed_temporary_password(self):
        self.api.students = [self.student(41, email="mail@example.com")]
        HollihopSyncEngine(client=self.api).sync_students()
        user = User.objects.get(profile__hollihop_client_id=41)
        delivery = deliver_new_temporary_access(user)
        user.refresh_from_db()
        self.assertEqual(delivery.email_status, "sent")
        self.assertEqual(delivery.sms_status, "not_available")
        self.assertEqual(delivery.overall_status, "sent")
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.profile.must_change_password)
        self.assertNotIn("Temporary password", user.password)

    def test_dry_run_writes_nothing(self):
        self.api.students = [self.student(77, email="dry@example.com")]
        summary = HollihopSyncEngine(client=self.api, dry_run=True).sync_students()
        self.assertEqual(summary.students_created, 1)
        self.assertFalse(User.objects.filter(profile__hollihop_client_id=77).exists())
        self.assertEqual(HollihopSyncConflict.objects.count(), 0)
        self.assertEqual(HollihopSyncLog.objects.count(), 0)

    def test_ambiguous_email_and_phone_create_conflict_not_link(self):
        first = User.objects.create_user("holli-candidate-email", email="shared@example.com", password="x")
        second = User.objects.create_user("holli-candidate-phone", email="other@example.com", password="x")
        second.profile.phone_number = "+998901234567"
        second.profile.save()
        self.api.students = [self.student(78, email="shared@example.com", phone="90 123 45 67")]
        summary = HollihopSyncEngine(client=self.api).sync_students()
        self.assertEqual(summary.conflicts, 1)
        self.assertEqual(HollihopSyncConflict.objects.filter(external_type="student", external_id="78", status="pending").count(), 1)
        self.assertFalse(User.objects.filter(profile__hollihop_client_id=78).exists())
        self.assertIsNone(first.profile.hollihop_client_id)

    @override_settings(HOLLIHOP_MODE="users")
    def test_users_mode_uses_noncorporative_memberships(self):
        self.api.students = [
            self.student(81, email="regular@example.com"),
            self.student(82, email="corporate@example.com"),
        ]
        self.api.edunits = [
            {"Id": 1, "Name": "Regular", "Corporative": False, "_status": "Working"},
            {"Id": 2, "Name": "Corporate", "Corporative": True, "_status": "Working"},
        ]
        self.api.relations = [
            {"EdUnitId": 1, "StudentClientId": 81, "EdUnitCorporative": False, "Status": "Normal"},
            {"EdUnitId": 2, "StudentClientId": 82, "EdUnitCorporative": True, "Status": "Normal"},
        ]
        HollihopSyncEngine(client=self.api).sync_students()
        self.assertTrue(User.objects.filter(profile__hollihop_client_id=81).exists())
        self.assertFalse(User.objects.filter(profile__hollihop_client_id=82).exists())

    def test_missing_edunit_deactivates_but_does_not_delete_classroom(self):
        self._prepare_teacher_and_two_classes()
        classroom = Classroom.objects.get(hollihop_edunit_id=15)
        self.assertTrue(classroom.is_active)
        self.api.edunits = [self.api.edunits[0]]
        HollihopSyncEngine(client=self.api).sync_classrooms()
        classroom.refresh_from_db()
        self.assertFalse(classroom.is_active)
        self.assertTrue(Classroom.objects.filter(pk=classroom.pk).exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MAKONBOOK_SMS_PROVIDER="disabled")
    def test_successful_credentials_are_not_resent_on_next_sync(self):
        self.api.students = [self.student(83, email="once@example.com")]
        HollihopSyncEngine(client=self.api, send_credentials=True).sync_students()
        self.assertEqual(HollihopCredentialDelivery.objects.count(), 1)
        HollihopSyncEngine(client=self.api, send_credentials=True).sync_students()
        self.assertEqual(HollihopCredentialDelivery.objects.count(), 1)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MAKONBOOK_SMS_PROVIDER="disabled")
    @patch("apps.integrations.hollihop.credentials.EmailMultiAlternatives.send", side_effect=RuntimeError("mail down"))
    def test_email_failure_keeps_account_and_records_safe_failure(self, _send):
        self.api.students = [self.student(84, email="mailfail@example.com")]
        HollihopSyncEngine(client=self.api).sync_students()
        user = User.objects.get(profile__hollihop_client_id=84)
        delivery = deliver_new_temporary_access(user)
        user.refresh_from_db()
        self.assertEqual(delivery.overall_status, "failed")
        self.assertEqual(delivery.email_status, "failed")
        self.assertIn("Email provider error", delivery.email_error_safe)
        # No delivery channel received the generated secret. The safe behaviour
        # is to restore the previous authentication state rather than leave an
        # unreachable password hash on the account. A later retry generates a
        # fresh temporary password.
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.profile.must_change_password)
        self.assertEqual(user.profile.credentials_delivery_status, "failed")

    def test_ignored_conflict_stays_ignored_on_later_sync(self):
        first = User.objects.create_user("holli-ignore-email", email="ignore@example.com", password="x")
        second = User.objects.create_user("holli-ignore-phone", email="other-ignore@example.com", password="x")
        second.profile.phone_number = "+998901234570"
        second.profile.save()
        self.api.students = [self.student(86, email="ignore@example.com", phone="+998901234570")]
        HollihopSyncEngine(client=self.api).sync_students()
        conflict = HollihopSyncConflict.objects.get(external_type="student", external_id="86")
        conflict.status = "ignored"
        conflict.save()
        HollihopSyncEngine(client=self.api).sync_students()
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "ignored")

    @override_settings(MAKONBOOK_SMS_PROVIDER="disabled")
    def test_disabled_sms_is_deferred_without_rotating_password(self):
        self.api.students = [self.student(87, phone="+998901234571")]
        HollihopSyncEngine(client=self.api, send_credentials=True).sync_students()
        user = User.objects.get(profile__hollihop_client_id=87)
        self.assertEqual(HollihopCredentialDelivery.objects.count(), 0)
        self.assertEqual(user.profile.credentials_delivery_status, "pending")
        self.assertFalse(user.has_usable_password())
        HollihopSyncEngine(client=self.api, send_credentials=True).sync_students()
        self.assertEqual(HollihopCredentialDelivery.objects.count(), 0)

    @override_settings(MAKONBOOK_SMS_PROVIDER="disabled")
    def test_direct_delivery_treats_disabled_sms_as_unavailable(self):
        self.api.students = [self.student(85, phone="+998901234568")]
        HollihopSyncEngine(client=self.api).sync_students()
        user = User.objects.get(profile__hollihop_client_id=85)
        delivery = deliver_new_temporary_access(user)
        user.refresh_from_db()
        self.assertEqual(delivery.overall_status, "no_contact")
        self.assertEqual(delivery.sms_status, "not_available")
        self.assertFalse(user.has_usable_password())

    def test_auth_backend_accepts_email_and_normalized_phone(self):
        user = User.objects.create_user("holli-login-user", email="Login@Example.com", password="StrongPass123!")
        user.profile.phone_number = "+998901234569"
        user.profile.save()
        self.assertEqual(authenticate(username="login@example.com", password="StrongPass123!"), user)
        self.assertEqual(authenticate(username="90 123 45 69", password="StrongPass123!"), user)

    @override_settings(ROOT_URLCONF="apps.base.urls")
    def test_temporary_password_middleware_blocks_normal_pages(self):
        user = User.objects.create_user("holli-temp-gate", password="StrongPass123!")
        user.profile.must_change_password = True
        user.profile.save()
        request = RequestFactory().get("/dashboard/")
        request.user = user
        response = TemporaryPasswordChangeMiddleware(lambda _request: HttpResponse("normal"))(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("change-temporary-password", response.url)


@override_settings(
    **BASE_SETTINGS,
    SCHOOL_DATA_PROVIDER="hollihop",
    HOLLIHOP_ENABLED=True,
    HOLLIHOP_WEBHOOK_SECRET="secret123",
    HOLLIHOP_WEBHOOK_RATE_LIMIT=120,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "hollihop-webhook-tests",
        }
    },
)
class HollihopWebhookTests(TestCase):
    def test_unauthorized_webhook_rejected(self):
        response = self.client.post(reverse("hollihop_webhook"), {"TriggerType": "Created", "ObjectType": "StudentClient", "ObjectId": "1"})
        self.assertEqual(response.status_code, 403)

    @patch("apps.integrations.hollihop.views.process_student_webhook.delay")
    def test_replayed_authorized_webhook_is_accepted_and_delegated(self, mocked_delay):
        payload = {"key": "secret123", "TriggerType": "PassSet", "ObjectType": "StudentClient", "ObjectId": "236"}
        first = self.client.post(reverse("hollihop_webhook"), payload)
        second = self.client.post(reverse("hollihop_webhook"), payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mocked_delay.call_count, 2)


@override_settings(
    **BASE_SETTINGS,
    HOLLIHOP_API_URL="https://school.example/Api/V2",
    HOLLIHOP_AUTH_KEY="test-auth-key",
)
class HollihopManagementCommandTests(TestCase):
    @override_settings(SCHOOL_DATA_PROVIDER="local", HOLLIHOP_ENABLED=False)
    @patch("apps.integrations.management.commands.sync_hollihop.HollihopSyncEngine")
    def test_dry_run_is_allowed_while_provider_is_local(self, engine_cls):
        engine_cls.return_value.run.return_value = SyncSummary(students_found=3, students_created=2)
        output = StringIO()
        call_command("sync_hollihop", "--students", "--dry-run", stdout=output)
        engine_cls.assert_called_once_with(dry_run=True, send_credentials=False)
        engine_cls.return_value.run.assert_called_once()
        self.assertIn("DRY RUN complete", output.getvalue())
        self.assertIn("Found: 3", output.getvalue())

    @override_settings(SCHOOL_DATA_PROVIDER="local", HOLLIHOP_ENABLED=False)
    def test_live_sync_is_rejected_while_provider_is_local(self):
        with self.assertRaisesMessage(CommandError, "Live sync is disabled"):
            call_command("sync_hollihop", "--students")

    @override_settings(SCHOOL_DATA_PROVIDER="hollihop", HOLLIHOP_ENABLED=True)
    def test_dry_run_rejects_send_credentials(self):
        with self.assertRaisesMessage(CommandError, "--send-credentials cannot be used with --dry-run"):
            call_command("sync_hollihop", "--students", "--dry-run", "--send-credentials")

    @override_settings(SCHOOL_DATA_PROVIDER="local", HOLLIHOP_ENABLED=False)
    @patch("apps.integrations.management.commands.sync_hollihop.HollihopSyncEngine")
    def test_manager_stage_is_available_in_dry_run(self, engine_cls):
        engine_cls.return_value.run.return_value = SyncSummary(managers_found=2, managers_created=1)
        output = StringIO()
        call_command("sync_hollihop", "--managers", "--dry-run", stdout=output)
        stages = engine_cls.return_value.run.call_args.kwargs["stages"]
        self.assertEqual(stages, {"managers"})
        self.assertIn("Managers (Hollihop admin employees)", output.getvalue())

    @override_settings(SCHOOL_DATA_PROVIDER="local", HOLLIHOP_ENABLED=True)
    @patch("apps.integrations.management.commands.sync_hollihop.HollihopSyncEngine")
    def test_live_pilot_phone_is_allowed_while_provider_stays_local(self, engine_cls):
        engine = engine_cls.return_value
        engine.resolve_student_client_id_by_phone.return_value = 236
        engine.run_pilot_student.return_value = SyncSummary(students_found=1, students_created=1)
        output = StringIO()
        call_command("sync_hollihop", "--pilot-student-phone", "90 123 45 67", stdout=output)
        engine.resolve_student_client_id_by_phone.assert_called_once_with("90 123 45 67")
        engine.run_pilot_student.assert_called_once()
        self.assertEqual(engine.run_pilot_student.call_args.kwargs["client_id"], 236)
        self.assertIn("Pilot: YES", output.getvalue())
        self.assertIn("Pilot target: Hollihop Student #236", output.getvalue())

    @override_settings(SCHOOL_DATA_PROVIDER="local", HOLLIHOP_ENABLED=True)

    @override_settings(
        HOLLIHOP_ENABLED=True,
        SCHOOL_DATA_PROVIDER="local",
        HOLLIHOP_API_URL="https://example.t8s.ru/Api/V2",
        HOLLIHOP_AUTH_KEY="x" * 64,
    )
    @patch("apps.integrations.management.commands.sync_hollihop.HollihopSyncEngine")
    def test_live_pilot_manager_phone_is_allowed_while_provider_stays_local(self, engine_cls):
        engine = engine_cls.return_value
        engine.resolve_manager_employee_id_by_phone.return_value = 701
        engine.run_pilot_manager.return_value = SyncSummary(managers_found=1, managers_matched=1)
        output = StringIO()
        call_command("sync_hollihop", "--pilot-manager-phone", "+998971975838", stdout=output)
        engine.resolve_manager_employee_id_by_phone.assert_called_once_with("+998971975838")
        engine.run_pilot_manager.assert_called_once_with(employee_id=701)
        self.assertIn("Pilot target: Hollihop Manager Employee #701", output.getvalue())

    def test_pilot_cannot_be_combined_with_bulk_stage_flags(self):
        with self.assertRaisesMessage(CommandError, "Pilot mode cannot be combined"):
            call_command("sync_hollihop", "--pilot-student-id", "236", "--all")

    @override_settings(
        SCHOOL_DATA_PROVIDER="local",
        HOLLIHOP_ENABLED=True,
        HOLLIHOP_API_URL="https://example.t8s.ru/Api/V2",
        HOLLIHOP_AUTH_KEY="x" * 64,
    )
    @patch.dict("os.environ", {
        "HOLLIHOP_SYNC_SCOPE": "single",
        "HOLLIHOP_SYNC_PHONE": "+998971975838",
        "HOLLIHOP_SEND_CREDENTIALS": "true",
    }, clear=False)
    @patch("apps.integrations.management.commands.sync_hollihop.HollihopSyncEngine")
    def test_env_single_scope_needs_no_cli_selector(self, engine_cls):
        engine = engine_cls.return_value
        engine.resolve_manager_employee_id_by_phone.side_effect = ValueError(
            "No manager-eligible Hollihop employee was found with that normalized phone number."
        )
        engine.client.get_teachers.return_value = []
        engine.resolve_student_client_id_by_phone.return_value = 236
        engine.run_pilot_student.return_value = SyncSummary(students_found=1, students_created=1)
        output = StringIO()
        call_command("sync_hollihop", stdout=output)
        engine_cls.assert_called_once_with(dry_run=False, send_credentials=True)
        engine.run_pilot_student.assert_called_once()
        self.assertEqual(engine.run_pilot_student.call_args.kwargs["client_id"], 236)
        self.assertIn("Scope: single", output.getvalue())
        self.assertIn("Single phone: +998971975838", output.getvalue())

    @override_settings(
        SCHOOL_DATA_PROVIDER="local",
        HOLLIHOP_ENABLED=False,
        HOLLIHOP_API_URL="https://example.t8s.ru/Api/V2",
        HOLLIHOP_AUTH_KEY="x" * 64,
    )
    @patch.dict("os.environ", {
        "HOLLIHOP_SYNC_SCOPE": "all",
        "HOLLIHOP_SEND_CREDENTIALS": "true",
    }, clear=False)
    @patch("apps.integrations.management.commands.sync_hollihop.HollihopSyncEngine")
    def test_env_all_dry_run_uses_full_stages_without_sending_credentials(self, engine_cls):
        engine_cls.return_value.run.return_value = SyncSummary()
        call_command("sync_hollihop", "--dry-run")
        engine_cls.assert_called_once_with(dry_run=True, send_credentials=False)
        self.assertEqual(engine_cls.return_value.run.call_args.kwargs["stages"], {
            "managers", "teachers", "students", "classrooms", "memberships", "attendance"
        })

    @override_settings(SCHOOL_DATA_PROVIDER="hollihop", HOLLIHOP_ENABLED=True)
    def test_invalid_attendance_date_range_is_rejected(self):
        with self.assertRaisesMessage(CommandError, "--from must be before or equal to --to"):
            call_command("sync_hollihop", "--attendance", "--from", "2026-08-22", "--to", "2026-08-21")
