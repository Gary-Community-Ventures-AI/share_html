from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime

from flask import Blueprint, Response, abort, current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .auth import authenticated, issue_api_key
from .extensions import db
from .host import require_surface
from .models import (
    ApiKey,
    Contact,
    Document,
    DocumentAccess,
    DocumentLinkAccess,
    DocumentUnlockThrottle,
    Group,
    GroupRecipient,
    User,
    new_id,
    now,
)
from .permissions import (
    can_edit_document,
    can_manage_document,
    can_share_document,
    can_view_document,
    require_group_owner,
    viewable_documents,
)
from .storage import storage
from .thumbnails import enqueue_thumbnail, thumbnail_serializer, thumbnail_url


api = Blueprint("api", __name__)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def user_json(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}


def contact_json(contact: Contact) -> dict:
    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "created_at": iso(contact.created_at),
    }


def group_json(group: Group) -> dict:
    recipient_count = db.session.scalar(
        select(func.count()).select_from(GroupRecipient).where(GroupRecipient.group_id == group.id)
    )
    return {
        "id": group.id,
        "name": group.name,
        "recipient_count": recipient_count or 0,
        "created_at": iso(group.created_at),
    }


def document_json(document: Document, viewer: User | None = None) -> dict:
    payload = {
        "id": document.id,
        "title": document.title,
        "url": f"{current_app.config['APP_PUBLIC_URL']}/documents/{document.id}",
        "created_at": iso(document.created_at),
        "updated_at": iso(document.updated_at),
        "thumbnail_status": document.thumbnail_status,
        "thumbnail_stale": (
            document.thumbnail_version is not None
            and document.thumbnail_version < document.content_version
        ),
        "thumbnail_url": thumbnail_url(document),
    }
    if viewer is not None:
        payload["relationship"] = "mine" if document.created_by_id == viewer.id else "shared"
        payload["can_edit"] = can_edit_document(viewer, document)
        payload["can_manage"] = can_manage_document(viewer, document)
        payload["can_share"] = can_share_document(viewer, document)
    return payload


def document_content_origin(document: Document) -> str:
    suffix = current_app.config["CONTENT_HOST_SUFFIX"]
    scheme = current_app.config["CONTENT_PUBLIC_SCHEME"]
    port = current_app.config["CONTENT_PUBLIC_PORT"]
    port_part = "" if port in {"", "80", "443"} else f":{port}"
    return f"{scheme}://{document.id}{suffix}{port_part}"


def api_key_json(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": f"sh_live_{key.public_id}.",
        "created_at": iso(key.created_at),
        "last_used_at": iso(key.last_used_at),
        "expires_at": iso(key.expires_at),
    }


def link_access_json(policy: DocumentLinkAccess | None, *, include_password: bool = False) -> dict:
    result = {
        "enabled": bool(policy and policy.enabled),
        "password_protected": bool(policy and policy.password),
    }
    if include_password:
        result["password"] = policy.password if policy else None
    return result


def json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, description="A JSON object is required")
    return body


def required_text(body: dict, field: str, *, maximum: int | None = None) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        abort(400, description=f"{field} is required")
    value = value.strip() if field != "content" else value
    if maximum and len(value) > maximum:
        abort(400, description=f"{field} is too long")
    return value


def public_access_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="public-document-access")


def render_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="document-render")


def unlock_client_hash() -> str:
    client = request.remote_addr or "unknown"
    return hmac.new(
        current_app.config["API_KEY_PEPPER"].encode(),
        client.encode(),
        hashlib.sha256,
    ).hexdigest()


def record_unlock_failure(document_id: str) -> None:
    current_time = int(time.time())
    client_hash = unlock_client_hash()
    throttle = db.session.get(DocumentUnlockThrottle, (document_id, client_hash))
    if throttle is None:
        throttle = DocumentUnlockThrottle(
            document_id=document_id,
            client_hash=client_hash,
            attempts=0,
            window_started_at=current_time,
        )
        db.session.add(throttle)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            throttle = db.session.get(DocumentUnlockThrottle, (document_id, client_hash))
            if throttle is None:
                abort(429, description="Unable to process password attempt")
    elif current_time - throttle.window_started_at >= 900:
        throttle.attempts = 0
        throttle.window_started_at = current_time
    if throttle.attempts >= 10:
        abort(429, description="Too many password attempts. Try again later")
    throttle.attempts += 1
    db.session.commit()


def clear_unlock_failures(document_id: str) -> None:
    throttle = db.session.get(DocumentUnlockThrottle, (document_id, unlock_client_hash()))
    if throttle is not None:
        db.session.delete(throttle)
        db.session.commit()


@api.get("/me")
@authenticated()
def me():
    return jsonify(user=user_json(g.current_user))


@api.get("/api-keys")
@authenticated(browser_only=True)
def list_api_keys():
    keys = db.session.scalars(
        select(ApiKey)
        .where(ApiKey.user_id == g.current_user.id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
    ).all()
    return jsonify(api_keys=[api_key_json(key) for key in keys])


@api.post("/api-keys")
@authenticated(browser_only=True)
def create_api_key():
    body = json_body()
    key, token = issue_api_key(g.current_user, required_text(body, "name", maximum=120))
    payload = api_key_json(key)
    payload["key"] = token
    return jsonify(api_key=payload), 201


@api.delete("/api-keys/<key_id>")
@authenticated(browser_only=True)
def revoke_api_key(key_id: str):
    key = db.session.get(ApiKey, key_id)
    if key is None or key.user_id != g.current_user.id or key.revoked_at is not None:
        abort(404, description="API key not found")
    key.revoked_at = now()
    db.session.commit()
    return "", 204


@api.get("/contacts")
@authenticated()
def list_contacts():
    contacts = db.session.scalars(
        select(Contact).where(Contact.user_id == g.current_user.id).order_by(Contact.name, Contact.email)
    ).all()
    return jsonify(contacts=[contact_json(contact) for contact in contacts])


@api.post("/contacts")
@authenticated()
def create_contact():
    body = json_body()
    name = required_text(body, "name", maximum=160)
    email = required_text(body, "email", maximum=320).lower()
    contact = db.session.scalar(
        select(Contact).where(Contact.user_id == g.current_user.id, Contact.email == email)
    )
    status = 200
    if contact is None:
        contact = Contact(user_id=g.current_user.id, name=name, email=email)
        db.session.add(contact)
        status = 201
    else:
        contact.name = name
    db.session.commit()
    return jsonify(contact=contact_json(contact)), status


@api.delete("/contacts/<contact_id>")
@authenticated()
def delete_contact(contact_id: str):
    contact = db.session.get(Contact, contact_id)
    if contact is None or contact.user_id != g.current_user.id:
        abort(404, description="Contact not found")
    db.session.delete(contact)
    db.session.commit()
    return "", 204


@api.get("/groups")
@authenticated()
def list_groups():
    groups = db.session.scalars(
        select(Group).where(Group.created_by_id == g.current_user.id).order_by(Group.name)
    ).all()
    return jsonify(groups=[group_json(group) for group in groups])


@api.post("/groups")
@authenticated()
def create_group():
    body = json_body()
    group = Group(
        name=required_text(body, "name", maximum=120),
        created_by_id=g.current_user.id,
    )
    db.session.add(group)
    db.session.commit()
    return jsonify(group=group_json(group)), 201


@api.delete("/groups/<group_id>")
@authenticated()
def delete_group(group_id: str):
    group = require_group_owner(g.current_user, group_id)
    db.session.query(DocumentAccess).filter(
        DocumentAccess.principal_type == "group",
        DocumentAccess.principal_id == group.id,
    ).delete(synchronize_session=False)
    db.session.query(GroupRecipient).filter(GroupRecipient.group_id == group.id).delete(
        synchronize_session=False
    )
    db.session.delete(group)
    db.session.commit()
    return "", 204


@api.get("/groups/<group_id>")
@authenticated()
def get_group(group_id: str):
    group = require_group_owner(g.current_user, group_id)
    recipients = db.session.scalars(
        select(GroupRecipient)
        .where(GroupRecipient.group_id == group.id)
        .order_by(GroupRecipient.email)
    ).all()
    return jsonify(
        group=group_json(group),
        emails=[{"id": recipient.id, "email": recipient.email} for recipient in recipients],
    )


@api.post("/groups/<group_id>/emails")
@authenticated()
def add_group_email(group_id: str):
    require_group_owner(g.current_user, group_id)
    body = json_body()
    email = required_text(body, "email", maximum=320).lower()
    recipient = db.session.scalar(
        select(GroupRecipient).where(
            GroupRecipient.group_id == group_id,
            GroupRecipient.email == email,
        )
    )
    if recipient is None:
        recipient = GroupRecipient(group_id=group_id, email=email)
        db.session.add(recipient)
    db.session.commit()
    return jsonify(email={"id": recipient.id, "email": recipient.email}), 201


@api.delete("/groups/<group_id>/emails/<recipient_id>")
@authenticated()
def remove_group_email(group_id: str, recipient_id: str):
    require_group_owner(g.current_user, group_id)
    recipient = db.session.scalar(
        select(GroupRecipient).where(
            GroupRecipient.group_id == group_id,
            GroupRecipient.id == recipient_id,
        )
    )
    if recipient is None:
        abort(404, description="Group email not found")
    db.session.delete(recipient)
    db.session.commit()
    return "", 204


@api.get("/documents")
@authenticated()
def list_documents():
    documents = db.session.scalars(
        viewable_documents(g.current_user).order_by(Document.created_at.desc())
    ).all()
    return jsonify(documents=[document_json(document, g.current_user) for document in documents])


@api.post("/documents")
@authenticated()
def create_document():
    body = json_body()
    title = required_text(body, "title", maximum=200)
    content = required_text(body, "content")
    document_id = new_id()
    document = Document(
        id=document_id,
        created_by_id=g.current_user.id,
        title=title,
        object_key=f"documents/{document_id}/index.html",
        content_version=1,
    )
    db.session.add(document)
    try:
        storage.put(document.object_key, content)
        enqueue_thumbnail(document)
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            storage.delete(document.object_key)
        except Exception:
            current_app.logger.exception("Failed to clean up document content after create error")
        raise
    return jsonify(document=document_json(document, g.current_user)), 201


@api.get("/documents/<document_id>")
@authenticated()
def get_document(document_id: str):
    document = db.session.get(Document, document_id)
    if document is None or not can_view_document(g.current_user, document):
        abort(404, description="Document not found")
    return jsonify(document=document_json(document, g.current_user))


@api.put("/documents/<document_id>")
@authenticated()
def rename_document(document_id: str):
    document = db.session.get(Document, document_id)
    if document is None:
        abort(404, description="Document not found")
    if not can_edit_document(g.current_user, document):
        abort(403, description="Document editing access required")
    document.title = required_text(json_body(), "title", maximum=200)
    document.updated_at = now()
    db.session.commit()
    return jsonify(document=document_json(document, g.current_user))


@api.put("/documents/<document_id>/content")
@authenticated()
def replace_document(document_id: str):
    document = db.session.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )
    if document is None:
        abort(404, description="Document not found")
    if not can_edit_document(g.current_user, document):
        abort(403, description="Document editing access required")
    body = json_body()
    content = required_text(body, "content")
    title = required_text(body, "title", maximum=200) if "title" in body else None
    previous_object_key = document.object_key
    next_version = document.content_version + 1
    next_object_key = f"documents/{document.id}/versions/{next_version}/index.html"
    try:
        storage.put(next_object_key, content)
        document.object_key = next_object_key
        document.content_version = next_version
        enqueue_thumbnail(document)
        if "title" in body:
            document.title = title
        document.updated_at = now()
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            storage.delete(next_object_key)
        except Exception:
            current_app.logger.exception("Failed to clean up document content after update error")
        raise
    if previous_object_key != next_object_key:
        try:
            storage.delete(previous_object_key)
        except Exception:
            current_app.logger.exception("Failed to clean up superseded document content")
    return jsonify(document=document_json(document, g.current_user))


@api.put("/documents/<document_id>/access")
@authenticated()
def replace_document_access(document_id: str):
    document = db.session.get(Document, document_id)
    if document is None:
        abort(404, description="Document not found")
    is_owner = can_manage_document(g.current_user, document)
    if not can_share_document(g.current_user, document):
        abort(403, description="Document sharing access required")
    body = json_body()
    group_ids = body.get("group_ids", [])
    user_emails = body.get("user_emails", [])
    roles = body.get("roles", {})
    if not isinstance(group_ids, list) or not isinstance(user_emails, list) or not isinstance(roles, dict):
        abort(400, description="group_ids and user_emails must be arrays")
    if any(not isinstance(group_id, str) or not group_id for group_id in group_ids):
        abort(400, description="Every group ID must be a non-empty string")
    if any(not isinstance(email, str) or not email.strip() for email in user_emails):
        abort(400, description="Every direct recipient must be a valid email string")
    if any(
        not isinstance(key, str)
        or not isinstance(role, str)
        or role not in {"viewer", "sharer", "editor"}
        for key, role in roles.items()
    ):
        abort(400, description="Access roles must be viewer, sharer, or editor")

    can_edit = can_edit_document(g.current_user, document)
    if not is_owner and not can_edit and any(role == "editor" for role in roles.values()):
        abort(403, description="Editing access is required to grant the editor role")

    available_groups = set(
        db.session.scalars(
            select(Group.id).where(
                Group.created_by_id == g.current_user.id,
                Group.id.in_(group_ids or [""]),
            )
        ).all()
    )
    normalized_emails = {email.strip().lower() for email in user_emails}
    if available_groups != set(group_ids):
        abort(400, description="You can only share with groups you own")

    if is_owner:
        db.session.query(DocumentAccess).filter_by(document_id=document.id).delete()
        for group_id in available_groups:
            role = roles.get(f"group:{group_id}", "sharer")
            db.session.add(
                DocumentAccess(
                    document_id=document.id,
                    principal_type="group",
                    principal_id=group_id,
                    role="sharer" if role == "editor" else role,
                    can_edit=role == "editor",
                )
            )
        for email in normalized_emails:
            if email != g.current_user.email:
                role = roles.get(f"email:{email}", "sharer")
                db.session.add(
                    DocumentAccess(
                        document_id=document.id,
                        principal_type="email",
                        principal_id=email,
                        role="sharer" if role == "editor" else role,
                        can_edit=role == "editor",
                    )
                )
    else:
        if "link" in body:
            abort(403, description="Only the document owner can change public link access")
        existing = {
            (rule.principal_type, rule.principal_id)
            for rule in db.session.scalars(
                select(DocumentAccess).where(DocumentAccess.document_id == document.id)
            ).all()
        }
        for group_id in available_groups:
            if ("group", group_id) not in existing:
                role = roles.get(f"group:{group_id}", "sharer")
                db.session.add(
                    DocumentAccess(
                        document_id=document.id,
                        principal_type="group",
                        principal_id=group_id,
                        role="sharer" if role == "editor" else role,
                        can_edit=role == "editor",
                    )
                )
        for email in normalized_emails:
            if email != g.current_user.email and ("email", email) not in existing:
                role = roles.get(f"email:{email}", "sharer")
                db.session.add(
                    DocumentAccess(
                        document_id=document.id,
                        principal_type="email",
                        principal_id=email,
                        role="sharer" if role == "editor" else role,
                        can_edit=role == "editor",
                    )
                )

    policy = db.session.get(DocumentLinkAccess, document.id)
    link_body = body.get("link")
    if is_owner and link_body is not None:
        if not isinstance(link_body, dict):
            abort(400, description="link must be an object")
        if policy is None:
            policy = DocumentLinkAccess(document_id=document.id, version=1)
            db.session.add(policy)
        enabled = bool(link_body.get("enabled"))
        password_protected = bool(link_body.get("password_protected"))
        password = link_body.get("password")
        previous_password = policy.password
        if password_protected:
            if isinstance(password, str) and password:
                if len(password) > 128:
                    abort(400, description="Link passwords must be 128 characters or fewer")
                policy.password = password
            elif not policy.password:
                abort(400, description="A password is required for password-protected links")
        else:
            policy.password = None
        if policy.enabled != enabled or policy.password != previous_password:
            policy.version += 1
        policy.enabled = enabled
    db.session.commit()
    return "", 204


@api.get("/documents/<document_id>/access")
@authenticated()
def get_document_access(document_id: str):
    document = db.session.get(Document, document_id)
    if document is None:
        abort(404, description="Document not found")
    is_owner = can_manage_document(g.current_user, document)
    if not can_share_document(g.current_user, document):
        abort(403, description="Document sharing access required")
    rules = (
        db.session.scalars(
            select(DocumentAccess).where(DocumentAccess.document_id == document.id)
        ).all()
        if is_owner
        else []
    )
    group_ids = [rule.principal_id for rule in rules if rule.principal_type == "group"]
    user_emails = [rule.principal_id for rule in rules if rule.principal_type == "email"]
    roles = {
        f"{rule.principal_type}:{rule.principal_id}": "editor" if rule.can_edit else rule.role
        for rule in rules
    }
    groups = db.session.scalars(
        select(Group).where(Group.created_by_id == g.current_user.id).order_by(Group.name)
    ).all()
    contacts = db.session.scalars(
        select(Contact).where(Contact.user_id == g.current_user.id).order_by(Contact.name, Contact.email)
    ).all()
    group_recipients = db.session.scalars(
        select(GroupRecipient).where(GroupRecipient.group_id.in_([group.id for group in groups] or [""]))
    ).all()
    recipients_by_group = {
        group.id: sorted(recipient.email for recipient in group_recipients if recipient.group_id == group.id)
        for group in groups
    }
    return jsonify(
        access={
            "group_ids": sorted(group_ids),
            "user_emails": sorted(user_emails),
            "roles": roles,
        },
        can_manage=is_owner,
        can_edit=can_edit_document(g.current_user, document),
        link=link_access_json(
            db.session.get(DocumentLinkAccess, document.id), include_password=is_owner
        ),
        groups=[{**group_json(group), "recipients": recipients_by_group[group.id]} for group in groups],
        contacts=[contact_json(contact) for contact in contacts],
    )


@api.delete("/documents/<document_id>")
@authenticated()
def delete_document(document_id: str):
    document = db.session.get(Document, document_id)
    if document is None:
        abort(404, description="Document not found")
    if not can_manage_document(g.current_user, document):
        abort(403, description="Document management access required")
    object_key = document.object_key
    thumbnail_object_key = document.thumbnail_object_key
    db.session.delete(document)
    db.session.commit()
    try:
        storage.delete(object_key)
        if thumbnail_object_key:
            storage.delete(thumbnail_object_key)
    except Exception:
        current_app.logger.exception("Failed to clean up deleted document content")
    return "", 204


@api.get("/document-thumbnails/<document_id>/<int:version>")
def get_document_thumbnail(document_id: str, version: int):
    require_surface("app")
    token = request.args.get("token", "")
    try:
        payload = thumbnail_serializer().loads(
            token,
            max_age=current_app.config["THUMBNAIL_URL_SECONDS"],
        )
    except (BadSignature, SignatureExpired):
        abort(401, description="Thumbnail URL expired or invalid")
    if payload != {"document_id": document_id, "version": version}:
        abort(401, description="Thumbnail URL does not match")
    document = db.session.get(Document, document_id)
    if (
        document is None
        or document.thumbnail_version != version
        or not document.thumbnail_object_key
    ):
        abort(404, description="Thumbnail not found")
    try:
        content = storage.get_bytes(document.thumbnail_object_key)
    except FileNotFoundError:
        abort(404, description="Thumbnail not found")
    return Response(
        content,
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@api.post("/documents/<document_id>/render")
@authenticated(browser_only=True)
def create_render_ticket(document_id: str):
    document = db.session.get(Document, document_id)
    if document is None or not can_view_document(g.current_user, document):
        abort(404, description="Document not found")
    token = render_serializer().dumps({"document_id": document.id, "user_id": g.current_user.id})
    return jsonify(url=f"{document_content_origin(document)}/_render?token={token}")


@api.get("/public/documents/<document_id>")
def get_public_document(document_id: str):
    require_surface("app")
    document = db.session.get(Document, document_id)
    policy = db.session.get(DocumentLinkAccess, document_id)
    if document is None or policy is None or not policy.enabled:
        abort(404, description="Public document not found")
    return jsonify(
        document={
            "id": document.id,
            "title": document.title,
            "url": f"{current_app.config['APP_PUBLIC_URL']}/documents/{document.id}",
        },
        link=link_access_json(policy),
    )


@api.post("/public/documents/<document_id>/unlock")
def unlock_public_document(document_id: str):
    require_surface("app")
    document = db.session.get(Document, document_id)
    policy = db.session.get(DocumentLinkAccess, document_id)
    if document is None or policy is None or not policy.enabled:
        abort(404, description="Public document not found")
    if policy.password:
        body = json_body()
        password = body.get("password")
        password_matches = isinstance(password, str) and hmac.compare_digest(policy.password, password)
        if not password_matches:
            record_unlock_failure(document.id)
            abort(401, description="Incorrect document password")
        clear_unlock_failures(document.id)
    token = public_access_serializer().dumps({"document_id": document.id, "version": policy.version})
    return jsonify(access_token=token)


@api.post("/public/documents/<document_id>/render")
def create_public_render_ticket(document_id: str):
    require_surface("app")
    document = db.session.get(Document, document_id)
    policy = db.session.get(DocumentLinkAccess, document_id)
    if document is None or policy is None or not policy.enabled:
        abort(404, description="Public document not found")
    if policy.password:
        body = json_body()
        access_token = body.get("access_token")
        if not isinstance(access_token, str):
            abort(401, description="Document password required")
        try:
            payload = public_access_serializer().loads(
                access_token,
                max_age=current_app.config["PUBLIC_ACCESS_TOKEN_SECONDS"],
            )
        except SignatureExpired:
            abort(401, description="Document access expired")
        except BadSignature:
            abort(401, description="Invalid document access")
        if payload.get("document_id") != document.id or payload.get("version") != policy.version:
            abort(401, description="Document access is no longer valid")
    token = render_serializer().dumps(
        {"document_id": document.id, "public": True, "version": policy.version}
    )
    return jsonify(url=f"{document_content_origin(document)}/_render?token={token}")
