#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # The test suite must not depend on production-only services such as
    # hashed static manifests or remote media storage.  A dedicated Django
    # settings module already exists for that purpose, so make ``manage.py
    # test`` use it automatically.  Other management commands keep the
    # normal application settings unchanged.
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        os.environ["DJANGO_SETTINGS_MODULE"] = os.environ.get(
            "DJANGO_TEST_SETTINGS_MODULE",
            "satmakon.test_settings",
        )
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satmakon.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
