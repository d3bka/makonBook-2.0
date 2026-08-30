from pathlib import Path
import os
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
dotenv_path = BASE_DIR / '.env'
load_dotenv(dotenv_path)



def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    config_path = BASE_DIR / "satmakon" / "config.ini"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as file:
            SECRET_KEY = file.readline().strip()
    else:
        raise RuntimeError("SECRET_KEY env var not set and config.ini not found")


DEBUG = env_bool("DEBUG", False)

# Keep the canonical production hosts available even when an older .env is
# accidentally mounted during deployment. A stale host/origin list causes
# valid authenticated POST requests to fail before they reach the view.
_CANONICAL_ALLOWED_HOSTS = [
    "makonbook.uz",
    "www.makonbook.uz",
    "makonbook.satmakon.com",
    "makonbook-sat.ondigitalocean.app",
    "127.0.0.1",
    "localhost",
]
ALLOWED_HOSTS = list(dict.fromkeys(
    env_list("ALLOWED_HOSTS") + _CANONICAL_ALLOWED_HOSTS
))

_CANONICAL_CSRF_ORIGINS = [
    "https://makonbook.uz",
    "https://www.makonbook.uz",
    "https://makonbook.satmakon.com",
    "https://makonbook-sat.ondigitalocean.app",
]
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
    env_list("CSRF_TRUSTED_ORIGINS") + _CANONICAL_CSRF_ORIGINS
))
# The one hostname search engines and social-card scrapers should see. The app
# answers on several names, so sitemap.xml, robots.txt and the og: tags all
# build their absolute URLs from this rather than from the request host --
# otherwise every alias advertises itself as a separate copy of the site.
SITE_DOMAIN = env_str("SITE_DOMAIN", "makonbook.uz")
SITE_PROTOCOL = env_str("SITE_PROTOCOL", "http" if DEBUG else "https")
SITE_URL = f"{SITE_PROTOCOL}://{SITE_DOMAIN}"


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "storages",

    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    "apps.base.apps.BaseConfig",
    "apps.sat.apps.SatConfig",
    "apps.apclasses.apps.ApClassesConfig",
    "apps.ratings.apps.RatingsConfig",
    "apps.integrations.apps.IntegrationsConfig",
    "apps.telegram_bot",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.base.middleware.MakonErrorPageMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.base.middleware.TemporaryPasswordChangeMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.sat.middleware.ClientSoftwareMiddleware",
    "apps.sat.middleware.RequestTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "satmakon.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.base.context_processors.site_meta",
                "apps.base.context_processors.test_import_meta",
            ],
        },
    },
]

WSGI_APPLICATION = "satmakon.wsgi.application"


def database_from_url(db_url: str) -> dict:
    parsed = urlparse(db_url)
    scheme = parsed.scheme.lower()

    if scheme in ("postgres", "postgresql", "pgsql"):
        engine = "django.db.backends.postgresql"
    elif scheme in ("sqlite", "sqlite3"):
        engine = "django.db.backends.sqlite3"
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")

    if engine == "django.db.backends.sqlite3":
        db_name = parsed.path.lstrip("/") or str(BASE_DIR / "db.sqlite3")
        return {
            "ENGINE": engine,
            "NAME": db_name,
        }

    query = parse_qs(parsed.query)
    options = {}

    if "sslmode" in query:
        options["sslmode"] = query["sslmode"][0]
    elif not DEBUG:
        options["sslmode"] = os.getenv("DB_SSLMODE", "require")

    db_config = {
        "ENGINE": engine,
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "600")),
    }

    if options:
        db_config["OPTIONS"] = options

    return db_config


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": database_from_url(DATABASE_URL)
    }
else:
    DB_ENGINE = os.getenv("DB_ENGINE", "django.db.backends.sqlite3")

    if DB_ENGINE == "django.db.backends.postgresql":
        db_options = {}
        db_sslmode = os.getenv("DB_SSLMODE", "").strip()
        if db_sslmode:
            db_options["sslmode"] = db_sslmode
        elif not DEBUG:
            db_options["sslmode"] = "require"

        DATABASES = {
            "default": {
                "ENGINE": os.getenv("DB_ENGINE"),
                "NAME": os.getenv("DB_NAME"),
                "USER": os.getenv("DB_USER"),
                "PASSWORD": os.getenv("DB_PASSWORD"),
                "HOST": os.getenv("DB_HOST"),
                "PORT": os.getenv("DB_PORT"),
                "CONN_MAX_AGE": 0,
                "CONN_HEALTH_CHECKS": True,
                "OPTIONS": db_options,
            }
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = []
project_static_dir = BASE_DIR / "static"
if project_static_dir.exists():
    STATICFILES_DIRS.append(project_static_dir)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email settings for verification/password reset codes
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env_str("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", env_str("EMAIL_PASSWORD", ""))
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "webmaster@localhost")
SERVER_EMAIL = env_str("SERVER_EMAIL", DEFAULT_FROM_EMAIL)


# File upload and request size limits for test submissions
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
DATA_UPLOAD_MAX_NUMBER_FILES = 100
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MBs

# Request timeout settings
REQUEST_TIMEOUT = 60  # seconds

# Public registration throttling. These defaults are intentionally tolerant of
# school NATs while still stopping repeated automated submissions.
REGISTRATION_RATE_LIMIT_ENABLED = env_bool("REGISTRATION_RATE_LIMIT_ENABLED", True)
REGISTRATION_RATE_LIMIT_IP_MAX = int(os.getenv("REGISTRATION_RATE_LIMIT_IP_MAX", "20"))
REGISTRATION_RATE_LIMIT_IP_WINDOW_SECONDS = int(os.getenv("REGISTRATION_RATE_LIMIT_IP_WINDOW_SECONDS", "600"))
REGISTRATION_RATE_LIMIT_IDENTIFIER_MAX = int(os.getenv("REGISTRATION_RATE_LIMIT_IDENTIFIER_MAX", "5"))
REGISTRATION_RATE_LIMIT_IDENTIFIER_WINDOW_SECONDS = int(os.getenv("REGISTRATION_RATE_LIMIT_IDENTIFIER_WINDOW_SECONDS", "1800"))

# Test Import Center upload/queue throttling. The short cooldown is primarily
# an idempotency guard against double-clicks; the wider window protects the
# expensive upload + background-audit pipeline from repeated requests.
TEST_IMPORT_RATE_LIMIT_ENABLED = env_bool("TEST_IMPORT_RATE_LIMIT_ENABLED", True)
TEST_IMPORT_SUBMIT_COOLDOWN_SECONDS = int(os.getenv("TEST_IMPORT_SUBMIT_COOLDOWN_SECONDS", "15"))
TEST_IMPORT_RATE_LIMIT_MAX = int(os.getenv("TEST_IMPORT_RATE_LIMIT_MAX", "6"))
TEST_IMPORT_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("TEST_IMPORT_RATE_LIMIT_WINDOW_SECONDS", "600"))

# Classroom join-code throttling. Per-user limits stop brute force without
# locking an entire school behind one NAT/public IP.
CLASSROOM_JOIN_USER_MAX_ATTEMPTS = max(3, int(os.getenv("CLASSROOM_JOIN_USER_MAX_ATTEMPTS", "10")))
CLASSROOM_JOIN_IP_MAX_ATTEMPTS = max(20, int(os.getenv("CLASSROOM_JOIN_IP_MAX_ATTEMPTS", "100")))
CLASSROOM_JOIN_RATE_WINDOW_SECONDS = max(60, int(os.getenv("CLASSROOM_JOIN_RATE_WINDOW_SECONDS", "600")))

# Shared Redis counters in production; zero-setup in-memory counters in local
# DEBUG mode. Set REGISTRATION_RATE_LIMIT_CACHE_URL explicitly to use Redis
# while running Django directly from a local virtualenv.
REGISTRATION_RATE_LIMIT_CACHE_URL = os.getenv("REGISTRATION_RATE_LIMIT_CACHE_URL", "").strip()
if REGISTRATION_RATE_LIMIT_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REGISTRATION_RATE_LIMIT_CACHE_URL,
            "KEY_PREFIX": "makonbook",
        }
    }
elif DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "makonbook-dev",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            # MakonBook production currently runs without Docker. Override
            # REGISTRATION_RATE_LIMIT_CACHE_URL when Redis is remote.
            "LOCATION": os.getenv("MAKONBOOK_CACHE_URL", "redis://127.0.0.1:6379/3"),
            "KEY_PREFIX": "makonbook",
        }
    }


# Logging configuration for monitoring large requests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'apps.sat.middleware': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}


SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# v35 deliberately uses a new cookie name. Browsers can retain an old host-only
# and an old domain-wide ``csrftoken`` at the same time; Django may then receive
# the wrong value and reject an otherwise valid form. A versioned name starts
# with one unambiguous cookie without weakening CSRF protection.
CSRF_COOKIE_NAME = env_str("CSRF_COOKIE_NAME", "makonbook_csrftoken_v35")
CSRF_COOKIE_PATH = "/"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = env_str("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SAMESITE = env_str("SESSION_COOKIE_SAMESITE", "Lax")

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)

SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)


R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")

AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
AWS_S3_ENDPOINT_URL = R2_ENDPOINT_URL
AWS_S3_REGION_NAME = os.getenv("R2_REGION", "auto")

AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "virtual"
AWS_S3_USE_SSL = True
AWS_S3_VERIFY = True
AWS_S3_CUSTOM_DOMAIN = os.getenv(
    "AWS_S3_CUSTOM_DOMAIN",
    "pub-2967bfd7582a441fa07820ea020c1616.r2.dev"
)
AWS_S3_URL_PROTOCOL = "https:"
AWS_QUERYSTRING_AUTH = False
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False

STORAGES = {
    "default": {
        "BACKEND": "apps.sat.storages.PublicStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

PRIVATE_MEDIA_STORAGE = "apps.sat.storages.PrivateStorage"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if not DEBUG else "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = 'sat_menu'
LOGOUT_REDIRECT_URL = '/login/'

AUTHENTICATION_BACKENDS = [
    "apps.base.auth_backends.EmailOrPhoneModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = int(os.getenv("SITE_ID", "1"))

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/sat/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/login/"

ACCOUNT_EMAIL_VERIFICATION = "none"
# ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]

SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"

GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "VERIFIED_EMAIL": True,
        "EMAIL_AUTHENTICATION": True,
        "EMAIL_AUTHENTICATION_AUTO_CONNECT": True,
        "APPS": [
            {
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "key": "",
                "settings": {
                    "scope": ["profile", "email"],
                    "auth_params": {"access_type": "online"},
                },
            }
        ],
        "OAUTH_PKCE_ENABLED": True,
    }
}


# Hollihop administrative-data integration.
# `holihop` is accepted as an alias because it is commonly typed that way.
SCHOOL_DATA_PROVIDER = env_str("SCHOOL_DATA_PROVIDER", "local").lower()
if SCHOOL_DATA_PROVIDER == "holihop":
    SCHOOL_DATA_PROVIDER = "hollihop"
if SCHOOL_DATA_PROVIDER not in {"local", "hollihop"}:
    raise RuntimeError("SCHOOL_DATA_PROVIDER must be local, holihop, or hollihop.")

HOLLIHOP_MODE = env_str("HOLLIHOP_MODE", "users").lower()
if HOLLIHOP_MODE not in {"users", "corporative", "all"}:
    raise RuntimeError("HOLLIHOP_MODE must be users, corporative, or all.")
HOLLIHOP_ENABLED = env_bool("HOLLIHOP_ENABLED", True)
HOLLIHOP_API_URL = env_str("HOLLIHOP_API_URL", "")
HOLLIHOP_AUTH_KEY = env_str("HOLLIHOP_AUTH_KEY", "")
HOLLIHOP_WEBHOOK_SECRET = env_str("HOLLIHOP_WEBHOOK_SECRET", "")
HOLLIHOP_TIMEOUT_SECONDS = max(3, int(os.getenv("HOLLIHOP_TIMEOUT_SECONDS", "20")))
HOLLIHOP_MAX_RETRIES = max(0, min(5, int(os.getenv("HOLLIHOP_MAX_RETRIES", "3"))))
HOLLIHOP_PAGE_SIZE = max(1, min(10000, int(os.getenv("HOLLIHOP_PAGE_SIZE", "1000"))))
HOLLIHOP_MAX_PAGES = max(5, min(1000, int(os.getenv("HOLLIHOP_MAX_PAGES", "100"))))
# Hollihop support reported a hard limit of 600 requests / 30 seconds. 0.10s
# keeps one MakonBook sync worker comfortably below that ceiling, including
# targeted dependency fetches after a delta is discovered.
HOLLIHOP_MIN_REQUEST_INTERVAL = max(0.05, float(os.getenv("HOLLIHOP_MIN_REQUEST_INTERVAL", "0.20")))
HOLLIHOP_RECENT_ATTENDANCE_DAYS = max(1, int(os.getenv("HOLLIHOP_RECENT_ATTENDANCE_DAYS", "30")))
HOLLIHOP_ATTENDANCE_CHUNK_DAYS = max(1, min(90, int(os.getenv("HOLLIHOP_ATTENDANCE_CHUNK_DAYS", "30"))))
HOLLIHOP_SYNC_LOCK_MINUTES = max(5, int(os.getenv("HOLLIHOP_SYNC_LOCK_MINUTES", "30")))
HOLLIHOP_WEBHOOK_RATE_LIMIT = max(10, int(os.getenv("HOLLIHOP_WEBHOOK_RATE_LIMIT", "120")))

# Smart reconciliation. There is deliberately NO sync-on-startup. The first
# import is started explicitly from Manager Panel; only after it succeeds does
# the lightweight 5-minute reconciliation become active for that database.
HOLLIHOP_SYNC_INTERVAL_MINUTES = max(1, int(os.getenv("HOLLIHOP_SYNC_INTERVAL_MINUTES", "5")))
HOLLIHOP_TEACHER_POLL_MINUTES = max(5, int(os.getenv("HOLLIHOP_TEACHER_POLL_MINUTES", "5")))
HOLLIHOP_MANAGER_POLL_MINUTES = max(10, int(os.getenv("HOLLIHOP_MANAGER_POLL_MINUTES", "15")))
# GetEdUnitStudents is Hollihop's heavy endpoint. The automatic full relation
# sweep is intentionally limited to several times/day and always queryDays=False.
HOLLIHOP_MEMBERSHIP_SWEEP_MINUTES = max(60, int(os.getenv("HOLLIHOP_MEMBERSHIP_SWEEP_MINUTES", "360")))
HOLLIHOP_STUDENT_PROFILE_SWEEP_MINUTES = max(120, int(os.getenv("HOLLIHOP_STUDENT_PROFILE_SWEEP_MINUTES", "360")))
HOLLIHOP_EDUNIT_CATALOG_SWEEP_MINUTES = max(120, int(os.getenv("HOLLIHOP_EDUNIT_CATALOG_SWEEP_MINUTES", "360")))
HOLLIHOP_ATTENDANCE_DELTA_DAYS = max(1, min(30, int(os.getenv("HOLLIHOP_ATTENDANCE_DELTA_DAYS", "7"))))
HOLLIHOP_ATTENDANCE_SWEEP_MINUTES = max(360, int(os.getenv("HOLLIHOP_ATTENDANCE_SWEEP_MINUTES", "1440")))
HOLLIHOP_CHECKPOINT_OVERLAP_SECONDS = max(0, min(600, int(os.getenv("HOLLIHOP_CHECKPOINT_OVERLAP_SECONDS", "120"))))
# Full-sweep deletion circuit breaker. A truncated Hollihop response must not
# mass-remove otherwise valid classroom memberships.
HOLLIHOP_MAX_AUTOMATIC_MEMBERSHIP_REMOVALS = max(1, int(os.getenv("HOLLIHOP_MAX_AUTOMATIC_MEMBERSHIP_REMOVALS", "500")))
HOLLIHOP_MAX_AUTOMATIC_MEMBERSHIP_REMOVAL_RATIO = max(0.01, min(1.0, float(os.getenv("HOLLIHOP_MAX_AUTOMATIC_MEMBERSHIP_REMOVAL_RATIO", "0.35"))))
HOLLIHOP_MEMBERSHIP_REMOVAL_GUARD_MIN_POPULATION = max(1, int(os.getenv("HOLLIHOP_MEMBERSHIP_REMOVAL_GUARD_MIN_POPULATION", "50")))

# Data synchronization and credential delivery are intentionally separated.
# Keep the automatic gate false while Eskiz is in test mode.
HOLLIHOP_SEND_CREDENTIALS = env_bool("HOLLIHOP_SEND_CREDENTIALS", False)
HOLLIHOP_AUTO_SEND_CREDENTIALS = env_bool("HOLLIHOP_AUTO_SEND_CREDENTIALS", False)

# Hollihop LearningType is separate from Type=Group/MiniGroup. Only ordinary
# GROUP units enter MakonBook; ONLINE / IV ONLINE / IV OFFLINE are ignored.
HOLLIHOP_ALLOWED_LEARNING_TYPES = tuple(env_list("HOLLIHOP_ALLOWED_LEARNING_TYPES", "GROUP"))

# Backwards-compatible names for older settings/schedules. They no longer imply
# an automatic full reconciliation; the beat normalization below removes legacy
# Hollihop schedule entries and installs only the smart task.
HOLLIHOP_RECONCILE_MINUTES = HOLLIHOP_SYNC_INTERVAL_MINUTES
HOLLIHOP_FULL_RECONCILE_MINUTES = max(60, int(os.getenv("HOLLIHOP_FULL_RECONCILE_MINUTES", "360")))
HOLLIHOP_CLASSROOM_TYPE = env_str("HOLLIHOP_CLASSROOM_TYPE", "sat").lower()
if HOLLIHOP_CLASSROOM_TYPE not in {"sat", "ap"}:
    raise RuntimeError("HOLLIHOP_CLASSROOM_TYPE must be sat or ap.")
HOLLIHOP_FALLBACK_TEACHER_USERNAME = env_str("HOLLIHOP_FALLBACK_TEACHER_USERNAME", "")
# GetEmployees does not document a dedicated permission field, so MakonBook
# accepts the commonly returned role/type/position fields and only promotes
# employees matching these explicit markers. This avoids making every employee
# a Manager. Override the list if your Hollihop tenant uses a custom label.
HOLLIHOP_MANAGER_TYPES = {
    item.casefold() for item in env_list(
        "HOLLIHOP_MANAGER_TYPES",
        "Admin,Administrator,CEO,Chief Executive Officer,Админ,Администратор",
    )
}
HOLLIHOP_ACTIVE_STUDENT_STATUSES = {
    item.casefold() for item in env_list("HOLLIHOP_ACTIVE_STUDENT_STATUSES", "Занимается,Active,Working")
}
HOLLIHOP_INACTIVE_STUDENT_STATUSES = {
    item.casefold() for item in env_list(
        "HOLLIHOP_INACTIVE_STUDENT_STATUSES",
        "Inactive,Archived,Stopped studying,Не занимается,Архив,Закончил обучение",
    )
}

# SMS provider abstraction. Keep disabled until the provider account, sender and
# operator-approved templates are ready. Supported: disabled, generic_http, eskiz.
MAKONBOOK_SMS_PROVIDER = env_str("MAKONBOOK_SMS_PROVIDER", "disabled").lower()
MAKONBOOK_SMS_API_URL = env_str("MAKONBOOK_SMS_API_URL", "")
MAKONBOOK_SMS_API_TOKEN = env_str("MAKONBOOK_SMS_API_TOKEN", "")
MAKONBOOK_SMS_SENDER = env_str("MAKONBOOK_SMS_SENDER", "MakonBook")
MAKONBOOK_SMS_TIMEOUT_SECONDS = max(3, int(os.getenv("MAKONBOOK_SMS_TIMEOUT_SECONDS", "15")))

# Native Eskiz.uz adapter. Credentials stay in environment variables only.
ESKIZ_API_BASE_URL = env_str("ESKIZ_API_BASE_URL", "https://notify.eskiz.uz/api").rstrip("/")
ESKIZ_AUTH_URL = env_str("ESKIZ_AUTH_URL", f"{ESKIZ_API_BASE_URL}/auth/login")
ESKIZ_SEND_URL = env_str("ESKIZ_SEND_URL", f"{ESKIZ_API_BASE_URL}/message/sms/send")
ESKIZ_EMAIL = env_str("ESKIZ_EMAIL", "")
ESKIZ_PASSWORD = env_str("ESKIZ_PASSWORD", "")
ESKIZ_SENDER = env_str("ESKIZ_SENDER", "4546")
ESKIZ_CALLBACK_URL = env_str("ESKIZ_CALLBACK_URL", "")
# Shared Django cache (Redis in production) prevents authenticating before each SMS.
# A 6-hour cache is deliberately conservative; HTTP 401 triggers one forced refresh.
ESKIZ_TOKEN_CACHE_SECONDS = max(60, int(os.getenv("ESKIZ_TOKEN_CACHE_SECONDS", "21600")))

# Celery / Redis remain available for unrelated background tasks (for example video conversion).
# Structured Test Import does NOT enqueue Celery jobs and does not require Redis.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_RESULT_EXPIRES = int(os.getenv("CELERY_RESULT_EXPIRES", "86400"))
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

CELERY_BEAT_SCHEDULE = {
    "hollihop-periodic-reconciliation": {
        "task": "apps.integrations.hollihop.tasks.reconcile_hollihop",
        "schedule": HOLLIHOP_RECONCILE_MINUTES * 60.0,
    },
}

# BEGIN MAKONBOOK HOLLIHOP SMART BEAT
# Preserve unrelated Celery Beat jobs, remove only legacy Hollihop schedules,
# then install the single low-load smart reconciliation task.
for _hollihop_beat_key in list(CELERY_BEAT_SCHEDULE):
    if _hollihop_beat_key.startswith("hollihop-"):
        CELERY_BEAT_SCHEDULE.pop(_hollihop_beat_key, None)
CELERY_BEAT_SCHEDULE["hollihop-smart-reconciliation"] = {
    "task": "apps.integrations.hollihop.tasks.smart_reconcile_hollihop",
    "schedule": HOLLIHOP_SYNC_INTERVAL_MINUTES * 60.0,
}
# END MAKONBOOK HOLLIHOP SMART BEAT

# AI is used for administrator/manager-run question-bank audits.
# Structured-PDF imports themselves are deterministic and do not require an AI provider.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Prefer DeepSeek automatically when its key is configured; set QUESTION_AUDIT_PROVIDER explicitly to override.
QUESTION_AUDIT_PROVIDER = os.getenv(
    "QUESTION_AUDIT_PROVIDER",
    "deepseek" if DEEPSEEK_API_KEY else "openai",
).strip().lower()
_default_question_audit_model = "deepseek-v4-flash" if QUESTION_AUDIT_PROVIDER == "deepseek" else "gpt-5.6-terra"
QUESTION_AUDIT_MODEL = os.getenv("QUESTION_AUDIT_MODEL", _default_question_audit_model).strip()
# Ignore stale model names when switching providers (for example an old gpt-* value in .env).
if QUESTION_AUDIT_PROVIDER == "deepseek" and not QUESTION_AUDIT_MODEL.startswith("deepseek-"):
    QUESTION_AUDIT_MODEL = "deepseek-v4-flash"
elif QUESTION_AUDIT_PROVIDER == "openai" and QUESTION_AUDIT_MODEL.startswith("deepseek-"):
    QUESTION_AUDIT_MODEL = "gpt-5.6-terra"
QUESTION_AUDIT_TIMEOUT_SECONDS = int(os.getenv("QUESTION_AUDIT_TIMEOUT_SECONDS", "90"))
QUESTION_AUDIT_BATCH_SIZE = max(1, min(30, int(os.getenv("QUESTION_AUDIT_BATCH_SIZE", "12"))))
QUESTION_AUDIT_MAX_TOKENS = max(1000, int(os.getenv("QUESTION_AUDIT_MAX_TOKENS", "12000")))
QUESTION_AUDIT_JSON_RETRIES = max(1, min(4, int(os.getenv("QUESTION_AUDIT_JSON_RETRIES", "2"))))
QUESTION_AUDIT_DEEPSEEK_THINKING = os.getenv("QUESTION_AUDIT_DEEPSEEK_THINKING", "0").strip().lower() in {"1", "true", "yes", "on"}
QUESTION_AUDIT_DEEPSEEK_REASONING_EFFORT = os.getenv("QUESTION_AUDIT_DEEPSEEK_REASONING_EFFORT", "low")

# Legacy arbitrary-PDF AI extraction remains OpenAI-only for old import records.
# New MakonBook Structured PDF v1/v2 imports never call TEST_IMPORT_MODEL.
TEST_IMPORT_MODEL = os.getenv("TEST_IMPORT_MODEL", "gpt-5.6-terra")
TEST_IMPORT_AUDIT_MODEL = os.getenv("TEST_IMPORT_AUDIT_MODEL", QUESTION_AUDIT_MODEL).strip()
if QUESTION_AUDIT_PROVIDER == "deepseek" and not TEST_IMPORT_AUDIT_MODEL.startswith("deepseek-"):
    TEST_IMPORT_AUDIT_MODEL = QUESTION_AUDIT_MODEL
elif QUESTION_AUDIT_PROVIDER == "openai" and TEST_IMPORT_AUDIT_MODEL.startswith("deepseek-"):
    TEST_IMPORT_AUDIT_MODEL = QUESTION_AUDIT_MODEL
TEST_IMPORT_TIMEOUT_SECONDS = int(os.getenv("TEST_IMPORT_TIMEOUT_SECONDS", "180"))
TEST_IMPORT_RUN_AI_AUDIT = os.getenv("TEST_IMPORT_RUN_AI_AUDIT", "1").strip().lower() not in {"0", "false", "no", "off"}  # CLI/legacy opt-in only; web import never auto-audits.

