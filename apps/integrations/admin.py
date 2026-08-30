from django.contrib import admin

from .models import HollihopAttendance, HollihopCredentialDelivery, HollihopSyncConflict, HollihopSyncLog, HollihopSyncState


@admin.register(HollihopSyncState)
class HollihopSyncStateAdmin(admin.ModelAdmin):
    list_display = ("provider", "initial_sync_completed", "last_status", "last_attempt", "last_successful_sync", "last_incremental_sync", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(HollihopSyncLog)
class HollihopSyncLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "entity_type", "external_id", "user", "classroom", "created_at")
    list_filter = ("event_type", "entity_type")
    search_fields = ("external_id", "user__username", "user__email", "classroom__name")
    readonly_fields = ("created_at",)


@admin.register(HollihopSyncConflict)
class HollihopSyncConflictAdmin(admin.ModelAdmin):
    list_display = ("external_type", "external_id", "display_name", "status", "updated_at")
    list_filter = ("external_type", "status")
    search_fields = ("external_id", "display_name", "normalized_email", "normalized_phone")


@admin.register(HollihopAttendance)
class HollihopAttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "classroom", "date", "status", "accepted", "updated_at")
    list_filter = ("status", "accepted", "date")
    search_fields = ("student__username", "student__email", "classroom__name", "external_key")


@admin.register(HollihopCredentialDelivery)
class HollihopCredentialDeliveryAdmin(admin.ModelAdmin):
    list_display = ("user", "overall_status", "email_status", "sms_status", "created_at", "completed_at")
    list_filter = ("overall_status", "email_status", "sms_status")
    search_fields = ("user__username", "user__email")
