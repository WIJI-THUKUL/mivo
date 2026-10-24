---
name: rest-api
description: Design and call HTTP/REST APIs - routes, status codes, auth, errors, requests usage. Use when building or consuming an API.
triggers: api, rest, endpoint, flask, fastapi, server
---
# REST APIs
- Resources as nouns: `GET /users`, `GET /users/{id}`, `POST /users`, `PATCH /users/{id}`, `DELETE /users/{id}`.
- Status codes: 200 ok, 201 created, 204 no content, 400 bad input, 401 unauthenticated, 403 forbidden, 404 missing, 409 conflict, 422 validation, 500 server error.
- Return consistent JSON errors: `{"error": {"code": "...", "message": "..."}}`. Validate all input.
- Auth: tokens in the `Authorization: Bearer` header; never in URLs; secrets from environment variables.
- Python server: Flask/FastAPI (check what's installable in Termux; `http.server` for trivial cases).
- Client: always set a timeout, check `response.status_code`, handle `requests.RequestException`, retry with backoff only on 429/5xx.
