from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, Q
from django.db.migrations.recorder import MigrationRecorder

from apps.base.models import UserProfile
from apps.integrations.models import HollihopSyncState
from apps.sat.models import Classroom, ClassroomJoinCode, ClassroomMembership


class Command(BaseCommand):
    help = "Read-only production audit for classroom schema, permissions, join codes and Hollihop ownership."

    REQUIRED_MIGRATIONS = (
        ("sat", "0040_hollihop_classroom_fields"),
        ("sat", "0041_repair_hollihop_schema_drift"),
        ("base", "0041_hollihop_profile_fields"),
        ("integrations", "0002_hollihop_smart_sync_state"),
    )

    REQUIRED_COLUMNS = {
        Classroom._meta.db_table: {
            "id", "teacher_id", "name", "classroom_type", "is_active",
            "hollihop_edunit_id", "hollihop_corporative", "hollihop_managed", "hollihop_last_synced_at",
        },
        ClassroomMembership._meta.db_table: {
            "id", "classroom_id", "user_id", "role", "status",
            "hollihop_managed", "hollihop_status", "hollihop_last_synced_at",
        },
        ClassroomJoinCode._meta.db_table: {
            "id", "classroom_id", "code", "expires_at", "is_active",
        },
        UserProfile._meta.db_table: {
            "id", "user_id", "middle_name", "phone_number",
            "hollihop_client_id", "hollihop_teacher_id", "hollihop_employee_id",
            "hollihop_status", "hollihop_created", "must_change_password",
            "credentials_delivery_status", "credentials_last_sent_at",
            "hollihop_last_synced_at",
        },
        HollihopSyncState._meta.db_table: {
            "id", "initial_sync_completed", "initial_sync_completed_at",
            "last_incremental_sync", "cursor_state",
        },
    }

    def handle(self, *args, **options):
        problems = []
        warnings = []
        self.stdout.write(self.style.MIGRATE_HEADING("Classroom production audit"))

        self.stdout.write("\nMigrations")
        recorder = MigrationRecorder(connection)
        applied = set(recorder.applied_migrations())
        for app, name in self.REQUIRED_MIGRATIONS:
            ok = (app, name) in applied
            self.stdout.write(f"  {'OK' if ok else 'MISSING'} {app}.{name}")
            if not ok:
                problems.append(f"missing migration {app}.{name}")

        self.stdout.write("\nDatabase schema")
        table_names = set(connection.introspection.table_names())
        with connection.cursor() as cursor:
            for table, required in self.REQUIRED_COLUMNS.items():
                if table not in table_names:
                    self.stdout.write(f"  MISSING table {table}")
                    problems.append(f"missing table {table}")
                    continue
                actual = {col.name for col in connection.introspection.get_table_description(cursor, table)}
                missing = sorted(required - actual)
                if missing:
                    self.stdout.write(f"  MISSING {table}: {', '.join(missing)}")
                    problems.append(f"missing columns in {table}: {', '.join(missing)}")
                else:
                    self.stdout.write(f"  OK {table}")

        # Do not query models if schema is known incomplete; that could itself
        # throw the exact production error this command is intended to diagnose.
        if problems:
            self.stdout.write("\nResult")
            raise CommandError("Classroom audit failed: " + "; ".join(problems))

        self.stdout.write("\nData / permissions")
        duplicate_memberships = list(
            ClassroomMembership.objects.values("classroom_id", "user_id")
            .annotate(n=Count("id")).filter(n__gt=1)[:20]
        )
        self.stdout.write(f"  duplicate classroom memberships: {len(duplicate_memberships)}")
        if duplicate_memberships:
            problems.append("duplicate classroom memberships exist")

        # Role/membership integrity is actionable only for active classrooms.
        # Historical classrooms are intentionally kept after a Hollihop teacher is
        # fired/deactivated; the sync correctly removes the Teacher group while
        # preserving the classroom and its memberships for history/reporting.
        active_classrooms = Classroom.objects.filter(is_active=True)
        inactive_classrooms = Classroom.objects.filter(is_active=False)

        active_owner_without_teacher = active_classrooms.exclude(
            Q(teacher__groups__name__iexact="Teacher") | Q(teacher__is_superuser=True)
        ).distinct().count()
        self.stdout.write(
            f"  active classroom owners without Teacher group: {active_owner_without_teacher}"
        )
        if active_owner_without_teacher:
            warnings.append(
                f"{active_owner_without_teacher} active classroom owners lack authoritative Teacher role"
            )

        archived_owner_without_teacher = inactive_classrooms.exclude(
            Q(teacher__groups__name__iexact="Teacher") | Q(teacher__is_superuser=True)
        ).distinct().count()
        self.stdout.write(
            "  inactive/archive classroom owners without Teacher group: "
            f"{archived_owner_without_teacher} (informational)"
        )

        missing_owner_membership = 0
        for classroom in active_classrooms.only("id", "teacher_id").iterator(chunk_size=500):
            if not ClassroomMembership.objects.filter(
                classroom_id=classroom.id,
                user_id=classroom.teacher_id,
                role="teacher",
                status="approved",
            ).exists():
                missing_owner_membership += 1
        self.stdout.write(
            f"  active owners missing approved teacher membership: {missing_owner_membership}"
        )
        if missing_owner_membership:
            warnings.append(
                f"{missing_owner_membership} active classroom owners lack approved teacher membership"
            )

        malformed_codes = 0
        for code in ClassroomJoinCode.objects.values_list("code", flat=True).iterator(chunk_size=500):
            if not (isinstance(code, str) and len(code) == 6 and code.isdigit()):
                malformed_codes += 1
        self.stdout.write(f"  malformed join codes: {malformed_codes}")
        if malformed_codes:
            problems.append("malformed classroom join codes exist")

        inactive_with_code = ClassroomJoinCode.objects.filter(
            is_active=True, classroom__is_active=False
        ).count()
        self.stdout.write(f"  inactive classrooms with active join code: {inactive_with_code}")
        if inactive_with_code:
            warnings.append(f"{inactive_with_code} inactive classrooms still have active join codes")

        hollihop_with_code = ClassroomJoinCode.objects.filter(
            is_active=True, classroom__hollihop_managed=True
        ).count()
        self.stdout.write(f"  Hollihop classrooms with active manual join code: {hollihop_with_code}")
        if hollihop_with_code:
            problems.append("Hollihop-managed classrooms have active manual join codes")

        manual_pending_hollihop = ClassroomMembership.objects.filter(
            classroom__hollihop_managed=True,
            role="student",
            status="pending",
            hollihop_managed=False,
        ).count()
        self.stdout.write(f"  manual pending requests inside Hollihop classrooms: {manual_pending_hollihop}")
        if manual_pending_hollihop:
            warnings.append(f"{manual_pending_hollihop} manual pending requests exist inside Hollihop classrooms")

        hollihop_membership_manual_classroom = ClassroomMembership.objects.filter(
            hollihop_managed=True,
            classroom__hollihop_managed=False,
        ).count()
        self.stdout.write(f"  Hollihop-managed memberships inside manual classrooms: {hollihop_membership_manual_classroom}")
        if hollihop_membership_manual_classroom:
            problems.append("Hollihop-managed memberships exist inside manual classrooms")

        self.stdout.write("\nResult")
        for warning in warnings:
            self.stdout.write(self.style.WARNING("  WARNING " + warning))
        if problems:
            raise CommandError("Classroom audit failed: " + "; ".join(problems))
        self.stdout.write(self.style.SUCCESS("  OK - no critical classroom integrity problems detected."))
