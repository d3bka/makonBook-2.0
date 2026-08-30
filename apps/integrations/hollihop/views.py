from __future__ import annotations

import secrets
from collections import Counter

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from apps.integrations.models import (
    HollihopAttendance,
    HollihopCredentialDelivery,
    HollihopSyncConflict,
    HollihopSyncLog,
    HollihopSyncState,
)
from apps.sat.models import Classroom
from apps.sat.roles import can_manage_classroom, is_manager, is_platform_admin

from .credentials import deliver_new_temporary_access
from .tasks import (
    manual_full_hollihop_reconciliation,
    manual_initial_hollihop_sync,
    manual_membership_hollihop_sync,
    manual_smart_hollihop_sync,
    process_student_webhook,
    sync_resolved_classroom_mapping,
)

User = get_user_model()


def _manager_allowed(user):
    return bool(user.is_authenticated and (is_manager(user) or is_platform_admin(user)))


def _sync_precheck(request):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    if not settings.HOLLIHOP_ENABLED or settings.SCHOOL_DATA_PROVIDER != "hollihop":
        messages.error(request, "Hollihop is disabled. Set SCHOOL_DATA_PROVIDER=hollihop and restart the app first.")
        return redirect("hollihop_dashboard")
    if not settings.HOLLIHOP_API_URL or not settings.HOLLIHOP_AUTH_KEY:
        messages.error(request, "Hollihop API URL/auth key are not configured.")
        return redirect("hollihop_dashboard")
    state = HollihopSyncState.objects.filter(provider="hollihop").first()
    if state and state.lock_token and state.lock_expires_at and state.lock_expires_at > timezone.now():
        messages.warning(request, "A Hollihop synchronization is already running.")
        return redirect("hollihop_dashboard")
    return None


def integration_dashboard(request):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    state = HollihopSyncState.objects.filter(provider="hollihop").first()
    conflicts = HollihopSyncConflict.objects.filter(status=HollihopSyncConflict.STATUS_PENDING).order_by("-updated_at")[:30]
    failed_deliveries = HollihopCredentialDelivery.objects.filter(
        overall_status__in=["failed", "partial", "no_contact"]
    ).select_related("user", "user__profile")[:30]
    recent_logs = HollihopSyncLog.objects.select_related("user", "classroom")[:50]
    delivery_qs = HollihopCredentialDelivery.objects.all()
    delivery_counts = Counter(delivery_qs.values_list("overall_status", flat=True))
    delivery_channel_counts = {
        "email_sms": delivery_qs.filter(email_status="sent", sms_status="sent").count(),
        "email_only": delivery_qs.filter(email_status="sent", sms_status="not_available").count(),
        "sms_only": delivery_qs.filter(email_status="not_available", sms_status="sent").count(),
        "failed": delivery_qs.filter(overall_status__in=["failed", "no_contact"]).count(),
    }
    teacher_choices = (
        User.objects
        .filter(Q(profile__hollihop_teacher_id__isnull=False) | Q(groups__name="Teacher"))
        .distinct()
        .order_by("first_name", "last_name", "username")
    )
    context = {
        "provider": settings.SCHOOL_DATA_PROVIDER,
        "enabled": settings.HOLLIHOP_ENABLED,
        "mode": settings.HOLLIHOP_MODE,
        "allowed_learning_types": ", ".join(settings.HOLLIHOP_ALLOWED_LEARNING_TYPES) or "ALL",
        "sync_interval_minutes": settings.HOLLIHOP_SYNC_INTERVAL_MINUTES,
        "teacher_poll_minutes": settings.HOLLIHOP_TEACHER_POLL_MINUTES,
        "manager_poll_minutes": settings.HOLLIHOP_MANAGER_POLL_MINUTES,
        "membership_sweep_minutes": settings.HOLLIHOP_MEMBERSHIP_SWEEP_MINUTES,
        "student_profile_sweep_minutes": settings.HOLLIHOP_STUDENT_PROFILE_SWEEP_MINUTES,
        "edunit_catalog_sweep_minutes": settings.HOLLIHOP_EDUNIT_CATALOG_SWEEP_MINUTES,
        "configured": bool(settings.HOLLIHOP_API_URL and settings.HOLLIHOP_AUTH_KEY),
        "webhook_configured": bool(settings.HOLLIHOP_WEBHOOK_SECRET),
        "state": state,
        "initial_sync_completed": bool(state and state.initial_sync_completed),
        "students_count": User.objects.filter(profile__hollihop_client_id__isnull=False).count(),
        "teachers_count": User.objects.filter(profile__hollihop_teacher_id__isnull=False).count(),
        "managers_count": User.objects.filter(profile__hollihop_employee_id__isnull=False, groups__name="Manager").distinct().count(),
        "classrooms_count": Classroom.objects.filter(hollihop_edunit_id__isnull=False).count(),
        "attendance_count": HollihopAttendance.objects.count(),
        "conflicts_count": HollihopSyncConflict.objects.filter(status="pending").count(),
        "conflicts": conflicts,
        "failed_deliveries": failed_deliveries,
        "recent_logs": recent_logs,
        "delivery_counts": delivery_counts,
        "delivery_channel_counts": delivery_channel_counts,
        "credentials_auto_send": settings.HOLLIHOP_AUTO_SEND_CREDENTIALS,
        "sms_provider": getattr(settings, "MAKONBOOK_SMS_PROVIDER", "disabled"),
        "teacher_choices": teacher_choices,
    }
    return render(request, "integrations/hollihop/dashboard.html", context)


@require_POST
def initial_sync(request):
    precheck = _sync_precheck(request)
    if precheck:
        return precheck
    state = HollihopSyncState.objects.filter(provider="hollihop").first()
    if state and state.initial_sync_completed:
        messages.warning(request, "Initial sync is already completed for this database. Use Full reconciliation if you really need a complete re-check.")
        return redirect("hollihop_dashboard")
    if request.POST.get("confirm") != "INITIAL":
        messages.error(request, "Initial synchronization confirmation is missing.")
        return redirect("hollihop_dashboard")
    # Prevent double-clicks / two browser tabs from queueing two expensive first
    # imports before the Celery worker has had time to acquire the DB lock.
    try:
        queued = cache.add("hollihop:initial-sync-queued", 1, timeout=30 * 60)
    except Exception:
        queued = True  # DB lock in the worker remains the second line of defence.
    if not queued:
        messages.warning(request, "Initial Hollihop synchronization is already queued or running.")
        return redirect("hollihop_dashboard")
    try:
        manual_initial_hollihop_sync.delay()
        messages.success(request, "Initial Hollihop import was queued. Automatic 5-minute smart sync will remain disabled until this import finishes successfully.")
    except Exception:
        try:
            cache.delete("hollihop:initial-sync-queued")
        except Exception:
            pass
        messages.error(request, "Background worker is unavailable. Run: python manage.py sync_hollihop --all --mark-initial")
    return redirect("hollihop_dashboard")


@require_POST
def smart_sync_now(request):
    precheck = _sync_precheck(request)
    if precheck:
        return precheck
    state = HollihopSyncState.objects.filter(provider="hollihop").first()
    if not state or not state.initial_sync_completed:
        messages.warning(request, "Run the Initial sync first. Smart synchronization is intentionally gated for local/test safety.")
        return redirect("hollihop_dashboard")
    try:
        manual_smart_hollihop_sync.delay()
        messages.success(request, "Lightweight Hollihop update check was queued.")
    except Exception:
        messages.error(request, "Background worker is unavailable.")
    return redirect("hollihop_dashboard")


@require_POST
def membership_sync_now(request):
    precheck = _sync_precheck(request)
    if precheck:
        return precheck
    state = HollihopSyncState.objects.filter(provider="hollihop").first()
    if not state or not state.initial_sync_completed:
        messages.warning(request, "Run the Initial sync first.")
        return redirect("hollihop_dashboard")
    if request.POST.get("confirm") != "MEMBERSHIPS":
        messages.error(request, "Membership reconciliation confirmation is missing.")
        return redirect("hollihop_dashboard")
    try:
        manual_membership_hollihop_sync.delay()
        messages.success(request, "Relation-only Hollihop membership reconciliation was queued (Days/payments are not requested).")
    except Exception:
        messages.error(request, "Background worker is unavailable.")
    return redirect("hollihop_dashboard")


@require_POST
def full_reconciliation(request):
    precheck = _sync_precheck(request)
    if precheck:
        return precheck
    state = HollihopSyncState.objects.filter(provider="hollihop").first()
    if not state or not state.initial_sync_completed:
        messages.warning(request, "Run the Initial sync first.")
        return redirect("hollihop_dashboard")
    if request.POST.get("confirm") != "FULL":
        messages.error(request, "Full reconciliation confirmation is missing.")
        return redirect("hollihop_dashboard")
    try:
        manual_full_hollihop_reconciliation.delay()
        messages.success(request, "Full Hollihop reconciliation was queued. This is manual only and is never run on app startup.")
    except Exception:
        messages.error(request, "Background worker is unavailable. Run: python manage.py sync_hollihop --all")
    return redirect("hollihop_dashboard")


@require_POST
def sync_now(request):
    """Backward-compatible action used by older templates/bookmarks."""
    state = HollihopSyncState.objects.filter(provider="hollihop").first()
    if state and state.initial_sync_completed:
        return smart_sync_now(request)
    # Old button did not include the new explicit confirmation; do not silently
    # start a full import. Redirect with a clear instruction instead.
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    messages.warning(request, "Initial synchronization now requires the explicit Initial sync button for safety.")
    return redirect("hollihop_dashboard")


@require_POST
def resend_credentials(request, user_id):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    if request.POST.get("confirm") != "RESET":
        messages.error(request, "Confirmation missing. Password was not reset.")
        return redirect("hollihop_dashboard")
    user = get_object_or_404(User.objects.select_related("profile"), id=user_id)
    profile = user.profile
    if not (profile.hollihop_client_id or profile.hollihop_teacher_id or profile.hollihop_employee_id):
        messages.error(request, "This user is not linked to Hollihop.")
        return redirect("hollihop_dashboard")
    delivery = deliver_new_temporary_access(user)
    if delivery.overall_status == "sent":
        messages.success(request, "A new temporary password was generated and delivered.")
    else:
        messages.warning(request, f"Password was reset, but delivery status is {delivery.get_overall_status_display().lower()}.")
    return redirect("hollihop_dashboard")


@require_POST
def resolve_conflict(request, conflict_id):
    if not _manager_allowed(request.user):
        return HttpResponseForbidden("Manager access required.")
    conflict = get_object_or_404(HollihopSyncConflict, id=conflict_id, status="pending")
    action = request.POST.get("action")
    if action == "ignore":
        conflict.status = "ignored"
        conflict.save(update_fields=["status", "updated_at"])
        messages.success(request, "Conflict marked as ignored.")
        return redirect("hollihop_dashboard")
    if conflict.external_type not in {"student", "teacher", "manager", "classroom"}:
        messages.error(request, "This conflict type cannot be linked from the dashboard.")
        return redirect("hollihop_dashboard")
    try:
        user_id = int(request.POST.get("user_id") or 0)
    except ValueError:
        user_id = 0
    user = User.objects.filter(id=user_id).select_related("profile").first()
    if not user:
        messages.error(request, "Select a valid MakonBook user.")
        return redirect("hollihop_dashboard")

    if conflict.external_type == "classroom":
        is_teacher_user = bool(
            user.profile.hollihop_teacher_id is not None
            or user.groups.filter(name__in=["Teacher", "Support Teacher"]).exists()
            or user.is_staff
            or user.is_superuser
        )
        if not is_teacher_user:
            messages.error(request, "For a classroom conflict, select a MakonBook teacher user.")
            return redirect("hollihop_dashboard")
        conflict.status = HollihopSyncConflict.STATUS_RESOLVED
        conflict.resolved_user = user
        conflict.save(update_fields=["status", "resolved_user", "updated_at"])
        try:
            sync_resolved_classroom_mapping.delay(int(conflict.external_id))
            messages.success(request, "Classroom teacher mapping saved. A targeted Hollihop membership sync was queued for this EdUnit.")
        except Exception:
            messages.warning(request, "Classroom teacher mapping saved. It will be applied on the next membership reconciliation.")
        return redirect("hollihop_dashboard")

    field = {
        "student": "hollihop_client_id",
        "teacher": "hollihop_teacher_id",
        "manager": "hollihop_employee_id",
    }[conflict.external_type]
    external_id = int(conflict.external_id)
    if User.objects.filter(**{f"profile__{field}": external_id}).exclude(id=user.id).exists():
        messages.error(request, "That Hollihop ID is already linked to another user.")
        return redirect("hollihop_dashboard")
    setattr(user.profile, field, external_id)
    user.profile.save(update_fields=[field, "updated_at"])
    conflict.status = "resolved"
    conflict.resolved_user = user
    conflict.save(update_fields=["status", "resolved_user", "updated_at"])
    messages.success(request, "Hollihop object linked. The next sync will refresh the user's fields.")
    return redirect("hollihop_dashboard")


def my_attendance(request):
    if not request.user.is_authenticated:
        return redirect("login")
    records = HollihopAttendance.objects.filter(student=request.user).select_related("classroom")[:120]
    totals = HollihopAttendance.objects.filter(student=request.user).aggregate(
        total=Count("id"), present=Count("id", filter=Q(status="present")), absent=Count("id", filter=Q(status="absent"))
    )
    total = totals["total"] or 0
    totals["percentage"] = round((totals["present"] or 0) * 100 / total, 1) if total else None
    return render(request, "integrations/hollihop/my_attendance.html", {"records": records, "totals": totals})


def classroom_attendance(request, classroom_id):
    if not request.user.is_authenticated:
        return redirect("login")
    classroom = get_object_or_404(Classroom, id=classroom_id)
    if not (_manager_allowed(request.user) or can_manage_classroom(request.user, classroom)):
        return HttpResponseForbidden("You do not have access to this classroom attendance.")
    records = HollihopAttendance.objects.filter(classroom=classroom).select_related("student")[:300]
    return render(request, "integrations/hollihop/classroom_attendance.html", {"classroom": classroom, "records": records})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if not settings.HOLLIHOP_ENABLED or settings.SCHOOL_DATA_PROVIDER != "hollihop":
        return JsonResponse({"Error": "Hollihop integration is disabled."}, status=503)
    expected = settings.HOLLIHOP_WEBHOOK_SECRET
    supplied = request.POST.get("key") or request.GET.get("key") or ""
    if not expected or not secrets.compare_digest(str(expected), str(supplied)):
        return JsonResponse({"Error": "Unauthorized."}, status=403)

    remote_ip = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "unknown") or "unknown"
    rate_key = f"hollihop:webhook-rate:{remote_ip}"
    try:
        count = cache.get(rate_key, 0)
        if count >= settings.HOLLIHOP_WEBHOOK_RATE_LIMIT:
            return JsonResponse({"Error": "Rate limit exceeded."}, status=429)
        if count == 0:
            cache.set(rate_key, 1, timeout=60)
        else:
            try:
                cache.incr(rate_key)
            except ValueError:
                cache.set(rate_key, count + 1, timeout=60)
    except Exception:
        return JsonResponse({"Error": "Webhook temporarily unavailable."}, status=503)

    trigger_type = request.POST.get("TriggerType") or request.GET.get("TriggerType") or ""
    object_type = request.POST.get("ObjectType") or request.GET.get("ObjectType") or ""
    object_id = request.POST.get("ObjectId") or request.GET.get("ObjectId") or ""
    allowed_triggers = {"Created", "StatusSet", "PassSet"}
    if object_type != "StudentClient" or trigger_type not in allowed_triggers:
        return JsonResponse({"ok": True, "ignored": True})
    try:
        client_id = int(object_id)
    except (TypeError, ValueError):
        return JsonResponse({"Error": "Invalid ObjectId."}, status=400)

    HollihopSyncLog.objects.create(
        event_type="webhook_received", entity_type="student", external_id=str(client_id),
        details={"trigger_type": trigger_type, "object_type": object_type},
    )
    try:
        process_student_webhook.delay(trigger_type, client_id)
    except Exception:
        process_student_webhook.apply(args=[trigger_type, client_id])
    return JsonResponse({"ok": True})
