from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class HollihopSyncState(models.Model):
    STATUS_IDLE = "idle"
    STATUS_SYNCING = "syncing"
    STATUS_SUCCESS = "success"
    STATUS_PARTIAL = "partial"
    STATUS_ERROR = "error"
    STATUS_DISABLED = "disabled"
    STATUS_CHOICES = [
        (STATUS_IDLE, "Idle"),
        (STATUS_SYNCING, "Syncing"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_PARTIAL, "Partial failure"),
        (STATUS_ERROR, "Error"),
        (STATUS_DISABLED, "Disabled"),
    ]

    provider = models.CharField(max_length=30, default="hollihop", unique=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_successful_sync = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IDLE)
    last_error_safe = models.CharField(max_length=500, blank=True)
    students_synced = models.PositiveIntegerField(default=0)
    teachers_synced = models.PositiveIntegerField(default=0)
    managers_synced = models.PositiveIntegerField(default=0)
    classrooms_synced = models.PositiveIntegerField(default=0)
    memberships_synced = models.PositiveIntegerField(default=0)
    attendance_synced = models.PositiveIntegerField(default=0)
    lock_token = models.UUIDField(null=True, blank=True, editable=False)
    lock_expires_at = models.DateTimeField(null=True, blank=True)

    # The first full Hollihop import is always explicit. Celery's periodic smart
    # reconciliation is a no-op until this flag is set by a successful manual
    # full synchronization. This makes local testing safe even when Celery Beat
    # is running against the same Hollihop tenant.
    initial_sync_completed = models.BooleanField(default=False)
    initial_sync_completed_at = models.DateTimeField(null=True, blank=True)
    last_incremental_sync = models.DateTimeField(null=True, blank=True)
    # Flexible persistent checkpoints/cursors for API deltas and low-frequency
    # safety sweeps. Stored as ISO timestamps / primitive values only.
    cursor_state = models.JSONField(default=dict, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Hollihop sync ({self.last_status})"


class HollihopSyncLog(models.Model):
    EVENT_CHOICES = [
        ("student_created", "Student created"),
        ("student_updated", "Student updated"),
        ("student_deactivated", "Student deactivated"),
        ("student_reactivated", "Student reactivated"),
        ("teacher_created", "Teacher created"),
        ("teacher_updated", "Teacher updated"),
        ("teacher_deactivated", "Teacher deactivated"),
        ("teacher_reactivated", "Teacher reactivated"),
        ("manager_created", "Manager created"),
        ("manager_updated", "Manager updated"),
        ("manager_deactivated", "Manager deactivated"),
        ("manager_reactivated", "Manager reactivated"),
        ("classroom_created", "Classroom created"),
        ("classroom_updated", "Classroom updated"),
        ("membership_added", "Membership added"),
        ("membership_removed", "Membership removed"),
        ("attendance_created", "Attendance created"),
        ("attendance_updated", "Attendance updated"),
        ("credentials_email_sent", "Credentials email sent"),
        ("credentials_sms_sent", "Credentials SMS sent"),
        ("sync_conflict", "Sync conflict"),
        ("sync_error", "Sync error"),
        ("webhook_received", "Webhook received"),
        ("smart_sync", "Smart sync cycle"),
        ("initial_sync_completed", "Initial sync completed"),
    ]
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES, db_index=True)
    entity_type = models.CharField(max_length=30, blank=True, db_index=True)
    external_id = models.CharField(max_length=100, blank=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="hollihop_sync_logs")
    classroom = models.ForeignKey("sat.Classroom", null=True, blank=True, on_delete=models.SET_NULL, related_name="hollihop_sync_logs")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["event_type", "created_at"], name="holli_log_type_date")]


class HollihopSyncConflict(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RESOLVED = "resolved"
    STATUS_IGNORED = "ignored"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_RESOLVED, "Resolved"), (STATUS_IGNORED, "Ignored")]

    external_type = models.CharField(max_length=30)
    external_id = models.CharField(max_length=100)
    display_name = models.CharField(max_length=255, blank=True)
    normalized_email = models.EmailField(blank=True)
    normalized_phone = models.CharField(max_length=32, blank=True)
    reason = models.CharField(max_length=500)
    candidate_user_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    resolved_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolved_hollihop_conflicts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["external_type", "external_id"], name="uniq_holli_conflict_object")]


class HollihopAttendance(models.Model):
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_CHOICES = [(STATUS_PRESENT, "Present"), (STATUS_ABSENT, "Absent")]

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hollihop_attendance")
    classroom = models.ForeignKey("sat.Classroom", on_delete=models.CASCADE, related_name="hollihop_attendance")
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    description = models.CharField(max_length=1000, blank=True)
    accepted = models.BooleanField(null=True, blank=True)
    schedule_key = models.CharField(max_length=200, blank=True)
    external_key = models.CharField(max_length=300, unique=True)
    source = models.CharField(max_length=30, default="hollihop")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["student", "date"], name="holli_att_student_date"),
            models.Index(fields=["classroom", "date"], name="holli_att_class_date"),
        ]


class HollihopCredentialDelivery(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"
    STATUS_NO_CONTACT = "no_contact"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_PARTIAL, "Partially sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_NO_CONTACT, "No contact"),
    ]
    CHANNEL_CHOICES = [
        ("not_available", "Not available"),
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hollihop_credential_deliveries")
    overall_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    email_status = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="not_available")
    sms_status = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="not_available")
    email_error_safe = models.CharField(max_length=300, blank=True)
    sms_error_safe = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
