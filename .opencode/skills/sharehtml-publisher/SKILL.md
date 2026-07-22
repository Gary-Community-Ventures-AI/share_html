---
name: sharehtml-publisher
description: Publish and manage ShareHTML HTML documents through the REST API. Use when the user asks to publish, host, update, list, share, or delete an HTML document with ShareHTML.
---

# ShareHTML Publisher

Use the ShareHTML REST API. Do not place credentials in files, commands shown to the user, HTML content, query parameters, or logs.

Required environment variables:

```text
SHAREHTML_API_KEY
SHAREHTML_API_URL
```

Default the API URL to `https://app.sharehtml.com/api/v1` when it is not set. Send the key only through this header:

```http
Authorization: Bearer $SHAREHTML_API_KEY
```

## Workflow

1. Read the complete HTML document.
2. Publish with `POST /documents`.
3. Return the document ID and trusted viewer URL from the response.

Publish JSON:

```json
{
  "title": "Document title",
  "content": "<!DOCTYPE html>..."
}
```

Replace content with `PUT /documents/{document_id}/content` using the same JSON shape.

List documents with `GET /documents`.

List the user's private email groups with `GET /groups`. Each group is a reusable set of email recipients owned only by that user. Add addresses with `POST /groups/{group_id}/emails` using `{ "email": "person@example.com" }`; the address does not need an existing account.

Delete only after explicit user confirmation with `DELETE /documents/{document_id}`.

Set access with `PUT /documents/{document_id}/access`:

```json
{
  "group_ids": ["group-id"],
  "user_emails": ["person@example.com"],
  "roles": {
    "group:group-id": "viewer",
    "email:person@example.com": "sharer"
  },
  "link": {
    "enabled": false,
    "password_protected": false
  }
}
```

Roles are `viewer` or `sharer`. New grants default to `sharer` when no role is supplied. Sharers can add recipients with either role, but only the document owner can change existing roles, remove existing access, or change public-link settings.

Only enable anyone-with-link access when the user explicitly requests it. To protect a new public link, set `password_protected` to `true` and provide a `password` of at least eight characters. Never invent, display, or store a document password without the user's explicit direction.

Documents can execute JavaScript but cannot contact external services. Publish exactly one self-contained HTML file. Inline every required script, stylesheet, SVG, image, font, and data payload. Do not create or reference a separate asset bundle.

Never expose `SHAREHTML_API_KEY` inside published content.
