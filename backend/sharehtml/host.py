from __future__ import annotations

import re

from flask import abort, current_app, g, request


DOCUMENT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def request_host() -> str:
    raw = request.host
    if "," in raw:
        abort(400, description="Invalid host")
    return raw.split(",", 1)[0].strip().split(":", 1)[0].lower()


def classify_request_host() -> None:
    if request.path in {"/health", "/ready"}:
        g.request_surface = "health"
        g.document_id = None
        return

    host = request_host()
    app_host = current_app.config["APP_HOST"].lower()
    suffix = current_app.config["CONTENT_HOST_SUFFIX"].lower()

    if host == app_host or (current_app.config["APP_ENV"] == "development" and host in {"localhost", "127.0.0.1"}):
        g.request_surface = "app"
        g.document_id = None
        return

    if host.endswith(suffix):
        document_id = host[: -len(suffix)]
        if DOCUMENT_ID_PATTERN.fullmatch(document_id):
            g.request_surface = "document"
            g.document_id = document_id
            return

    abort(404, description="Unknown host")


def require_surface(surface: str) -> None:
    if getattr(g, "request_surface", None) != surface:
        abort(404)
