from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="hollihopsyncstate",
            name="initial_sync_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="hollihopsyncstate",
            name="initial_sync_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="hollihopsyncstate",
            name="last_incremental_sync",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="hollihopsyncstate",
            name="cursor_state",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="hollihopsynclog",
            name="event_type",
            field=models.CharField(
                choices=[
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
                ],
                db_index=True,
                max_length=40,
            ),
        ),
    ]
