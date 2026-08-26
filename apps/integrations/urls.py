from django.urls import path

from .hollihop import views

urlpatterns = [
    path("hollihop/", views.integration_dashboard, name="hollihop_dashboard"),
    path("hollihop/sync-now/", views.sync_now, name="hollihop_sync_now"),
    path("hollihop/sync-initial/", views.initial_sync, name="hollihop_initial_sync"),
    path("hollihop/sync-smart/", views.smart_sync_now, name="hollihop_smart_sync"),
    path("hollihop/sync-memberships/", views.membership_sync_now, name="hollihop_membership_sync"),
    path("hollihop/sync-full/", views.full_reconciliation, name="hollihop_full_reconciliation"),
    path("hollihop/resend/<int:user_id>/", views.resend_credentials, name="hollihop_resend_credentials"),
    path("hollihop/conflict/<int:conflict_id>/resolve/", views.resolve_conflict, name="hollihop_resolve_conflict"),
    path("hollihop/my-attendance/", views.my_attendance, name="hollihop_my_attendance"),
    path("hollihop/classroom/<int:classroom_id>/attendance/", views.classroom_attendance, name="hollihop_classroom_attendance"),
    path("hollihop/webhook/", views.webhook, name="hollihop_webhook"),
]
