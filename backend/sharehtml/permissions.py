from __future__ import annotations

from flask import abort
from sqlalchemy import and_, or_, select

from .extensions import db
from .models import Document, DocumentAccess, Group, GroupRecipient, User


def require_group_owner(user: User, group_id: str) -> Group:
    group = db.session.get(Group, group_id)
    if group is None:
        abort(404, description="Group not found")
    if group.created_by_id != user.id:
        abort(403, description="Group owner access required")
    return group


def viewable_documents(user: User):
    group_ids = select(GroupRecipient.group_id).where(GroupRecipient.email == user.email)
    shared_document_ids = select(DocumentAccess.document_id).where(
        or_(
            and_(
                DocumentAccess.principal_type == "email",
                DocumentAccess.principal_id == user.email,
            ),
            and_(
                DocumentAccess.principal_type == "group",
                DocumentAccess.principal_id.in_(group_ids),
            ),
        )
    )
    return select(Document).where(
        or_(Document.created_by_id == user.id, Document.id.in_(shared_document_ids))
    )


def can_view_document(user: User, document: Document) -> bool:
    if document.created_by_id == user.id:
        return True

    group_ids = select(GroupRecipient.group_id).where(GroupRecipient.email == user.email)
    access = db.session.scalar(
        select(DocumentAccess.id).where(
            DocumentAccess.document_id == document.id,
            or_(
                and_(
                    DocumentAccess.principal_type == "email",
                    DocumentAccess.principal_id == user.email,
                ),
                and_(
                    DocumentAccess.principal_type == "group",
                    DocumentAccess.principal_id.in_(group_ids),
                ),
            ),
        )
    )
    return access is not None


def can_share_document(user: User, document: Document) -> bool:
    if document.created_by_id == user.id:
        return True

    group_ids = select(GroupRecipient.group_id).where(GroupRecipient.email == user.email)
    access = db.session.scalar(
        select(DocumentAccess.id).where(
            DocumentAccess.document_id == document.id,
            DocumentAccess.role == "sharer",
            or_(
                and_(
                    DocumentAccess.principal_type == "email",
                    DocumentAccess.principal_id == user.email,
                ),
                and_(
                    DocumentAccess.principal_type == "group",
                    DocumentAccess.principal_id.in_(group_ids),
                ),
            ),
        )
    )
    return access is not None


def can_manage_document(user: User, document: Document) -> bool:
    return document.created_by_id == user.id
