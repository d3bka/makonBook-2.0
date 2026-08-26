from datetime import timedelta
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.integrations.hollihop.client import HollihopConfigurationError, HollihopError
from apps.integrations.hollihop.sync import HollihopSyncAlreadyRunning, HollihopSyncEngine, full_stage_set
from apps.integrations.hollihop.normalization import normalize_phone
from apps.integrations.hollihop.reconcile import mark_initial_sync_completed


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_scope():
    scope = (os.getenv("HOLLIHOP_SYNC_SCOPE", "single") or "single").strip().lower()
    if scope not in {"single", "all"}:
        raise CommandError("HOLLIHOP_SYNC_SCOPE must be 'single' or 'all'.")
    return scope


def _teacher_id_for_phone(engine, phone):
    target = normalize_phone(phone)
    matches = []
    for row in engine.client.get_teachers():
        if normalize_phone(row.get("Mobile") or row.get("Phone")) == target:
            matches.append(row)
    if len(matches) > 1:
        ids = sorted(str(row.get("Id")) for row in matches if row.get("Id") is not None)
        raise ValueError(
            "Multiple Hollihop teachers use HOLLIHOP_SYNC_PHONE; single sync was refused. "
            f"Teacher IDs: {', '.join(ids) or 'unknown'}."
        )
    if not matches:
        return None
    try:
        return int(matches[0].get("Id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Matched Hollihop teacher has an invalid Id.") from exc


class Command(BaseCommand):
    help = "Synchronize Hollihop managers, students, teachers, classrooms, memberships and attendance with MakonBook."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Read Hollihop and report changes without writing anything.")
        parser.add_argument("--all", action="store_true", help="Run every sync stage.")
        parser.add_argument("--managers", action="store_true", help="Sync Hollihop employees whose explicit type/role is configured as admin into the MakonBook Manager group.")
        parser.add_argument("--students", action="store_true")
        parser.add_argument("--teachers", action="store_true")
        parser.add_argument("--classrooms", action="store_true")
        parser.add_argument("--memberships", action="store_true")
        parser.add_argument("--attendance", action="store_true")
        parser.add_argument("--send-credentials", action="store_true", help="Explicitly deliver temporary access to eligible Hollihop-created users.")
        parser.add_argument(
            "--mark-initial",
            action="store_true",
            help="After a successful live --all sync, mark this database as initialized so periodic smart sync may run.",
        )
        parser.add_argument(
            "--pilot-student-phone",
            help="Safely sync exactly one student by normalized phone, plus only that student's teachers/classrooms/membership/recent attendance.",
        )
        parser.add_argument(
            "--pilot-student-id",
            type=int,
            help="Safely sync exactly one Hollihop Client ID, plus only that student's teachers/classrooms/membership/recent attendance.",
        )
        parser.add_argument(
            "--pilot-manager-phone",
            help="Safely sync exactly one manager-eligible Hollihop employee (Admin/Administrator/CEO) by normalized phone.",
        )
        parser.add_argument(
            "--pilot-manager-id",
            type=int,
            help="Safely sync exactly one manager-eligible Hollihop Employee ID.",
        )
        parser.add_argument("--from", dest="date_from", help="Attendance start date YYYY-MM-DD.")
        parser.add_argument("--to", dest="date_to", help="Attendance end date YYYY-MM-DD.")

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        mark_initial = bool(options.get("mark_initial"))
        explicit_send_credentials = bool(options["send_credentials"])
        pilot_phone = (options.get("pilot_student_phone") or "").strip()
        pilot_id = options.get("pilot_student_id")
        pilot_manager_phone = (options.get("pilot_manager_phone") or "").strip()
        pilot_manager_id = options.get("pilot_manager_id")
        pilot_selectors = [
            bool(pilot_phone),
            pilot_id is not None,
            bool(pilot_manager_phone),
            pilot_manager_id is not None,
        ]

        explicit = {
            name for name in ["managers", "students", "teachers", "classrooms", "memberships", "attendance"] if options.get(name)
        }
        using_env_scope = not options["all"] and not explicit and not any(pilot_selectors)
        scope = _env_scope() if using_env_scope else "cli"
        env_single = using_env_scope and scope == "single"
        env_phone = (os.getenv("HOLLIHOP_SYNC_PHONE", "") or "").strip() if env_single else ""

        if env_single and not normalize_phone(env_phone):
            raise CommandError("HOLLIHOP_SYNC_PHONE must contain a valid phone when HOLLIHOP_SYNC_SCOPE=single.")

        pilot_mode = any(pilot_selectors) or env_single
        pilot_kind = (
            "single" if env_single else
            "manager" if (pilot_manager_phone or pilot_manager_id is not None) else
            "student"
        )

        if sum(pilot_selectors) > 1:
            raise CommandError(
                "Use exactly one pilot selector: --pilot-student-phone, --pilot-student-id, "
                "--pilot-manager-phone, or --pilot-manager-id."
            )
        if dry_run and explicit_send_credentials:
            raise CommandError("--send-credentials cannot be used with --dry-run.")
        if mark_initial and dry_run:
            raise CommandError("--mark-initial cannot be used with --dry-run.")
        if mark_initial and (pilot_mode or not options["all"]):
            raise CommandError("--mark-initial requires a live --all sync and cannot be used in pilot mode.")

        send_credentials = explicit_send_credentials
        if using_env_scope and not dry_run:
            send_credentials = send_credentials or _env_bool("HOLLIHOP_SEND_CREDENTIALS", False)
        # Preserve the existing bulk safety gate. The one-student pilot is the
        # only live path allowed while SCHOOL_DATA_PROVIDER remains local.
        if not dry_run and not pilot_mode and (not settings.HOLLIHOP_ENABLED or settings.SCHOOL_DATA_PROVIDER != "hollihop"):
            raise CommandError("Live sync is disabled. Set SCHOOL_DATA_PROVIDER=holihop (or hollihop) and HOLLIHOP_ENABLED=true.")
        if not dry_run and pilot_mode and not settings.HOLLIHOP_ENABLED:
            raise CommandError("HOLLIHOP_ENABLED=true is required for live pilot sync.")
        # The one-student pilot is deliberately allowed while the provider is
        # still local. This lets the school test one account end-to-end without
        # activating webhooks/Celery reconciliation or a bulk import.
        if not settings.HOLLIHOP_API_URL or not settings.HOLLIHOP_AUTH_KEY:
            raise CommandError("HOLLIHOP_API_URL and HOLLIHOP_AUTH_KEY must be configured.")

        if any(pilot_selectors) and (options["all"] or explicit):
            raise CommandError("Pilot mode cannot be combined with --all or stage flags. It already syncs only the target user's required objects.")
        if using_env_scope:
            stages = full_stage_set() if scope == "all" else set()
        else:
            stages = full_stage_set() if options["all"] or not explicit else explicit
        # Memberships depend on both synced users and classrooms during a full run.
        if options["all"]:
            stages = full_stage_set()

        date_from = parse_date(options["date_from"]) if options["date_from"] else None
        date_to = parse_date(options["date_to"]) if options["date_to"] else None
        if options["date_from"] and not date_from:
            raise CommandError("Invalid --from date. Use YYYY-MM-DD.")
        if options["date_to"] and not date_to:
            raise CommandError("Invalid --to date. Use YYYY-MM-DD.")
        if "attendance" in stages or pilot_mode:
            date_to = date_to or timezone.localdate()
            date_from = date_from or (date_to - timedelta(days=settings.HOLLIHOP_RECENT_ATTENDANCE_DAYS - 1))
            if date_from > date_to:
                raise CommandError("--from must be before or equal to --to.")

        self.stdout.write(self.style.MIGRATE_HEADING("Hollihop → MakonBook sync"))
        self.stdout.write(f"Mode: {settings.HOLLIHOP_MODE}")
        self.stdout.write(f"Scope: {scope if using_env_scope else 'CLI override'}")
        self.stdout.write(f"Pilot: {'YES' if pilot_mode else 'NO'}")
        if pilot_kind == "manager":
            pilot_stage_label = "target manager only"
        elif pilot_kind == "single":
            pilot_stage_label = "all Hollihop identities matching HOLLIHOP_SYNC_PHONE + related student objects"
        else:
            pilot_stage_label = "target student + related objects"
        self.stdout.write(f"Stages: {pilot_stage_label if pilot_mode else ', '.join(sorted(stages))}")
        if env_single:
            self.stdout.write(f"Single phone: {normalize_phone(env_phone)}")
        self.stdout.write(f"Dry run: {'YES' if dry_run else 'NO'}")
        self.stdout.write(f"Send credentials: {'YES' if send_credentials else 'NO'}")
        if "attendance" in stages or pilot_mode:
            self.stdout.write(f"Attendance range: {date_from} → {date_to}")

        try:
            engine = HollihopSyncEngine(dry_run=dry_run, send_credentials=send_credentials)
            if env_single:
                found_any = False

                try:
                    manager_id = engine.resolve_manager_employee_id_by_phone(env_phone)
                except ValueError as exc:
                    if not str(exc).startswith("No manager-eligible Hollihop employee"):
                        raise
                    manager_id = None
                if manager_id is not None:
                    found_any = True
                    self.stdout.write(f"Single target: Hollihop Manager Employee #{manager_id}")
                    summary = engine.run_pilot_manager(employee_id=manager_id)

                teacher_id = _teacher_id_for_phone(engine, env_phone)
                if teacher_id is not None:
                    found_any = True
                    self.stdout.write(f"Single target: Hollihop Teacher #{teacher_id}")
                    engine.acquire_lock()
                    try:
                        engine.sync_teachers(only_teacher_id=teacher_id)
                        engine.release_lock(success=engine.summary.errors == 0, partial=engine.summary.errors > 0)
                    except Exception as exc:
                        engine.release_lock(success=False, error=f"{type(exc).__name__}: {str(exc)[:400]}")
                        raise
                    summary = engine.summary

                try:
                    student_id = engine.resolve_student_client_id_by_phone(env_phone)
                except ValueError as exc:
                    if not str(exc).startswith("No Hollihop student was found"):
                        raise
                    student_id = None
                if student_id is not None:
                    found_any = True
                    self.stdout.write(f"Single target: Hollihop Student #{student_id}")
                    summary = engine.run_pilot_student(client_id=student_id, date_from=date_from, date_to=date_to)

                if not found_any:
                    raise ValueError("No Hollihop Student, Teacher, or manager-eligible Employee matches HOLLIHOP_SYNC_PHONE.")
            elif pilot_mode:
                if pilot_kind == "manager":
                    target_id = (
                        pilot_manager_id
                        if pilot_manager_id is not None
                        else engine.resolve_manager_employee_id_by_phone(pilot_manager_phone)
                    )
                    self.stdout.write(f"Pilot target: Hollihop Manager Employee #{target_id}")
                    summary = engine.run_pilot_manager(employee_id=target_id)
                else:
                    target_id = pilot_id if pilot_id is not None else engine.resolve_student_client_id_by_phone(pilot_phone)
                    self.stdout.write(f"Pilot target: Hollihop Student #{target_id}")
                    summary = engine.run_pilot_student(client_id=target_id, date_from=date_from, date_to=date_to)
            else:
                summary = engine.run(stages=stages, date_from=date_from, date_to=date_to)
        except (HollihopConfigurationError, HollihopSyncAlreadyRunning, HollihopError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        if mark_initial:
            if summary.errors:
                raise CommandError("Full sync completed with errors; initial-sync gate was NOT enabled.")
            mark_initial_sync_completed()
            self.stdout.write(self.style.SUCCESS("Initial-sync gate enabled for this database."))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_LABEL("Managers (Hollihop admin employees)"))
        self.stdout.write(f"  Found: {summary.managers_found}")
        self.stdout.write(f"  Existing matched: {summary.managers_matched}")
        self.stdout.write(f"  New: {summary.managers_created}")
        self.stdout.write(f"  Updated: {summary.managers_updated}")
        self.stdout.write(self.style.MIGRATE_LABEL("Students"))
        self.stdout.write(f"  Found: {summary.students_found}")
        self.stdout.write(f"  Existing matched: {summary.students_matched}")
        self.stdout.write(f"  New: {summary.students_created}")
        self.stdout.write(f"  Updated: {summary.students_updated}")
        self.stdout.write(f"  Inactive skipped (no existing account): {summary.students_inactive_skipped}")
        self.stdout.write(self.style.MIGRATE_LABEL("Teachers"))
        self.stdout.write(f"  Found: {summary.teachers_found}")
        self.stdout.write(f"  Existing matched: {summary.teachers_matched}")
        self.stdout.write(f"  New: {summary.teachers_created}")
        self.stdout.write(f"  Updated: {summary.teachers_updated}")
        self.stdout.write(self.style.MIGRATE_LABEL("Classrooms"))
        self.stdout.write(f"  Found: {summary.classrooms_found}")
        self.stdout.write(f"  Created: {summary.classrooms_created}")
        self.stdout.write(f"  Updated: {summary.classrooms_updated}")
        self.stdout.write(self.style.MIGRATE_LABEL("Membership changes"))
        self.stdout.write(f"  Add: {summary.memberships_added}")
        self.stdout.write(f"  Update: {summary.memberships_updated}")
        self.stdout.write(f"  Remove: {summary.memberships_removed}")
        self.stdout.write(self.style.MIGRATE_LABEL("Attendance"))
        self.stdout.write(f"  New: {summary.attendance_created}")
        self.stdout.write(f"  Update: {summary.attendance_updated}")
        self.stdout.write(f"Conflicts: {summary.conflicts}")
        self.stdout.write(f"Errors: {summary.errors}")

        if summary.conflict_details:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Conflicts/manual review:"))
            for item in summary.conflict_details:
                self.stdout.write(
                    f"  {item['external_type']} #{item['external_id']} · {item['display_name']} · "
                    f"{item['reason']} · candidates={item['candidate_user_ids']}"
                )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN complete. Database was not modified."))
        else:
            self.stdout.write(self.style.SUCCESS("Hollihop sync complete."))
