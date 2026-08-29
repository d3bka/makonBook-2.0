from .settings import *  # noqa: F401,F403

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Keep request/response tests independent from production static serving and
# the custom 500-page renderer.  WhiteNoise is unnecessary in Django's test
# client and would otherwise inspect STATIC_ROOT/manifest state.
_TEST_DISABLED_MIDDLEWARE = {
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.base.middleware.MakonErrorPageMiddleware",
}
MIDDLEWARE = [item for item in MIDDLEWARE if item not in _TEST_DISABLED_MIDDLEWARE]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
