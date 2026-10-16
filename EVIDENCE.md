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
```
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
```

## Webhook side effect that may fail (notify.py)

The webhook runs after the 201 is returned (FastAPI BackgroundTasks), only for stored submissions. A failure is logged without the URL or the payload and never affects the response. The target URL comes from the NOTIFY_WEBHOOK_URL env var, not from widget owners.

### Unit proof (tools/notify_proof.py)

```text
== not configured (disabled)
  result: skipped

== mock ok
  result: sent

== mock fail
  log: WARNING webhook delivery failed: RuntimeError: mock webhook forced to fail
  result: failed

== real URL, nothing listening
  log: WARNING webhook delivery failed: URLError: <urlopen error timed out>
  result: failed

== bad URL scheme
  log: WARNING webhook delivery failed: ValueError: webhook URL must start with http:// or https://
  result: failed

== outbox file after the run
{"event":"submission.created","submission_id":"sub-1","widget_id":"widget-1","fields":{"email":"visitor@example.com"}}

== signature: sha256=5910e62016ef5... | deterministic: True | differs by secret: True
```

### End-to-end proof (tools/notify_e2e.py, live server)

```text
== webhook ok (ip=9.9.9.7)
  HTTP 201 {'id': '02135b78-5d0d-4369-823b-a2b6722837d6', 'status': 'stored'} in 145 ms
  webhook outbox lines for this submission: 1
== honeypot spam (ip=9.9.9.8)
  HTTP 201 {'id': 'dc156b5d-5a2d-48b4-ae7f-f7db8e934d6e', 'status': 'stored'} in 69 ms
  webhook outbox lines for this submission: 0
== webhook fails (ip=9.9.9.9)
  HTTP 201 {'id': '1d3cd949-33df-4d17-8927-9b99d7f25126', 'status': 'stored'} in 158 ms
  webhook outbox lines for this submission: 0
```

## Cached, versioned widget.js and public widget config

widget.js is served from static/widget.js. Its version is a content hash, and the embed snippet now carries it as ?v=. A URL with the current version is cached for a year (immutable). A missing or stale version gets a 5 minute cache, so a wrong v can never pin old code. Both endpoints send an ETag and answer conditional requests with 304. GET /widgets/{id}/config is public, returns only what a visitor needs (no owner_id), and Retry-After is exposed to browsers so the widget can show a retry time on 429.

### Server-side proof (tools/widget_proof.py, live server)

```text
== 1 widget.js, no version in URL
  status: 200 | body bytes: 5950
  content-type: application/javascript
  cache-control: public, max-age=300
  etag: "8fe14dbeb4fa"
== 2 widget.js, current version in URL
  status: 200 | body bytes: 5950
  content-type: application/javascript
  cache-control: public, max-age=31536000, immutable
  etag: "8fe14dbeb4fa"
== 3 widget.js, stale version in URL
  status: 200 | body bytes: 5950
  content-type: application/javascript
  cache-control: public, max-age=300
  etag: "8fe14dbeb4fa"
== 4 widget.js, conditional request
  status: 304 | body bytes: 0
  etag: "8fe14dbeb4fa"
  cache-control: public, max-age=31536000, immutable
== 5 public config, from another origin
  status: 200 | body bytes: 280
  content-type: application/json
  cache-control: public, max-age=60
  etag: "467d3abc526348eb"
  access-control-allow-origin: *
  access-control-expose-headers: Retry-After
  keys: ['button_text', 'description', 'display_options', 'form_fields', 'id', 'title', 'type']
  owner_id exposed: False
== 6 public config, conditional request
  status: 304 | body bytes: 0
  etag: "467d3abc526348eb"
== 7 unknown widget
  status: 404 | body bytes: 29
```

## Second-origin test page (real browser)

tools/testpage/index.html is served by `python -m http.server 9000 --directory tools\testpage`, so the page origin (localhost:9000) differs from the API (localhost:8000). It embeds two widgets with the snippets the API returns: an inline signup_form and a cta_popover positioned top-left.

Observed in the browser: both widgets render, a submit from each shows the thank-you message, and the rows are stored (listed below by widget, IP and status only; field values are left out because they contain a real email address).

```text
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 6243574c | ip 127.0.0.1 | stored
widget 4de78d7a | ip 127.0.0.1 | stored
```

### Cross-origin rate limit (tools/cors_429_proof.py, Origin: http://localhost:9000)

Requests 1 to 5 are accepted, 6 and 7 get 429 with Retry-After, and Retry-After is exposed to the browser through Access-Control-Expose-Headers.

```text
1 201 | retry-after: None | expose: Retry-After | allow-origin: *
2 201 | retry-after: None | expose: Retry-After | allow-origin: *
3 201 | retry-after: None | expose: Retry-After | allow-origin: *
4 201 | retry-after: None | expose: Retry-After | allow-origin: *
5 201 | retry-after: None | expose: Retry-After | allow-origin: *
6 429 | retry-after: 7 | expose: Retry-After | allow-origin: *
7 429 | retry-after: 7 | expose: Retry-After | allow-origin: *
```

## Owner dashboard API (GET /dashboard)

Requires the owner token. Returns one entry per widget the caller owns, with stored_count and last_submission_at, plus total_stored. Only rows with status = 'stored' are counted, so flagged_spam rows never inflate the numbers. The query filters on widgets.owner_id, so one owner can never see another owner's widgets, and widgets with no submissions are listed with 0 (LEFT JOIN).

### Proof (tools/dashboard_proof.py, live server, two throwaway owners)

The raw rows show that spam exists in the table; the dashboard counts exclude it.

```text
== setup
== raw rows in the database (this run only)
  Proof A1 | flagged_spam | 2
  Proof A1 | stored | 3
  Proof A2 | stored | 1
  Proof B1 | flagged_spam | 1
  Proof B1 | stored | 2
== dashboard for owner A
  Proof A1 (signup_form): stored_count=3
  Proof A2 (signup_form): stored_count=1
  Proof A3 empty (signup_form): stored_count=0
  total_stored: 4
  PASS owner A gets 200
  PASS A1 counts 3 stored and ignores the 2 flagged_spam rows
  PASS A2 counts 1
  PASS empty widget A3 is listed with 0
  PASS total_stored is 4
  PASS owner A does not see owner B's widget
== dashboard for owner B
  widgets: [('Proof B1', 2)] | total_stored: 2
  PASS owner B sees only their own widget
  PASS owner B counts 2 stored and ignores 1 flagged_spam
  PASS owner B does not see owner A's widgets
== authentication
  no token -> 401
  PASS no token is rejected (401 or 403)
  bad token -> 401
  PASS bad token is rejected (401 or 403)
== result: ALL CHECKS PASSED
```
