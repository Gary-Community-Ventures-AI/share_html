from __future__ import annotations

import base64
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(override=os.getenv("APP_ENV", "development") != "production")


def clerk_issuer() -> str:
    configured = os.getenv("CLERK_ISSUER", "").rstrip("/")
    if configured:
        return configured
    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY", "") or os.getenv(
        "VITE_CLERK_PUBLISHABLE_KEY", ""
    )
    if not publishable_key.startswith(("pk_test_", "pk_live_")):
        return ""
    encoded = publishable_key.split("_", 2)[2]
    try:
        domain = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode().rstrip("$")
    except (UnicodeDecodeError, ValueError):
        return ""
    return f"https://{domain}" if domain else ""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "sqlite:///sharehtml-v1.db")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def authorized_parties() -> tuple[str, ...]:
    default = os.getenv("APP_PUBLIC_URL", "http://app.localtest.me:5173").rstrip("/")
    return tuple(
        value.strip().rstrip("/")
        for value in os.getenv("CLERK_AUTHORIZED_PARTIES", default).split(",")
        if value.strip()
    )


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-only")
    API_KEY_PEPPER = os.getenv("API_KEY_PEPPER", "development-pepper-only")

    SQLALCHEMY_DATABASE_URI = database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(5 * 1024 * 1024)))

    APP_HOST = os.getenv("APP_HOST", "app.localtest.me")
    APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://app.localtest.me:5173").rstrip("/")
    CONTENT_HOST_SUFFIX = os.getenv("CONTENT_HOST_SUFFIX", ".lvh.me")
    CONTENT_PUBLIC_SCHEME = os.getenv("CONTENT_PUBLIC_SCHEME", "http")
    CONTENT_PUBLIC_PORT = os.getenv("CONTENT_PUBLIC_PORT", "5000")
    TRUST_PROXY_HOST = env_bool("TRUST_PROXY_HOST", False)

    CLERK_ISSUER = clerk_issuer()
    CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
    CLERK_AUTHORIZED_PARTIES = authorized_parties()

    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
    LOCAL_STORAGE_PATH = os.getenv("LOCAL_STORAGE_PATH", str(Path("instance") / "documents"))
    S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
    S3_REGION = os.getenv("S3_REGION", "auto")
    S3_BUCKET = os.getenv("S3_BUCKET", "")
    S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")

    RENDER_TICKET_SECONDS = int(os.getenv("RENDER_TICKET_SECONDS", "300"))
    PUBLIC_ACCESS_TOKEN_SECONDS = int(os.getenv("PUBLIC_ACCESS_TOKEN_SECONDS", "3600"))
    THUMBNAIL_URL_SECONDS = int(os.getenv("THUMBNAIL_URL_SECONDS", "3600"))
    THUMBNAIL_RENDER_SECONDS = int(os.getenv("THUMBNAIL_RENDER_SECONDS", "300"))
