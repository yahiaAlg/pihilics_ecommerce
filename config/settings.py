"""
Django settings for the Pihilics e-commerce backend.

Project-config layout: this file lives in the `config/` package alongside
urls.py and wsgi.py/asgi.py, one level above the ten top-level app
packages themselves (accounts, bookings, cart, catalog, content, core,
dealers, orders, programs, support). This matches every app's `apps.py`,
which sets `name` to its own bare package name (e.g. `name = "accounts"`,
not `"config.accounts"`), and every existing cross-app import, which
already uses that same flat form (e.g. `from core.constants import ...`
in accounts/models.py, `from .models import Category, Product` etc.).
Only project-wide wiring (settings, root urlconf, wsgi/asgi) is namespaced
under `config`.

Anything that legitimately varies between environments -- secret key,
debug flag, allowed hosts, database -- is read from the environment, with
insecure-but-convenient defaults so `manage.py runserver` works out of
the box for local development with zero setup.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# One level up from config/settings.py -- the project root where manage.py
# and every app package live.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-pihilics-dev-only-key-do-not-use-in-production",
)

DEBUG = env_bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "www.pihilics-product.com,pihilics-product.com,localhost,127.0.0.1",
)

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party -- powers catalog.resources' ProductResource/CategoryResource
    # (django-import-export), registered onto ProductAdmin via
    # ImportExportModelAdmin. Needs to be a real installed app (not just
    # importable) so its admin templates/static assets are found.
    "import_export",
    # Project apps. `core` first since `core.constants` (wilaya choices,
    # language choices, ...) and `core.models.CompanyInfo`
    # are depended on by several of the others; the rest are alphabetical.
    # Django itself doesn't require FK-dependency ordering here -- migrations
    # resolve that independently -- this ordering is purely for readability.
    "core",
    "accounts",
    "bookings",
    "cart",
    "catalog",
    "content",
    "dealers",
    "orders",
    "programs",
    "support",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves STATIC_ROOT *and* MEDIA_ROOT directly from the app process, so
    # the project runs identically under `runserver` and behind gunicorn
    # with no nginx/S3 in front. This is core.middleware's WhiteNoise
    # subclass rather than WhiteNoise's own class because stock WhiteNoise
    # has no notion of MEDIA_URL -- see that module's docstring. It must sit
    # immediately after SecurityMiddleware and above everything else: assets
    # are then returned before session, auth, and CSRF middleware do
    # per-request work that a static file never needs.
    "core.middleware.WhiteNoiseMediaMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Per-app templates (APP_DIRS, e.g. catalog/templates/catalog/shop.html
        # for the render(request, "catalog/shop.html", ...) calls already
        # throughout views.py) are the primary source; this project-level
        # dir is for any truly shared/base templates (base.html, 404.html).
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_identity",
                "core.context_processors.header_badges",
                "core.context_processors.nav_active_default",
                "core.context_processors.mega_menu_catalog",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Defaults to SQLite, which is what every prior phase's `django check`,
# `makemigrations --check`, and live admin/test-client runs have used.
# Set DJANGO_DB_ENGINE=mysql (plus the DJANGO_DB_* vars below) for a real
# deployment against MySQL/MariaDB -- requires the `mysqlclient` package
# (see requirements.txt).

if os.environ.get("DJANGO_DB_ENGINE") == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ["DJANGO_DB_NAME"],
            "USER": os.environ.get("DJANGO_DB_USER", ""),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", "localhost"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Every @login_required view added so far (catalog's wishlist/garage/reviews,
# orders history, bookings, the Account page itself) redirects unauthenticated
# visitors here; accounts.urls names its login view "login" under the
# "accounts" namespace, i.e. accounts/login/.
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:account"
LOGOUT_REDIRECT_URL = "content:home"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
# Note: UserProfile.preferred_language (choices from the core.Language
# table, via core.constants.language_choices) is
# an Account > Preferences field describing what language the storefront
# should render in for that visitor -- a template/i18n concern for a later
# phase, distinct from this server-side default.

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
# MEDIA is real, admin-editable content -- Product.image, Story.cover_image,
# CompanyInfo.logo are all ImageField -- not just admin-upload scratch space.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise -----------------------------------------------------------------
# STORAGES["staticfiles"] uses WhiteNoise's compressed + manifest backend:
# `collectstatic` pre-compresses every asset and rewrites each filename with
# a content hash, so CSS/JS can be served with a far-future cache header and
# a redeploy busts the cache automatically. The manifest backend raises on a
# missing file at render time, which catches a typo'd `{% static %}` path in
# CI rather than in production -- but it needs `collectstatic` to have run,
# so DEBUG keeps the plain backend for local work.
#
# MEDIA is admin-uploaded content (Product.image, Story.cover_image,
# HomeCarouselSlide.image, CompanyInfo.logo, HomePageContent.cine_video),
# so it must NOT be hashed or manifested -- those filenames are stored in
# the database and must stay byte-identical to what was uploaded. It is
# served instead by core.middleware.WhiteNoiseMediaMiddleware, which mounts
# MEDIA_ROOT under MEDIA_URL, so MEDIA_ROOT/home/hero.jpg is reachable at
# /media/home/hero.jpg with no extra URL wiring and no DEBUG-only branch.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

WHITENOISE_INDEX_FILE = False

# Admin-uploaded media changes without a redeploy, so it can't take the
# immutable far-future header hashed static files get. A short cache is
# still worth having for repeat views of the same product photo.
WHITENOISE_MAX_AGE = 0 if DEBUG else 3600

# ---------------------------------------------------------------------------
# Site URL (for absolute links in outgoing emails)
# ---------------------------------------------------------------------------

SITE_URL = os.environ.get("SITE_URL", "https://pihilics.dz").rstrip("/")

# ---------------------------------------------------------------------------
# Chargily Pay (orders.chargily) -- CIB / Edahabia card checkout
# ---------------------------------------------------------------------------
#
# Chargily is the payment gateway that actually reaches SATIM (Algeria's
# domestic card switch) on our behalf -- there's no direct integration with
# CIB or Edahabia to be had otherwise, the same way there's no way to accept
# Visa/Mastercard without going through Stripe or a similar gateway. Test
# and live are two entirely separate environments (separate base URL,
# separate key pair) rather than one flag, specifically so a stray deploy
# can't accidentally start charging real cards -- see orders/chargily.py.
#
# CHARGILY_SECRET is also what signs/verifies webhooks (Chargily has no
# separate webhook-signing secret the way Stripe does), so treat it with the
# same care as EMAIL_HOST_PASSWORD: never in git, never client-side.
CHARGILY_KEY = os.environ.get("CHARGILY_KEY", "")
CHARGILY_SECRET = os.environ.get("CHARGILY_SECRET", "")
CHARGILY_API_URL = os.environ.get(
    "CHARGILY_API_URL", "https://pay.chargily.net/test/api/v2/"
)

# ---------------------------------------------------------------------------
# Email (core.emails + <app>/notifications.py)
# ---------------------------------------------------------------------------
# Mailing notifications back and forth between admin and customer (order
# confirmation/status, test-ride/service booking received/approved, contact
# form ack, etc. -- see core/emails.py for the shared send layer). SMTP
# creds come from the environment, same as everything else that legitimately
# varies per-environment (see module docstring). When EMAIL_HOST_PASSWORD is
# unset -- the out-of-the-box local-dev case -- mail falls back to the
# console backend so nothing ever needs a live mail server to run or to pass
# the verify_*.py suite.

EMAIL_HOST = os.environ.get("EMAIL_HOST", "mail.pihilics-product.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "465"))
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", default=True)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=False)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "commercial@pihilics-product.com")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10

EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST_PASSWORD
    else "django.core.mail.backends.console.EmailBackend"
)

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", f"Pihilics <{EMAIL_HOST_USER}>"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Fixed internal inbox that every admin-facing notification (new order, new
# booking, contact-form alert, ...) is sent to -- distinct from
# EMAIL_HOST_USER, which is only the SMTP login/sending identity.
ADMIN_NOTIFICATION_EMAIL = os.environ.get(
    "ADMIN_NOTIFICATION_EMAIL", "admin@pihilics-product.com"
)
