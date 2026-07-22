from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, g, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from .api import api
from .config import Config
from .documents import documents
from .extensions import db, migrate
from .host import classify_request_host


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config)

    if app.config["STORAGE_BACKEND"] not in {"local", "s3"}:
        raise RuntimeError("STORAGE_BACKEND must be local or s3")
    if app.config["RENDER_TICKET_SECONDS"] <= 0 or app.config["PUBLIC_ACCESS_TOKEN_SECONDS"] <= 0:
        raise RuntimeError("Token lifetimes must be positive")

    if app.config["APP_ENV"] == "production":
        if app.config["SECRET_KEY"] == "development-secret-only":
            raise RuntimeError("SECRET_KEY must be set in production")
        if app.config["API_KEY_PEPPER"] == "development-pepper-only":
            raise RuntimeError("API_KEY_PEPPER must be set in production")
        if not app.config["CLERK_ISSUER"] or not app.config["CLERK_SECRET_KEY"]:
            raise RuntimeError("Clerk configuration must be set in production")
        if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://"):
            raise RuntimeError("PostgreSQL with the psycopg driver is required in production")
        if app.config["STORAGE_BACKEND"] != "s3":
            raise RuntimeError("S3 storage is required in production")
        required_s3 = ["S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]
        if any(not app.config[name] for name in required_s3):
            raise RuntimeError("Complete S3 configuration is required in production")
        if not app.config["APP_PUBLIC_URL"].startswith("https://"):
            raise RuntimeError("APP_PUBLIC_URL must use HTTPS in production")
        if app.config["CONTENT_PUBLIC_SCHEME"] != "https":
            raise RuntimeError("Document content must use HTTPS in production")
        if not app.config["TRUST_PROXY_HOST"]:
            raise RuntimeError("TRUST_PROXY_HOST must be enabled behind the production proxy")
        if not app.config["CLERK_AUTHORIZED_PARTIES"]:
            raise RuntimeError("At least one Clerk authorized party is required in production")
        if app.config["APP_PUBLIC_URL"] not in app.config["CLERK_AUTHORIZED_PARTIES"]:
            raise RuntimeError("APP_PUBLIC_URL must be an authorized Clerk party")
        if app.config["APP_HOST"] in {"localhost", "app.localtest.me"}:
            raise RuntimeError("A production application host is required")
        if app.config["CONTENT_HOST_SUFFIX"] == ".lvh.me":
            raise RuntimeError("A production document host suffix is required")

    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    if app.config["TRUST_PROXY_HOST"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.register_blueprint(api, url_prefix="/api/v1")
    app.register_blueprint(documents)

    @app.before_request
    def identify_surface() -> None:
        classify_request_host()

    @app.after_request
    def secure_application_response(response):
        if getattr(g, "request_surface", None) == "app":
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault(
                "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
            )
            if app.config["APP_ENV"] == "production":
                response.headers.setdefault(
                    "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                )
        return response

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(413)
    @app.errorhandler(429)
    @app.errorhandler(503)
    def json_error(error):
        if getattr(error, "description", None):
            message = error.description
        else:
            message = "Request failed"
        return jsonify(error=message), error.code

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled request error", exc_info=error)
        return jsonify(error="Internal server error"), 500

    return app


app = create_app() if os.environ.get("SHAREHTML_CREATE_GLOBAL_APP") else None
