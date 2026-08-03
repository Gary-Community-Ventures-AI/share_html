from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import Blueprint, Response, abort, current_app, g, redirect, request, send_file, send_from_directory
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import text

from .extensions import db
from .host import require_surface
from .models import Document, DocumentLinkAccess, User
from .permissions import can_view_document
from .storage import storage


documents = Blueprint("documents", __name__)


def frontend_dist() -> Path:
    return Path(current_app.root_path) / "static"


def render_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="document-render")


def content_security_policy() -> str:
    app_url = urlsplit(current_app.config["APP_PUBLIC_URL"])
    frame_ancestor = f"{app_url.scheme}://{app_url.netloc}"
    return "; ".join(
        [
            "default-src 'none'",
            "script-src 'self' 'unsafe-inline' blob:",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "media-src 'self' blob:",
            "connect-src 'self'",
            "frame-src 'none'",
            "worker-src 'none'",
            "object-src 'none'",
            "form-action 'none'",
            "base-uri 'none'",
            f"frame-ancestors {frame_ancestor}",
            "sandbox allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox",
        ]
    )


def secure_document_response(response: Response) -> Response:
    response.headers["Content-Security-Policy"] = content_security_policy()
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-DNS-Prefetch-Control"] = "off"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), clipboard-write=(self)"
    )
    return response


@documents.get("/health")
def health():
    return {"status": "ok"}


@documents.get("/ready")
def ready():
    try:
        migrations_path = Path(current_app.root_path).parents[1] / "migrations"
        expected_revision = ScriptDirectory(str(migrations_path)).get_current_head()
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current_revision = MigrationContext.configure(connection).get_current_revision()
        if not expected_revision or current_revision != expected_revision:
            raise RuntimeError("Database migration revision is not current")
        storage.ready()
    except Exception:
        current_app.logger.exception("Readiness check failed")
        return {"status": "not ready"}, 503
    return {"status": "ready"}


@documents.get("/_render")
def render_document():
    require_surface("document")
    token = request.args.get("token", "")
    try:
        payload = render_serializer().loads(
            token,
            max_age=current_app.config["RENDER_TICKET_SECONDS"],
        )
    except SignatureExpired:
        abort(401, description="Render ticket expired")
    except BadSignature:
        abort(401, description="Invalid render ticket")
    if payload.get("document_id") != g.document_id:
        abort(401, description="Render ticket does not match this document")
    document = db.session.get(Document, g.document_id)
    if document is None:
        abort(404, description="Document not found")
    if payload.get("public"):
        policy = db.session.get(DocumentLinkAccess, document.id)
        if policy is None or not policy.enabled or payload.get("version") != policy.version:
            abort(403, description="Public link is no longer available")
    else:
        user = db.session.get(User, payload.get("user_id"))
        if user is None or not can_view_document(user, document):
            abort(403, description="Document access denied")

    try:
        content = storage.get(document.object_key)
    except FileNotFoundError:
        abort(404, description="Document content not found")
    if request.args.get("download") == "1":
        download_name = document.title if document.title.lower().endswith(".html") else f"{document.title}.html"
        return secure_document_response(
            send_file(
                BytesIO(content.encode("utf-8")),
                mimetype="text/html; charset=utf-8",
                as_attachment=True,
                download_name=download_name,
            )
        )
    return secure_document_response(Response(content, content_type="text/html; charset=utf-8"))


@documents.get("/")
def index():
    if g.request_surface == "document":
        document = db.session.get(Document, g.document_id)
        if document is None:
            abort(404, description="Document not found")
        return redirect(f"{current_app.config['APP_PUBLIC_URL']}/documents/{document.id}", code=303)

    require_surface("app")
    if (frontend_dist() / "index.html").is_file():
        return send_from_directory(frontend_dist(), "index.html")
    return {"name": "ShareHTML", "status": "running"}


@documents.get("/assets/<path:path>")
def application_asset(path: str):
    require_surface("app")
    return send_from_directory(frontend_dist() / "assets", path)


@documents.get("/<path:path>")
def application_route(path: str):
    require_surface("app")
    if path.startswith("api/"):
        abort(404)
    if (frontend_dist() / "index.html").is_file():
        return send_from_directory(frontend_dist(), "index.html")
    abort(404)
