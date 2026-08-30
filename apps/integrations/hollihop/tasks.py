from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.base.models import UserProfile
from apps.integrations.models import HollihopSyncLog, HollihopSyncState

from .reconcile import HollihopSmartReconciler, mark_initial_sync_completed
from .sync import HollihopSyncAlreadyRunning, HollihopSyncEngine, full_stage_set


def _integration_enabled():
    return bool(settings.HOLLIHOP_ENABLED and settings.SCHOOL_DATA_PROVIDER == "hollihop")


def _initial_sync_ready():
    state = HollihopSyncState.objects.filter(provider="hollihop").only("initial_sync_completed").first()
    return bool(state and state.initial_sync_completed)


def _new_engine(*, send_credentials=None):
    if send_credentials is None:
        send_credentials = settings.HOLLIHOP_AUTO_SEND_CREDENTIALS
    return HollihopSyncEngine(send_credentials=bool(send_credentials))


@shared_task(name="apps.integrations.hollihop.tasks.smart_reconcile_hollihop")
def smart_reconcile_hollihop():
    """Five-minute low-load reconciliation.

    The task is intentionally inert until a manager completes the explicit
    initial/full synchronization in this database. That makes local runserver,
    local Celery and production safe to use against the same Hollihop account.
    """
    if not _integration_enabled():
        return {"status": "disabled"}
    reconciler = HollihopSmartReconciler()
    report, summary = reconciler.run(require_initial=True)
    return {**report.as_dict(), **summary.as_dict()}


# Backwards-compatible task names from earlier patches. They now point to the
# same safe smart reconciliation instead of running a full account export.
@shared_task(name="apps.integrations.hollihop.tasks.reconcile_hollihop_core")
def reconcile_hollihop_core():
    return smart_reconcile_hollihop()


@shared_task(name="apps.integrations.hollihop.tasks.reconcile_hollihop")
def reconcile_hollihop():
    return smart_reconcile_hollihop()


@shared_task(name="apps.integrations.hollihop.tasks.manual_hollihop_sync")
def manual_hollihop_sync(
    stages=None,
    date_from=None,
    date_to=None,
    send_credentials=False,
    mark_initial=False,
):
    """Explicit full/staged synchronization started by Manager/CLI.

    `send_credentials` defaults to False on purpose. The user's Eskiz account is
    currently in test mode, and a data sync must never unexpectedly send or
    rotate credentials for thousands of users.
    """
    if not _integration_enabled():
        return {"status": "disabled"}
    engine = _new_engine(send_credentials=send_credentials)
    try:
        summary = engine.run(stages=set(stages or full_stage_set()), date_from=date_from, date_to=date_to)
    except HollihopSyncAlreadyRunning:
        return {"status": "busy"}

    if mark_initial and summary.errors == 0:
        state = mark_initial_sync_completed()
        HollihopSyncLog.objects.create(
            event_type="initial_sync_completed",
            entity_type="sync",
            details={"state_id": state.id, **summary.as_dict()},
        )
    return {"status": "ok" if summary.errors == 0 else "partial", **summary.as_dict()}


@shared_task(name="apps.integrations.hollihop.tasks.manual_initial_hollihop_sync")
def manual_initial_hollihop_sync():
    """One explicit initial import; no credential delivery."""
    try:
        return manual_hollihop_sync(
            list(full_stage_set()),
            send_credentials=False,
            mark_initial=True,
        )
    finally:
        try:
            cache.delete("hollihop:initial-sync-queued")
        except Exception:
            pass


@shared_task(name="apps.integrations.hollihop.tasks.manual_full_hollihop_reconciliation")
def manual_full_hollihop_reconciliation():
    """Explicit safety reconciliation after initial setup; never automatic."""
    if not _initial_sync_ready():
        return {"status": "awaiting_initial_sync"}
    return manual_hollihop_sync(
        list(full_stage_set()),
        send_credentials=False,
        mark_initial=False,
    )


@shared_task(name="apps.integrations.hollihop.tasks.manual_smart_hollihop_sync")
def manual_smart_hollihop_sync():
    if not _integration_enabled():
        return {"status": "disabled"}
    reconciler = HollihopSmartReconciler()
    report, summary = reconciler.run(require_initial=True)
    return {**report.as_dict(), **summary.as_dict()}


@shared_task(name="apps.integrations.hollihop.tasks.manual_membership_hollihop_sync")
def manual_membership_hollihop_sync():
    """Explicit relation-only membership sweep (no Days/payments)."""
    if not _integration_enabled():
        return {"status": "disabled"}
    if not _initial_sync_ready():
        return {"status": "awaiting_initial_sync"}
    engine = _new_engine(send_credentials=False)
    try:
        engine.acquire_lock()
    except HollihopSyncAlreadyRunning:
        return {"status": "busy"}
    try:
        relations = engine.client.get_ed_unit_students(
            corporative=engine.corporative_filter,
            query_days=False,
        )
        engine.sync_memberships(relations=relations, ensure_dependencies=True)
        engine.release_lock(success=engine.summary.errors == 0, partial=engine.summary.errors > 0)
        return {"status": "ok", **engine.summary.as_dict()}
    except Exception as exc:
        engine.release_lock(success=False, error=type(exc).__name__)
        raise




@shared_task(name="apps.integrations.hollihop.tasks.sync_resolved_classroom_mapping")
def sync_resolved_classroom_mapping(edunit_id):
    """Apply one manager-resolved Classroom -> Teacher mapping immediately."""
    if not _integration_enabled():
        return {"status": "disabled"}
    if not _initial_sync_ready():
        return {"status": "awaiting_initial_sync"}
    engine = _new_engine(send_credentials=False)
    try:
        engine.acquire_lock()
    except HollihopSyncAlreadyRunning:
        return {"status": "busy"}
    try:
        engine.sync_memberships(
            only_edunit_id=int(edunit_id),
            ensure_dependencies=True,
        )
        engine.release_lock(success=engine.summary.errors == 0, partial=engine.summary.errors > 0)
        return {"status": "ok", **engine.summary.as_dict()}
    except Exception as exc:
        engine.release_lock(success=False, error=type(exc).__name__)
        raise


@shared_task(name="apps.integrations.hollihop.tasks.process_student_webhook")
def process_student_webhook(trigger_type, client_id, attempt=0):
    if not _integration_enabled():
        return {"status": "disabled"}
    # Webhooks must not bootstrap an uninitialized local/test database. The
    # explicit initial import is the only operation allowed to cross that gate.
    if not _initial_sync_ready():
        return {"status": "awaiting_initial_sync"}

    engine = _new_engine()
    try:
        engine.acquire_lock()
    except HollihopSyncAlreadyRunning:
        # Do not silently lose an event just because a long initial/manual sync
        # owns the lock. Student membership changes are not represented by
        # EdUnit.lastUpdated, so queue a few bounded retries in addition to the
        # periodic reconciliation safety net.
        attempt = int(attempt or 0)
        if attempt < 5:
            process_student_webhook.apply_async(
                args=[trigger_type, client_id, attempt + 1],
                countdown=min(300, 60 * (attempt + 1)),
            )
            return {"status": "retry_queued", "attempt": attempt + 1}
        return {"status": "busy", "attempt": attempt}

    try:
        client_id = int(client_id)
        rows = engine.client.get_students(client_id=client_id)
        relations = engine._filter_relations_to_active_edunits(
            engine.client.get_ed_unit_students(
                student_client_id=client_id,
                corporative=engine.corporative_filter,
                query_days=False,
            ),
            require_active_student=False,
        )
        existing = UserProfile.objects.filter(hollihop_client_id=client_id).exists()
        if rows and (relations or existing):
            # Existing users continue receiving contact/status changes after
            # leaving their last GROUP. Only unknown ONLINE/no-GROUP users are
            # prevented from bootstrapping a new MakonBook account.
            engine.summary.students_found += 1
            with transaction.atomic():
                engine._sync_student(rows[0])
        if relations or existing:
            engine.sync_memberships(
                only_student_client_id=client_id,
                relations=relations,
                ensure_dependencies=True,
            )

        if str(trigger_type) == "PassSet":
            engine.sync_attendance(
                date_from=timezone.localdate() - timedelta(days=settings.HOLLIHOP_ATTENDANCE_DELTA_DAYS - 1),
                date_to=timezone.localdate(),
                only_student_client_id=client_id,
            )
        engine.release_lock(success=engine.summary.errors == 0, partial=engine.summary.errors > 0)
        return {"status": "ok", **engine.summary.as_dict()}
    except Exception as exc:
        engine.release_lock(success=False, error=type(exc).__name__)
        raise
