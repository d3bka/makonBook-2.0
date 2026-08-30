from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("base", "0040_generalissuereport_context_data")]

    operations = [
        migrations.AddField(model_name="userprofile", name="middle_name", field=models.CharField(blank=True, max_length=150)),
        migrations.AddField(model_name="userprofile", name="phone_number", field=models.CharField(blank=True, max_length=32, null=True, unique=True)),
        migrations.AddField(model_name="userprofile", name="hollihop_client_id", field=models.BigIntegerField(blank=True, null=True, unique=True)),
        migrations.AddField(model_name="userprofile", name="hollihop_teacher_id", field=models.BigIntegerField(blank=True, null=True, unique=True)),
        migrations.AddField(model_name="userprofile", name="hollihop_employee_id", field=models.BigIntegerField(blank=True, null=True, unique=True)),
        migrations.AddField(model_name="userprofile", name="hollihop_status", field=models.CharField(blank=True, max_length=150)),
        migrations.AddField(model_name="userprofile", name="hollihop_created", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="userprofile", name="must_change_password", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="userprofile", name="credentials_delivery_status", field=models.CharField(db_index=True, default="not_applicable", max_length=30)),
        migrations.AddField(model_name="userprofile", name="credentials_last_sent_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="userprofile", name="hollihop_last_synced_at", field=models.DateTimeField(blank=True, null=True)),
    ]
