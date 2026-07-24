# ShareHTML

ShareHTML publishes JavaScript-enabled HTML documents to isolated origins and shares them with people, reusable groups, or public links.

The MVP runs as one Flask service. Requests are split by hostname:

```text
app.sharehtml.com                    -> app and API
{document_id}.sharehtmlusercontent.com -> isolated document runtime
```

Document IDs have no hostname prefix.

## Local Development

`app.localtest.me` and `*.lvh.me` resolve to `127.0.0.1`, so wildcard DNS setup is not required locally.

Create the Python environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/flask --app sharehtml:create_app db upgrade
```

Start Flask:

```bash
APP_ENV=development \
.venv/bin/flask --app sharehtml:create_app run --host 0.0.0.0 --port 5000
```

Start Vite in another terminal:

```bash
npm --prefix frontend install
npm --prefix frontend run dev -- --host 0.0.0.0
```

Open [http://app.localtest.me:5173](http://app.localtest.me:5173).

Without Clerk configuration, Vite sends `X-Dev-User: dev@sharehtml.local` to Flask. This development identity is rejected when `APP_ENV` is not `development`. When Clerk is configured, the development header is disabled and normal Clerk bearer authentication is used.

SQLite and filesystem document storage are the defaults. To use local PostgreSQL:

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+psycopg://sharehtml:sharehtml@localhost:5432/sharehtml
```

## Agent API

Create an API key in the dashboard and provide it to the agent as a secret:

```bash
export SHAREHTML_API_KEY="sh_live_..."
export SHAREHTML_API_URL="http://app.localtest.me:5000/api/v1"
```

All agent requests use:

```http
Authorization: Bearer $SHAREHTML_API_KEY
```

The key acts as its user and inherits that user's current document and group permissions. Keys can be independently revoked.

Core agent endpoints:

```text
GET    /api/v1/documents
POST   /api/v1/documents
GET    /api/v1/documents/{id}
PUT    /api/v1/documents/{id}
PUT    /api/v1/documents/{id}/content
GET    /api/v1/documents/{id}/access
PUT    /api/v1/documents/{id}/access
DELETE /api/v1/documents/{id}
```

Contacts are private, user-owned name and email records for people you regularly share with.

```text
GET    /api/v1/contacts
POST   /api/v1/contacts
DELETE /api/v1/contacts/{id}
```

Groups are private, user-owned email lists. Addresses do not need an account when they are added; access activates when a user signs in with that verified email.

```text
GET  /api/v1/groups
POST /api/v1/groups
DELETE /api/v1/groups/{id}
POST /api/v1/groups/{id}/emails
DELETE /api/v1/groups/{id}/emails/{recipient_id}
```

Documents must be one self-contained HTML file. Inline all scripts, styles, images, SVG, fonts, and data. Separate asset bundles are not supported.

Document recipients have either a `viewer` or `sharer` role. New grants default to `sharer`. Viewers can open the document. Sharers can add recipients with either role, while only the owner can change existing roles, remove existing access, configure public links, update content, or delete the document. Set roles with keys such as `email:person@example.com` or `group:{group_id}` in the access payload's `roles` object.

## Railway

Create one Railway service from the root `Dockerfile`, one PostgreSQL resource, and one Bucket. Add both custom domains to the web service:

```text
app.sharehtml.com
*.sharehtmlusercontent.com
```

Set these production variables:

```env
APP_ENV=production
APP_HOST=app.sharehtml.com
APP_PUBLIC_URL=https://app.sharehtml.com
CONTENT_HOST_SUFFIX=.sharehtmlusercontent.com
CONTENT_PUBLIC_SCHEME=https
CONTENT_PUBLIC_PORT=443
RENDER_TICKET_SECONDS=300
PUBLIC_ACCESS_TOKEN_SECONDS=3600
TRUST_PROXY_HOST=true
STORAGE_BACKEND=s3
DATABASE_URL=${{Postgres.DATABASE_URL}}
CLERK_AUTHORIZED_PARTIES=https://app.sharehtml.com
S3_ENDPOINT=${{Bucket.ENDPOINT}}
S3_REGION=${{Bucket.REGION}}
S3_BUCKET=${{Bucket.BUCKET}}
S3_ACCESS_KEY_ID=${{Bucket.ACCESS_KEY_ID}}
S3_SECRET_ACCESS_KEY=${{Bucket.SECRET_ACCESS_KEY}}
```

Also set strong random values for `SECRET_KEY` and `API_KEY_PEPPER`. Browser authentication requires `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY` (or an explicit `CLERK_ISSUER`), and `VITE_CLERK_PUBLISHABLE_KEY` at frontend build time. Production startup rejects SQLite, local document storage, HTTP public URLs, incomplete bucket settings, and untrusted proxy configuration. Railway's conventional PostgreSQL URL is normalized automatically for Psycopg 3.

`railway.toml` runs versioned database migrations before each deployment:

```bash
flask --app sharehtml:create_app db upgrade
```

Railway uses `/ready` for deployment health checks. This endpoint verifies database connectivity, the current migration revision, and bucket access. `/health` remains a process-only liveness check.

## Security Model

- Every document uses its ID as a unique hostname.
- API and application routes reject document hostnames.
- The trusted app viewer embeds document content in a sandboxed cross-origin iframe.
- Document responses block external network access through CSP.
- Each iframe load uses a short-lived signed render ticket instead of a third-party cookie.
- The viewer creates a fresh ticket for reload and raw-document actions.
- Anyone-with-link access can be open or protected by a reusable password. The owner can retrieve the current password from the share panel; this intentionally favors resharing convenience over protection from database readers.
- Password unlock tokens stay in browser session storage and are never placed in URLs.
- Failed password attempts are throttled per document and client address.
- The content domain never receives agent API keys or application cookies.
