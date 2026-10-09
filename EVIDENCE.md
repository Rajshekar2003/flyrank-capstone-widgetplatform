# Evidence

One pasted proof per requirement, added as each is built. Tokens are redacted.

## Authenticated CRUD endpoints for widgets; requests without valid auth are rejected

Request with no Authorization header (POST /widgets):

    HTTP/1.1 401 Unauthorized
    date: Thu, 08 Oct 2026 09:55:34 GMT
    server: uvicorn
    content-length: 54
    content-type: application/json
    
    {"detail":"Missing or malformed Authorization header"}

Authenticated create, list and read are shown in the tenant-isolation section below.
Update and delete proofs will be added once tested.

## Multi-tenant isolation proven: tenant A cannot read or modify tenant B widgets

Owner 1 creates a widget (POST /widgets, owner 1 token) -> 201:

    {"id":"6243574c-3b9c-4df6-af03-ab8a67978566","owner_id":"27948dba-4855-4e3a-a8a1-bbe72d41a593","type":"signup_form","title":"Newsletter Signup","description":null,"form_fields":[{"name":"email","label":"Email","type":"email","required":true}],"button_text":"Submit","display_options":{"color":"#0f3d3a","position":"bottom-right"},"created_at":"2026-10-07T10:01:46.037197+00:00"}

Owner 2 (a different account) tries to read owner 1's widget:

    GET /widgets/6243574c-3b9c-4df6-af03-ab8a67978566   (owner 2 token)
    HTTP/1.1 404 Not Found
    {"detail":"Widget 6243574c-3b9c-4df6-af03-ab8a67978566 not found"}

Owner 2's own widget list does not leak owner 1's widget:

    GET /widgets   (owner 2 token)
    HTTP/1.1 200 OK
    []

Owner 1 can still read their own widget:

    GET /widgets/6243574c-3b9c-4df6-af03-ab8a67978566   (owner 1 token)
    HTTP/1.1 200 OK
    (full widget JSON, owner_id 27948dba-4855-4e3a-a8a1-bbe72d41a593)

## Embed snippet generated per widget

GET /widgets/{id}/embed with owner 1 token:

    HTTP/1.1 200 OK
    {"widget_id":"6243574c-3b9c-4df6-af03-ab8a67978566","snippet":"<script src=\"http://localhost:8000/widget.js?id=6243574c-3b9c-4df6-af03-ab8a67978566\"></script>"}

Same request with owner 2 token: HTTP/1.1 404 Not Found. With no token: HTTP/1.1 401 Unauthorized.

## Widget update and delete, including cross-tenant modification attempts

Owner 1 created a throwaway widget (2f34b057-0461-41d1-93a5-df7f5740a5b3), then:

    PUT    (owner 1) -> 200 OK, title "Renamed widget"
    PUT    (owner 2) -> 404 Not Found
    GET    (owner 1) -> 200 OK, title still "Renamed widget" (owner 2 attempt changed nothing)
    DELETE (owner 2) -> 404 Not Found
    DELETE (owner 1) -> 204 No Content
    GET    (owner 1) -> 404 Not Found

## Cross-origin submissions work: CORS headers correct, preflight (OPTIONS) handled

A submission sent with an Origin header from a different origin (http://localhost:5500):

    POST /submissions   (Origin: http://localhost:5500)
    HTTP/1.1 201 Created
    access-control-allow-origin: *
    {"id":"aa6befc7-0764-4522-a62b-8b9d4a1758a7","status":"stored"}

The preflight request:

    OPTIONS /submissions   (Origin: http://localhost:5500, Access-Control-Request-Method: POST, Access-Control-Request-Headers: content-type)
    HTTP/1.1 200 OK
    access-control-allow-origin: *
    access-control-allow-methods: GET, POST, OPTIONS
    access-control-allow-headers: Accept, Accept-Language, Content-Language, Content-Type
    access-control-max-age: 600

The Authorization header is deliberately not allowed cross-origin, so the owner API cannot be called from a customer website in a browser.
These are curl checks with an Origin header. Proof from a real browser on a second origin is added with the test page.

## All incoming input validated; malformed and oversized payloads rejected with 4xx and JSON errors

    missing required field    -> 400 {"detail":"Field 'email' is required"}
    invalid email             -> 400 {"detail":"Field 'email' must be a valid email address"}
    unknown field             -> 400 {"detail":"Unknown field(s): phone"}
    unknown widget            -> 404 {"detail":"Widget not found"}
    malformed JSON            -> 400 {"detail":"Body must be valid JSON"}
    oversized payload (20 KB) -> 413 {"detail":"Payload too large (max 10000 bytes)"}
    deeply nested JSON bomb   -> 400 {"detail":"Body must be valid JSON"}

No request produced a 500.
