from __future__ import annotations

import logging
import os
import socket
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from playwright.sync_api import Browser, sync_playwright
from sqlalchemy import and_, or_, select

from . import create_app
from .extensions import db
from .models import Document, ThumbnailJob, now
from .storage import storage
from .thumbnails import thumbnail_render_url


LOGGER = logging.getLogger("sharehtml.thumbnail_worker")
MAX_ATTEMPTS = 4
LEASE_SECONDS = 120


def claim_job(worker_id: str) -> tuple[str, int] | None:
    current_time = now()
    job = db.session.scalar(
        select(ThumbnailJob)
        .where(
            ThumbnailJob.available_at <= current_time,
            or_(
                ThumbnailJob.status == "pending",
                and_(
                    ThumbnailJob.status == "processing",
                    or_(
                        ThumbnailJob.lease_expires_at.is_(None),
                        ThumbnailJob.lease_expires_at < current_time,
                    ),
                ),
            ),
        )
        .order_by(ThumbnailJob.available_at, ThumbnailJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "processing"
    job.attempts += 1
    job.lease_owner = worker_id
    job.lease_expires_at = current_time + timedelta(seconds=LEASE_SECONDS)
    job.error = None
    db.session.commit()
    return job.document_id, job.content_version


def capture_thumbnail(browser: Browser, document: Document, version: int) -> bytes:
    render_url = thumbnail_render_url(document, version)
    render_origin = urlsplit(render_url).netloc
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        device_scale_factor=1,
        reduced_motion="reduce",
    )
    page = context.new_page()
    page.set_default_timeout(10_000)
    page.route(
        "**/*",
        lambda route: (
            route.continue_()
            if urlsplit(route.request.url).netloc in {"", render_origin}
            else route.abort("blockedbyclient")
        ),
    )
    try:
        response = page.goto(render_url, wait_until="domcontentloaded", timeout=15_000)
        if response is None or not response.ok:
            raise RuntimeError(
                f"Thumbnail render returned {response.status if response else 'no response'}"
            )
        page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve()")
        page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        page.wait_for_timeout(750)
        return page.screenshot(type="jpeg", quality=78, full_page=False)
    finally:
        context.close()


def finish_job(document_id: str, version: int, image: bytes) -> None:
    job = db.session.get(ThumbnailJob, (document_id, version))
    if job is None:
        return
    document = db.session.get(Document, document_id)
    if document is None or document.content_version != version:
        job.status = "superseded"
        job.lease_owner = None
        job.lease_expires_at = None
        db.session.commit()
        return

    object_key = f"documents/{document.id}/thumbnails/{version}.jpg"
    storage.put_bytes(object_key, image, "image/jpeg")
    document = db.session.scalar(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if document is None or document.content_version != version:
        storage.delete(object_key)
        job.status = "superseded"
        job.lease_owner = None
        job.lease_expires_at = None
        db.session.commit()
        return

    previous_key = document.thumbnail_object_key
    document.thumbnail_version = version
    document.thumbnail_object_key = object_key
    document.thumbnail_status = "ready"
    job.status = "complete"
    job.lease_owner = None
    job.lease_expires_at = None
    db.session.commit()
    if previous_key and previous_key != object_key:
        try:
            storage.delete(previous_key)
        except Exception:
            LOGGER.exception("Failed to remove superseded thumbnail %s", previous_key)


def fail_job(document_id: str, version: int, error: Exception) -> None:
    job = db.session.get(ThumbnailJob, (document_id, version))
    document = db.session.get(Document, document_id)
    if job is None:
        return
    job.error = str(error)[:1000]
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempts >= MAX_ATTEMPTS:
        job.status = "failed"
        if document is not None and document.content_version == version:
            document.thumbnail_status = "failed"
    else:
        job.status = "pending"
        job.available_at = now() + timedelta(seconds=5 * (2 ** (job.attempts - 1)))
    db.session.commit()


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/ready":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ready"}')
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return


def start_health_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "5000"))), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    app = create_app()
    health_server = start_health_server()
    with app.app_context(), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--disable-background-networking"],
        )
        try:
            while True:
                claimed = claim_job(worker_id)
                if claimed is None:
                    time.sleep(2)
                    continue
                document_id, version = claimed
                try:
                    document = db.session.get(Document, document_id)
                    if document is None or document.content_version != version:
                        finish_job(document_id, version, b"")
                        continue
                    image = capture_thumbnail(browser, document, version)
                    finish_job(document_id, version, image)
                    LOGGER.info("Generated thumbnail for %s version %s", document_id, version)
                except Exception as error:
                    db.session.rollback()
                    LOGGER.exception("Thumbnail generation failed for %s version %s", document_id, version)
                    fail_job(document_id, version, error)
        finally:
            browser.close()
            health_server.shutdown()


if __name__ == "__main__":
    main()
