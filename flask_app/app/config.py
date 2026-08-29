"""Environment-driven configuration. No secrets live in source code."""

import os
from datetime import timedelta


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _csv(name: str, default: str) -> list[str]:
    raw = os.environ.get(name) or default
    return [item.strip() for item in raw.split(",") if item.strip()]


class BaseConfig:
    # --- core -------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://localhost:5432/imagehost"
    )
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://") :]
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- branding ---------------------------------------------------------
    APP_NAME = os.environ.get("APP_NAME", "ADM Cloud")
    APP_BASE_URL = (
        os.environ.get("APP_BASE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or "http://localhost:5000"
    ).rstrip("/")
    APP_LOGO_URL = os.environ.get("APP_LOGO_URL") or "/static/images/adm-cloud-logo.svg"
    APP_FAVICON_URL = os.environ.get("APP_FAVICON_URL") or "/static/images/adm-cloud-logo.svg"
    APP_PRIMARY_COLOR = os.environ.get("APP_PRIMARY_COLOR", "#4f46e5")
    APP_SECONDARY_COLOR = os.environ.get("APP_SECONDARY_COLOR", "#0ea5e9")
    SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@example.com")
    PUBLIC_IMAGE_BASE_URL = (
        os.environ.get("PUBLIC_IMAGE_BASE_URL")
        or os.environ.get("APP_PUBLIC_BASE_URL")
        or os.environ.get("APP_BASE_URL")
        or ""
    ).rstrip("/")

    # --- social login -----------------------------------------------------
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

    # --- storage provider (server-side only) ------------------------------
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")
    CLOUDINARY_UPLOAD_FOLDER = os.environ.get("CLOUDINARY_UPLOAD_FOLDER", "uploads")
    CLOUDINARY_THUMB_TRANSFORM = os.environ.get(
        "CLOUDINARY_THUMB_TRANSFORM", "c_fill,w_400,h_400,q_auto,f_auto"
    )

    # --- mail -------------------------------------------------------------
    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "no-reply@example.com")
    SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
    SMTP_USE_SSL = _bool("SMTP_USE_SSL", False)
    SMTP_TIMEOUT = _int("SMTP_TIMEOUT", 15)
    MAIL_SUPPRESS_SEND = False

    # --- uploads ----------------------------------------------------------
    UPLOAD_MAX_SIZE = _int("UPLOAD_MAX_SIZE", 10 * 1024 * 1024)
    ALLOWED_IMAGE_TYPES = _csv(
        "ALLOWED_IMAGE_TYPES", "image/jpeg,image/png,image/webp,image/gif"
    )
    MAX_CONTENT_LENGTH = UPLOAD_MAX_SIZE + 1024 * 1024  # payload headroom

    # --- session / security ----------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=_int("PERMANENT_SESSION_LIFETIME", 604800))
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    VERIFICATION_TOKEN_MAX_AGE = _int("VERIFICATION_TOKEN_MAX_AGE", 86400)
    PREFERRED_URL_SCHEME = "https"

    # --- rate limiting ----------------------------------------------------
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_LOGIN = os.environ.get("RATELIMIT_LOGIN", "10 per 15 minutes")
    RATELIMIT_REGISTER = os.environ.get("RATELIMIT_REGISTER", "5 per hour")
    RATELIMIT_VERIFY_RESEND = os.environ.get("RATELIMIT_VERIFY_RESEND", "5 per hour")
    RATELIMIT_UPLOAD = os.environ.get("RATELIMIT_UPLOAD", "60 per hour")
    RATELIMIT_HEADERS_ENABLED = True

    DEBUG = False
    TESTING = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "testing-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    UPLOAD_MAX_SIZE = 1024 * 1024
    MAX_CONTENT_LENGTH = 1024 * 1024 + 4096


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None):
    key = (name or os.environ.get("FLASK_ENV") or "production").lower()
    return CONFIGS.get(key, ProductionConfig)
