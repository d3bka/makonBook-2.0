from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sat", "0039_test_global_makonbook_availability_semantics")]

    operations = [
        migrations.AddField(model_name="classroom", name="hollihop_edunit_id", field=models.BigIntegerField(blank=True, null=True, unique=True)),
        migrations.AddField(model_name="classroom", name="hollihop_corporative", field=models.BooleanField(blank=True, null=True)),
        migrations.AddField(model_name="classroom", name="hollihop_managed", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="classroom", name="hollihop_last_synced_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="classroommembership", name="hollihop_managed", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="classroommembership", name="hollihop_status", field=models.CharField(blank=True, max_length=30)),
        migrations.AddField(model_name="classroommembership", name="hollihop_last_synced_at", field=models.DateTimeField(blank=True, null=True)),
    ]
