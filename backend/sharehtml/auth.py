from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from functools import wraps
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import jwt
from flask import abort, current_app, g, request
from jwt import PyJWKClient
from sqlalchemy import select

from .extensions import db
from .host import require_surface
from .models import ApiKey, User, now


def api_key_digest(secret: str) -> str:
    pepper = current_app.config["API_KEY_PEPPER"].encode()
    return hmac.new(pepper, secret.encode(), hashlib.sha256).hexdigest()


def issue_api_key(user: User, name: str) -> tuple[ApiKey, str]:
    public_id = secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    token = f"sh_live_{public_id}.{secret}"
    key = ApiKey(
        public_id=public_id,
        user_id=user.id,
        name=name,
        secret_hash=api_key_digest(secret),
    )
    db.session.add(key)
    db.session.commit()
    return key, token


def authenticate_api_key(token: str) -> User | None:
    if not token.startswith("sh_live_") or "." not in token:
        return None
    prefix, secret = token.split(".", 1)
    public_id = prefix.removeprefix("sh_live_")
    key = db.session.scalar(select(ApiKey).where(ApiKey.public_id == public_id))
    if key is None or key.revoked_at is not None:
        return None
    if key.expires_at is not None and key.expires_at <= now():
        return None
    if not hmac.compare_digest(key.secret_hash, api_key_digest(secret)):
        return None
    key.last_used_at = now()
    db.session.commit()
    return db.session.get(User, key.user_id)


def authenticate_clerk(token: str) -> User | None:
    issuer = current_app.config["CLERK_ISSUER"]
    if not issuer:
        return None
    signing_key = PyJWKClient(f"{issuer}/.well-known/jwks.json").get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        leeway=60,
        options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
    )
    authorized_party = str(claims.get("azp", "")).rstrip("/")
    if authorized_party not in current_app.config["CLERK_AUTHORIZED_PARTIES"]:
        raise jwt.InvalidTokenError("Token authorized party is not allowed")
    external_id = claims["sub"]
    user = db.session.scalar(select(User).where(User.external_id == external_id))
    if user is None:
        secret_key = current_app.config["CLERK_SECRET_KEY"]
        clerk_request = Request(
            f"https://api.clerk.com/v1/users/{external_id}",
            headers={
                "Authorization": f"Bearer {secret_key}",
                "User-Agent": "ShareHTML/0.1",
            },
        )
        try:
            with urlopen(clerk_request, timeout=5) as response:
                clerk_user = json.load(response)
        except (HTTPError, URLError):
            current_app.logger.exception("Clerk user lookup failed")
            abort(503, description="Identity service unavailable")
        primary_email_id = clerk_user.get("primary_email_address_id")
        primary_email = next(
            (
                item
                for item in clerk_user.get("email_addresses", [])
                if item.get("id") == primary_email_id
            ),
            None,
        )
        if (
            not primary_email
            or not primary_email.get("email_address")
            or primary_email.get("verification", {}).get("status") != "verified"
        ):
            abort(401, description="A verified primary email is required")
        email = primary_email.get("email_address")
        name = " ".join(
            part for part in [clerk_user.get("first_name"), clerk_user.get("last_name")] if part
        ) or None
        user = User(external_id=external_id, email=email.lower(), name=name)
        db.session.add(user)
        db.session.commit()
    return user


def authenticate_request() -> tuple[User, str]:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token.startswith("sh_live_"):
            user = authenticate_api_key(token)
            if user:
                return user, "api_key"
        else:
            try:
                user = authenticate_clerk(token)
            except jwt.PyJWTError as error:
                if current_app.config["APP_ENV"] == "development":
                    current_app.logger.warning("Clerk JWT rejected: %s", error)
                user = None
            if user:
                return user, "browser"

    if current_app.config["APP_ENV"] == "development":
        email = request.headers.get("X-Dev-User")
        if email:
            normalized = email.strip().lower()
            user = db.session.scalar(select(User).where(User.email == normalized))
            if user is None:
                user = User(email=normalized, name="Local developer")
                db.session.add(user)
                db.session.commit()
            return user, "development"

    abort(401, description="Authentication required")


def authenticated(*, browser_only: bool = False):
    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            require_surface("app")
            user, auth_kind = authenticate_request()
            if browser_only and auth_kind == "api_key":
                abort(403, description="A browser session is required")
            g.current_user = user
            g.auth_kind = auth_kind
            return function(*args, **kwargs)

        return wrapped

    return decorator
