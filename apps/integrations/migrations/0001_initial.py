from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("base", "0041_hollihop_profile_fields"),
        ("sat", "0040_hollihop_classroom_fields"),
    ]
    operations = [
        migrations.CreateModel(
            name="HollihopSyncState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="hollihop", max_length=30, unique=True)),
                ("last_attempt", models.DateTimeField(blank=True, null=True)),
                ("last_successful_sync", models.DateTimeField(blank=True, null=True)),
                ("last_status", models.CharField(choices=[("idle", "Idle"), ("syncing", "Syncing"), ("success", "Success"), ("partial", "Partial failure"), ("error", "Error"), ("disabled", "Disabled")], default="idle", max_length=20)),
                ("last_error_safe", models.CharField(blank=True, max_length=500)),
                ("students_synced", models.PositiveIntegerField(default=0)),
                ("teachers_synced", models.PositiveIntegerField(default=0)),
                ("managers_synced", models.PositiveIntegerField(default=0)),
                ("classrooms_synced", models.PositiveIntegerField(default=0)),
                ("memberships_synced", models.PositiveIntegerField(default=0)),
                ("attendance_synced", models.PositiveIntegerField(default=0)),
                ("lock_token", models.UUIDField(blank=True, editable=False, null=True)),
                ("lock_expires_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="HollihopSyncConflict",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_type", models.CharField(max_length=30)),
                ("external_id", models.CharField(max_length=100)),
                ("display_name", models.CharField(blank=True, max_length=255)),
                ("normalized_email", models.EmailField(blank=True, max_length=254)),
                ("normalized_phone", models.CharField(blank=True, max_length=32)),
                ("reason", models.CharField(max_length=500)),
                ("candidate_user_ids", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("resolved", "Resolved"), ("ignored", "Ignored")], db_index=True, default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resolved_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_hollihop_conflicts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddConstraint(model_name="hollihopsyncconflict", constraint=models.UniqueConstraint(fields=("external_type", "external_id"), name="uniq_holli_conflict_object")),
        migrations.CreateModel(
            name="HollihopAttendance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True)),
                ("status", models.CharField(choices=[("present", "Present"), ("absent", "Absent")], max_length=10)),
                ("description", models.CharField(blank=True, max_length=1000)),
                ("accepted", models.BooleanField(blank=True, null=True)),
                ("schedule_key", models.CharField(blank=True, max_length=200)),
                ("external_key", models.CharField(max_length=300, unique=True)),
                ("source", models.CharField(default="hollihop", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("classroom", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hollihop_attendance", to="sat.classroom")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hollihop_attendance", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.AddIndex(model_name="hollihopattendance", index=models.Index(fields=["student", "date"], name="holli_att_student_date")),
        migrations.AddIndex(model_name="hollihopattendance", index=models.Index(fields=["classroom", "date"], name="holli_att_class_date")),
        migrations.CreateModel(
            name="HollihopCredentialDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("overall_status", models.CharField(choices=[("pending", "Pending"), ("sent", "Sent"), ("partial", "Partially sent"), ("failed", "Failed"), ("no_contact", "No contact")], db_index=True, default="pending", max_length=20)),
                ("email_status", models.CharField(choices=[("not_available", "Not available"), ("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")], default="not_available", max_length=20)),
                ("sms_status", models.CharField(choices=[("not_available", "Not available"), ("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")], default="not_available", max_length=20)),
                ("email_error_safe", models.CharField(blank=True, max_length=300)),
                ("sms_error_safe", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hollihop_credential_deliveries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="HollihopSyncLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("student_created", "Student created"), ("student_updated", "Student updated"), ("student_deactivated", "Student deactivated"), ("student_reactivated", "Student reactivated"), ("teacher_created", "Teacher created"), ("teacher_updated", "Teacher updated"), ("teacher_deactivated", "Teacher deactivated"), ("teacher_reactivated", "Teacher reactivated"), ("manager_created", "Manager created"), ("manager_updated", "Manager updated"), ("manager_deactivated", "Manager deactivated"), ("manager_reactivated", "Manager reactivated"), ("classroom_created", "Classroom created"), ("classroom_updated", "Classroom updated"), ("membership_added", "Membership added"), ("membership_removed", "Membership removed"), ("attendance_created", "Attendance created"), ("attendance_updated", "Attendance updated"), ("credentials_email_sent", "Credentials email sent"), ("credentials_sms_sent", "Credentials SMS sent"), ("sync_conflict", "Sync conflict"), ("sync_error", "Sync error"), ("webhook_received", "Webhook received")], db_index=True, max_length=40)),
                ("entity_type", models.CharField(blank=True, db_index=True, max_length=30)),
                ("external_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("classroom", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hollihop_sync_logs", to="sat.classroom")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hollihop_sync_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="hollihopsynclog", index=models.Index(fields=["event_type", "created_at"], name="holli_log_type_date")),
    ]
