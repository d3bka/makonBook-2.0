from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.sat.models import Classroom, ClassroomJoinCode, ClassroomMembership


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "classroom-v44"}},
    CLASSROOM_JOIN_USER_MAX_ATTEMPTS=10,
    CLASSROOM_JOIN_IP_MAX_ATTEMPTS=100,
    CLASSROOM_JOIN_RATE_WINDOW_SECONDS=600,
)
class ClassroomIntegrityV44Tests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        self.manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.teacher = User.objects.create_user(username="teacher_v44", password="pass12345")
        self.teacher.groups.add(self.teacher_group)
        self.student = User.objects.create_user(username="student_v44", password="pass12345")

    def _create_form_token(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("create_classroom"))
        self.assertEqual(response.status_code, 200)
        return self.client.session["classroom_create_token"]

    def _create_classroom(self, *, name="SAT Test", classroom_type="sat"):
        token = self._create_form_token()
        response = self.client.post(
            reverse("create_classroom"),
            {"name": name, "description": "Regression", "classroom_type": classroom_type, "submission_token": token},
        )
        self.assertEqual(response.status_code, 302)
        return Classroom.objects.get(name=name)

    def _join_code(self, classroom, code="123456"):
        return ClassroomJoinCode.objects.create(
            classroom=classroom,
            code=code,
            is_active=True,
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_create_classroom_creates_approved_teacher_membership(self):
        classroom = self._create_classroom()
        membership = ClassroomMembership.objects.get(classroom=classroom, user=self.teacher)
        self.assertEqual(membership.role, "teacher")
        self.assertEqual(membership.status, "approved")

    def test_same_create_submission_token_is_idempotent(self):
        token = self._create_form_token()
        url = reverse("create_classroom")
        payload = {"name": "One classroom", "classroom_type": "sat", "submission_token": token}
        self.client.post(url, payload)
        self.client.post(url, payload)
        self.assertEqual(Classroom.objects.filter(name="One classroom").count(), 1)

    def test_too_long_classroom_name_does_not_hit_database_error(self):
        token = self._create_form_token()
        response = self.client.post(
            reverse("create_classroom"),
            {"name": "x" * 256, "classroom_type": "sat", "submission_token": token},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Classroom.objects.exists())

    def test_secondary_teacher_sees_assigned_classroom(self):
        classroom = self._create_classroom()
        second = User.objects.create_user(username="second_v44", password="pass12345")
        second.groups.add(self.teacher_group)
        ClassroomMembership.objects.create(
            classroom=classroom, user=second, role="teacher", status="approved", approved_at=timezone.now()
        )
        self.client.force_login(second)
        response = self.client.get(reverse("teacher_classroom_list"))
        self.assertContains(response, classroom.name)

    def test_student_can_submit_valid_join_request(self):
        classroom = self._create_classroom()
        self._join_code(classroom)
        self.client.force_login(self.student)
        response = self.client.post(reverse("submit_classroom_join_request"), {"join_code": "123456"})
        self.assertEqual(response.status_code, 302)
        membership = ClassroomMembership.objects.get(classroom=classroom, user=self.student)
        self.assertEqual(membership.status, "pending")
        self.assertEqual(membership.role, "student")

    def test_repeated_join_request_does_not_create_duplicate(self):
        classroom = self._create_classroom()
        self._join_code(classroom)
        self.client.force_login(self.student)
        url = reverse("submit_classroom_join_request")
        self.client.post(url, {"join_code": "123456"})
        self.client.post(url, {"join_code": "123456"})
        self.assertEqual(ClassroomMembership.objects.filter(classroom=classroom, user=self.student).count(), 1)

    def test_staff_account_cannot_submit_student_join_request(self):
        classroom = self._create_classroom()
        self._join_code(classroom)
        manager = User.objects.create_user(username="manager_v44", password="pass12345")
        manager.groups.add(self.manager_group)
        self.client.force_login(manager)
        response = self.client.post(reverse("submit_classroom_join_request"), {"join_code": "123456"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ClassroomMembership.objects.filter(classroom=classroom, user=manager).exists())

    def test_redis_cache_failure_does_not_turn_join_into_500(self):
        classroom = self._create_classroom()
        self._join_code(classroom)
        self.client.force_login(self.student)
        with patch("apps.sat.views.cache.get", side_effect=RuntimeError("redis down")):
            response = self.client.post(reverse("submit_classroom_join_request"), {"join_code": "123456"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ClassroomMembership.objects.filter(classroom=classroom, user=self.student, status="pending").exists())

    def test_inactive_classroom_rejects_join_code(self):
        classroom = self._create_classroom()
        classroom.is_active = False
        classroom.save(update_fields=["is_active"])
        self._join_code(classroom)
        self.client.force_login(self.student)
        self.client.post(reverse("submit_classroom_join_request"), {"join_code": "123456"})
        self.assertFalse(ClassroomMembership.objects.filter(classroom=classroom, user=self.student).exists())

    def test_hollihop_classroom_rejects_manual_join(self):
        classroom = self._create_classroom()
        classroom.hollihop_managed = True
        classroom.hollihop_edunit_id = 9911
        classroom.save(update_fields=["hollihop_managed", "hollihop_edunit_id"])
        self._join_code(classroom)
        self.client.force_login(self.student)
        self.client.post(reverse("submit_classroom_join_request"), {"join_code": "123456"})
        self.assertFalse(ClassroomMembership.objects.filter(classroom=classroom, user=self.student).exists())

    def test_approve_is_idempotent_and_creates_section_access(self):
        classroom = self._create_classroom()
        membership = ClassroomMembership.objects.create(
            classroom=classroom, user=self.student, role="student", status="pending"
        )
        self.client.force_login(self.teacher)
        url = reverse("approve_join_request", args=[classroom.id, membership.id])
        first = self.client.post(url)
        second = self.client.post(url)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, "approved")
        self.assertEqual(membership.section_access.count(), 3)

    def test_student_cannot_leave_hollihop_membership_locally(self):
        classroom = self._create_classroom()
        classroom.hollihop_managed = True
        classroom.hollihop_edunit_id = 9912
        classroom.save(update_fields=["hollihop_managed", "hollihop_edunit_id"])
        membership = ClassroomMembership.objects.create(
            classroom=classroom,
            user=self.student,
            role="student",
            status="approved",
            approved_at=timezone.now(),
            hollihop_managed=True,
        )
        self.client.force_login(self.student)
        response = self.client.post(reverse("leave_classroom", args=[classroom.id]))
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, "approved")

    def test_inactive_classroom_direct_student_access_is_denied(self):
        classroom = self._create_classroom()
        ClassroomMembership.objects.create(
            classroom=classroom, user=self.student, role="student", status="approved", approved_at=timezone.now()
        )
        classroom.is_active = False
        classroom.save(update_fields=["is_active"])
        self.client.force_login(self.student)
        response = self.client.get(reverse("student_classroom_home", args=[classroom.id]))
        self.assertEqual(response.status_code, 403)
