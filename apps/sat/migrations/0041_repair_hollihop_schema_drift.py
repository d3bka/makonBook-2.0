"""Repair databases where Hollihop migrations are recorded as applied but columns are absent.

This is intentionally idempotent.  It only adds columns that are physically missing and
has no destructive reverse operation.  The migration state already contains these fields
from sat.0040/base.0041/integrations.0002; this migration repairs database state only.
"""

from django.db import migrations


FIELD_GROUPS = (
    (
        "sat",
        "Classroom",
        (
            "hollihop_edunit_id",
            "hollihop_corporative",
            "hollihop_managed",
            "hollihop_last_synced_at",
        ),
    ),
    (
        "sat",
        "ClassroomMembership",
        (
            "hollihop_managed",
            "hollihop_status",
            "hollihop_last_synced_at",
        ),
    ),
    (
        "base",
        "UserProfile",
        (
            "middle_name",
            "phone_number",
            "hollihop_client_id",
            "hollihop_teacher_id",
            "hollihop_employee_id",
            "hollihop_status",
            "hollihop_created",
            "must_change_password",
            "credentials_delivery_status",
            "credentials_last_sent_at",
            "hollihop_last_synced_at",
        ),
    ),
    (
        "integrations",
        "HollihopSyncState",
        (
            "initial_sync_completed",
            "initial_sync_completed_at",
            "last_incremental_sync",
            "cursor_state",
        ),
    ),
)


def _column_names(schema_editor, table_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }


def repair_missing_columns(apps, schema_editor):
    connection = schema_editor.connection
    existing_tables = set(connection.introspection.table_names())

    for app_label, model_name, field_names in FIELD_GROUPS:
        model = apps.get_model(app_label, model_name)
        table_name = model._meta.db_table
        if table_name not in existing_tables:
            raise RuntimeError(
                f"Cannot repair Hollihop schema: required table {table_name!r} does not exist."
            )

        existing_columns = _column_names(schema_editor, table_name)
        for field_name in field_names:
            field = model._meta.get_field(field_name)
            if field.column in existing_columns:
                continue
            schema_editor.add_field(model, field)
            existing_columns.add(field.column)


class Migration(migrations.Migration):
    dependencies = [
        ("sat", "0040_hollihop_classroom_fields"),
        ("base", "0041_hollihop_profile_fields"),
        ("integrations", "0002_hollihop_smart_sync_state"),
    ]

    operations = [
        migrations.RunPython(repair_missing_columns, migrations.RunPython.noop),
    ]
