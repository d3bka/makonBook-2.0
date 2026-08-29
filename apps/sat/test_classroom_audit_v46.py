from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.sat.models import Classroom, ClassroomMembership


class ClassroomProductionAuditV46Tests(TestCase):
    def _run_audit(self):
        out = StringIO()
        call_command("check_classroom_system", stdout=out)
        return out.getvalue()

    def test_inactive_archived_owner_without_teacher_role_is_informational_only(self):
        former_teacher = User.objects.create_user(
            username="former_hollihop_teacher_v46",
            password="pass12345",
            is_active=False,
        )
        Classroom.objects.create(
            teacher=former_teacher,
            name="Archived Hollihop classroom",
            is_active=False,
            hollihop_managed=True,
            hollihop_edunit_id=46001,
        )

        output = self._run_audit()

        self.assertIn("active classroom owners without Teacher group: 0", output)
        self.assertIn(
            "inactive/archive classroom owners without Teacher group: 1 (informational)",
            output,
        )
        self.assertNotIn(
            "WARNING 1 active classroom owners lack authoritative Teacher role",
            output,
        )

    def test_active_owner_without_teacher_role_remains_a_warning(self):
        owner = User.objects.create_user(username="active_non_teacher_v46", password="pass12345")
        classroom = Classroom.objects.create(
            teacher=owner,
            name="Active classroom without Teacher group",
            is_active=True,
        )
        ClassroomMembership.objects.create(
            classroom=classroom,
            user=owner,
            role="teacher",
            status="approved",
            approved_at=timezone.now(),
        )

        output = self._run_audit()

        self.assertIn("active classroom owners without Teacher group: 1", output)
        self.assertIn(
            "WARNING 1 active classroom owners lack authoritative Teacher role",
            output,
        )

    def test_active_owner_missing_membership_remains_a_warning(self):
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        owner = User.objects.create_user(username="teacher_without_membership_v46", password="pass12345")
        owner.groups.add(teacher_group)
        Classroom.objects.create(
            teacher=owner,
            name="Active classroom without owner membership",
            is_active=True,
        )

        output = self._run_audit()

        self.assertIn("active owners missing approved teacher membership: 1", output)
        self.assertIn(
            "WARNING 1 active classroom owners lack approved teacher membership",
            output,
        )
