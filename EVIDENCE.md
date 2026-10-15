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

## Rate limiting returns 429 under a burst, per IP and per widget, and the API keeps serving legitimate traffic

Per-IP limit (5 requests per 10 seconds per visitor IP), 12 rapid submissions from one IP:

    requests 1-5  -> 201 Created
    requests 6-12 -> 429 Too Many Requests
    13th request:
    HTTP/1.1 429 Too Many Requests
    retry-after: 6
    access-control-allow-origin: *
    {"detail":"Too many requests (per-IP limit). Try again in 6s."}

Legitimate traffic is unaffected:

    submission from a different visitor IP (203.0.113.7) -> 201
    GET /health during the flood                         -> 200
    same IP after waiting 11 seconds                     -> 201

Per-widget limit (30 per 10 seconds per widget). tools/burst_test.py sends 40 submissions from 40 different visitor IPs to one widget:

    {201: 30, 429: 10}     (40 submissions in 0.7 s)

The limit is configurable. With RATE_LIMIT_WIDGET_MAX=5 the same burst gives:

    {201: 5, 429: 35}

Limitation: the counters are in memory, so they reset on restart and are not shared between server processes.

## Honeypot spam control blocks a bot submission

A submission with the hidden field "website" filled in gets the same response as a real one, so the bot learns nothing:

    POST /submissions (website: "http://spam.example") -> 201 {"id":"56fb7682-...","status":"stored"}

The row is kept but marked, with no field values stored, so the dashboard can exclude it:

    ('flagged_spam', '203.0.113.9', '{}', '56fb7682')
    ('stored', '127.0.0.1', '{"email": "visitor@example.com"}', 'e77f4106')

## Rate limiting returns 429 under a burst, per IP and per widget, and the API keeps serving legitimate traffic

Per-IP limit (5 requests per 10 seconds per visitor IP), 12 rapid submissions from one IP:

    requests 1-5  -> 201 Created
    requests 6-12 -> 429 Too Many Requests
    13th request:
    HTTP/1.1 429 Too Many Requests
    retry-after: 6
    access-control-allow-origin: *
    {"detail":"Too many requests (per-IP limit). Try again in 6s."}

Legitimate traffic is unaffected:

    submission from a different visitor IP (203.0.113.7) -> 201
    GET /health during the flood                         -> 200
    same IP after waiting 11 seconds                     -> 201

Per-widget limit (30 per 10 seconds per widget). tools/burst_test.py sends 40 submissions from 40 different visitor IPs to one widget:

    {201: 30, 429: 10}     (40 submissions in 0.7 s)

The limit is configurable. With RATE_LIMIT_WIDGET_MAX=5 the same burst gives:

    {201: 5, 429: 35}

Limitation: the counters are in memory, so they reset on restart and are not shared between server processes.

## Honeypot spam control blocks a bot submission

A submission with the hidden field "website" filled in gets the same response as a real one, so the bot learns nothing:

    POST /submissions (website: "http://spam.example") -> 201 {"id":"56fb7682-...","status":"stored"}

The row is kept but marked, with no field values stored, so the dashboard can exclude it:

    ('flagged_spam', '203.0.113.9', '{}', '56fb7682')
    ('stored', '127.0.0.1', '{"email": "visitor@example.com"}', 'e77f4106')

## Geo lookup with provider fallback (A to B)

Providers are mocked via GEO_MOCK_A and GEO_MOCK_B. Private IPs skip the providers. A failed lookup never fails the submission.

### Unit proof (tools/geo_proof.py)

```text

== A answers (A=ok, B=ok, ip=8.8.8.8)
  result: {'country': 'Mockland-A', 'city': 'Mockville-A', 'provider': 'A'}

== A fails, B answers (A=fail, B=ok, ip=8.8.8.8)
  log: WARNING geo provider A failed for 8.8.8.8: mock provider A forced to fail
  result: {'country': 'Mockland-B', 'city': 'Mockville-B', 'provider': 'B'}

== both fail (A=fail, B=fail, ip=8.8.8.8)
  log: WARNING geo provider A failed for 8.8.8.8: mock provider A forced to fail
  log: WARNING geo provider B failed for 8.8.8.8: mock provider B forced to fail
  log: ERROR all geo providers failed for 8.8.8.8
  result: None

== private IP skips providers (A=ok, B=ok, ip=127.0.0.1)
  result: None
```n
### End-to-end proof (tools/geo_e2e.py, live server, X-Forwarded-For 8.8.8.8)

```text
== both providers fail (ip=8.8.8.8)
  HTTP 201 {'id': 'e6f791c5-e55c-4d8f-a8dc-20ed0d085c62', 'status': 'stored'}
  stored row (ip, country, city, status): ('8.8.8.8', None, None, 'stored')
== A fails, B answers (ip=8.8.8.8)
  HTTP 201 {'id': 'f9d535f8-e65f-4db4-9ef0-154b358299b2', 'status': 'stored'}
  stored row (ip, country, city, status): ('8.8.8.8', 'Mockland-B', 'Mockville-B', 'stored')
== A answers (ip=8.8.8.8)
  HTTP 201 {'id': '562bc182-0852-4d94-90e3-cb53ce1b2f1a', 'status': 'stored'}
  stored row (ip, country, city, status): ('8.8.8.8', 'Mockland-A', 'Mockville-A', 'stored')
```n
