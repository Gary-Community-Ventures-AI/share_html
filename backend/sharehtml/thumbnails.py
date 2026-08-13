from __future__ import annotations

from urllib.parse import urlencode

from flask import current_app
from itsdangerous import URLSafeTimedSerializer

from .extensions import db
from .models import Document, ThumbnailJob


def thumbnail_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="document-thumbnail")


def thumbnail_render_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="document-thumbnail-render")


def enqueue_thumbnail(document: Document) -> None:
    document.thumbnail_status = "pending"
    if db.session.get(ThumbnailJob, (document.id, document.content_version)) is None:
        db.session.add(
            ThumbnailJob(
                document_id=document.id,
                content_version=document.content_version,
            )
        )


def thumbnail_url(document: Document) -> str | None:
    if document.thumbnail_version is None or not document.thumbnail_object_key:
        return None
    token = thumbnail_serializer().dumps(
        {"document_id": document.id, "version": document.thumbnail_version}
    )
    query = urlencode({"token": token})
    return (
        f"{current_app.config['APP_PUBLIC_URL']}/api/v1/document-thumbnails/"
        f"{document.id}/{document.thumbnail_version}?{query}"
    )


def thumbnail_render_url(document: Document, version: int) -> str:
    suffix = current_app.config["CONTENT_HOST_SUFFIX"]
    scheme = current_app.config["CONTENT_PUBLIC_SCHEME"]
    port = current_app.config["CONTENT_PUBLIC_PORT"]
    port_part = "" if port in {"", "80", "443"} else f":{port}"
    token = thumbnail_render_serializer().dumps(
        {"document_id": document.id, "version": version}
    )
    return f"{scheme}://{document.id}{suffix}{port_part}/_thumbnail_render?{urlencode({'token': token})}"
