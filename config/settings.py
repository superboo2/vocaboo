"""
Django settings for the Vokie project.

Values that differ between machines (database, secret key, debug) come from
environment variables. For local work they can be put into the .env file in the
project directory, see .env.example and README.md.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    """Load KEY=VALUE lines from a file into os.environ.

    Real environment variables win over values from the file.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


load_env_file(BASE_DIR / ".env")


# Security

DEBUG = env_bool("DJANGO_DEBUG")

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "change-me":
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a secret value (see README.md).")
    # Only for local development
    SECRET_KEY = "django-insecure-local-development-only"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Full addresses the app is opened at, e.g. https://vokie.example.com (needed for forms over HTTPS)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

if not DEBUG:
    # The app runs behind nginx, which talks HTTPS to the browser and tells Django about it
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Browsers remember to use only HTTPS; start small, raise it when HTTPS works well
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Lets the form renderer below find Django's own form templates
    "django.forms",
    # Needed for unaccent lookups and PostgreSQL specific migrations
    "django.contrib.postgres",
    # Project apps
    "accounts",
    "vocabulary",
    "study",
    "dictionary",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every page needs a logged in user, except views marked with login_not_required
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Form fields use templates/forms/field.html
FORM_RENDERER = "config.forms.FormRenderer"


# Database

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "vokie"),
        "USER": env("DB_USER", "vokie"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Users and login

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# UI is Czech for now, texts are marked for translation so other languages can come later.

LANGUAGE_CODE = "cs"

TIME_ZONE = "Europe/Prague"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, images)

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Target folder for collectstatic (used on the server)
STATIC_ROOT = BASE_DIR / "staticfiles"


# Translation suggestions when a word is typed, sources in this order (see dictionary/providers.py)
SUGGESTION_PROVIDERS = env_list("VOKIE_SUGGESTION_PROVIDERS", "wiktionary")
# Pronunciation of words (IPA and recordings), sources in this order
PRONUNCIATION_PROVIDERS = env_list("VOKIE_PRONUNCIATION_PROVIDERS", "wiktionary")


# Logging: errors go to the console, on the server systemd keeps them (journalctl -u vokie)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
    },
}


# Email
# The MVP sends no emails. Locally they would be printed to the console; on the server the
# SMTP backend is set up already, it gets its settings once password reset by email comes.

MAILERS = {
    "default": {
        "BACKEND": (
            "django.core.mail.backends.console.EmailBackend"
            if DEBUG
            else "django.core.mail.backends.smtp.EmailBackend"
        ),
    },
}
