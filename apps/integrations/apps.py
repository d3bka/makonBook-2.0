from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations"
    verbose_name = "Integrations"

    # Intentionally no ready()-time Hollihop sync.
    #
    # A Django process can be started locally, by runserver's autoreloader,
    # Celery, management commands, migrations, health checks, etc. Triggering a
    # remote data import from AppConfig.ready() is therefore unsafe and can
    # duplicate credential delivery or mutate a test database unexpectedly.
    # The initial Hollihop import is explicit from Manager Panel/CLI; periodic
    # smart reconciliation is gated by HollihopSyncState.initial_sync_completed.
