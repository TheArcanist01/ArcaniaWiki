"""
Django settings for the Arcania Wiki.

Everything that differs between your computer and the public server is read
from environment variables, or from a `.env` file in the project folder (not
tracked by git). See `.env.example` and DEPLOYMENT.md.

On your computer no settings are needed: everything started through
`manage.py` (runserver, test, changepassword...) runs in development mode
(DEBUG on). The site started by gunicorn/waitress on the server (config/wsgi.py)
runs in the safe production mode. DJANGO_DEBUG, when set, always wins; the
server's .env sets DJANGO_DEBUG=False so its manage.py commands match the site.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    """Read KEY=VALUE lines from a .env file into os.environ (real env vars win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name):
    return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]


# --- Core -------------------------------------------------------------------

# manage.py sets DJANGO_DEBUG_DEFAULT=True; the WSGI server does not.
DEBUG = env_bool("DJANGO_DEBUG", env_bool("DJANGO_DEBUG_DEFAULT", False))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. Put a long random key in the server's "
            "environment or .env file (see .env.example)."
        )
    SECRET_KEY = "django-insecure-local-development-only"

# Domains the site answers to, e.g. "arcaniawiki.example.com,www.arcaniawiki.example.com".
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Full https:// addresses of the site, needed for logging in to the admin panel.
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Address of the admin panel (without slashes).
ADMIN_URL = os.environ.get("DJANGO_ADMIN_URL", "arcaniawikiadmin").strip("/")


# --- Application definition ---------------------------------------------------

try:
    import whitenoise  # noqa: F401  (serves CSS/JS/site images in production)

    HAS_WHITENOISE = True
except ImportError:
    HAS_WHITENOISE = False
    if not DEBUG:
        raise ImproperlyConfigured("WhiteNoise is missing: run `pip install -r requirements.txt`.")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'arcaniawiki',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves CSS/JS/site images on the server (locally, runserver does it).
    *(['whitenoise.middleware.WhiteNoiseMiddleware'] if HAS_WHITENOISE and not DEBUG else []),
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'arcaniawiki.security.AdminLoginThrottleMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'arcaniawiki.context_processors.navigation',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# --- Database -----------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# --- Passwords ------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Cache shared by all server processes (used for the admin login counter).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": BASE_DIR / ".cache",
    }
}

# Admin login protection (arcaniawiki/security.py): after this many failed
# attempts from one address, logging in from it is blocked for the given time.
ADMIN_LOGIN_MAX_FAILURES = int(os.environ.get("DJANGO_ADMIN_LOGIN_MAX_FAILURES", "5"))
ADMIN_LOGIN_LOCKOUT_SECONDS = int(os.environ.get("DJANGO_ADMIN_LOGIN_LOCKOUT_SECONDS", "900"))


# --- Internationalization -------------------------------------------------------

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# --- Static files (CSS, JavaScript, site images) and uploads ---------------------

STATIC_URL = 'static/'
# `python manage.py collectstatic` copies all static files here for the server.
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedStaticFilesStorage"
            if HAS_WHITENOISE and not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

# Uploaded images (items, enemies, maps)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Let Django itself serve the uploaded images. Always on locally; on a server
# that has no separate web server (nginx, Apache) for /media/, keep it on too.
SERVE_MEDIA = env_bool("DJANGO_SERVE_MEDIA", True)


# --- HTTPS and security headers (production) ------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # How long browsers must use HTTPS only. Start small; raise to 31536000
    # (a year) once you are sure HTTPS works on the domain.
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)
    # Behind a proxy/load balancer that terminates HTTPS (most hosting panels).
    if env_bool("DJANGO_BEHIND_PROXY", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
