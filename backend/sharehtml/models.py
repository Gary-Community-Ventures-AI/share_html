from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True, default=new_id)
    external_id: Mapped[str | None] = mapped_column(db.String(255), unique=True)
    email: Mapped[str] = mapped_column(db.String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(db.String(160))
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)


class Contact(db.Model):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("user_id", "email"),)

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(db.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(db.String(160))
    email: Mapped[str] = mapped_column(db.String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)


class Group(db.Model):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("created_by_id", "name"),)

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True, default=new_id)
    created_by_id: Mapped[str] = mapped_column(db.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(db.String(120))
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)


class GroupRecipient(db.Model):
    __tablename__ = "group_recipients"
    __table_args__ = (UniqueConstraint("group_id", "email"),)

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(db.ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(db.String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)


class Document(db.Model):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True, default=new_id)
    created_by_id: Mapped[str] = mapped_column(db.ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(db.String(200))
    object_key: Mapped[str] = mapped_column(db.String(500), unique=True)
    content_version: Mapped[int] = mapped_column(default=1, server_default="1")
    thumbnail_version: Mapped[int | None] = mapped_column()
    thumbnail_object_key: Mapped[str | None] = mapped_column(db.String(500))
    thumbnail_status: Mapped[str] = mapped_column(db.String(16), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now, onupdate=now)


class ThumbnailJob(db.Model):
    __tablename__ = "thumbnail_jobs"

    document_id: Mapped[str] = mapped_column(
        db.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    content_version: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(db.String(16), default="pending", server_default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now, index=True)
    lease_owner: Mapped[str | None] = mapped_column(db.String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True), index=True)
    error: Mapped[str | None] = mapped_column(db.String(1000))
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now, onupdate=now)


class DocumentAccess(db.Model):
    __tablename__ = "document_access"
    __table_args__ = (
        UniqueConstraint("document_id", "principal_type", "principal_id"),
        CheckConstraint("principal_type in ('group', 'email')"),
        CheckConstraint("role in ('viewer', 'sharer')"),
    )

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(db.ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    principal_type: Mapped[str] = mapped_column(db.String(16))
    principal_id: Mapped[str] = mapped_column(db.String(320), index=True)
    role: Mapped[str] = mapped_column(db.String(16), default="sharer", server_default="sharer")
    can_edit: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)


class DocumentLinkAccess(db.Model):
    __tablename__ = "document_link_access"

    document_id: Mapped[str] = mapped_column(
        db.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=False)
    password: Mapped[str | None] = mapped_column("password_hash", db.String(255))
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now, onupdate=now)


class DocumentUnlockThrottle(db.Model):
    __tablename__ = "document_unlock_throttles"

    document_id: Mapped[str] = mapped_column(
        db.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    client_hash: Mapped[str] = mapped_column(db.String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(default=0)
    window_started_at: Mapped[int] = mapped_column()


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(db.String(32), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(db.String(24), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(db.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(db.String(120))
    secret_hash: Mapped[str] = mapped_column(db.String(64))
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
