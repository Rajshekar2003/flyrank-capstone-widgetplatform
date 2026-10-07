# Design doc

## Widget model
A widget belongs to one owner (tenant). Fields: id, owner_id, type (signup_form | cta_popover), title, description, form_fields (JSON list of {name, label, type, required}), button_text, display_options (JSON: color, position), created_at. Index on owner_id, since every widget-management query filters by it.

## Submission model
A submission belongs to one widget. Fields: id, widget_id, field_values (JSON), ip_address, country, city (nullable - filled by geo enrichment), status (stored | flagged_spam), created_at. Index on widget_id, since the dashboard and the widget-owner isolation check both filter by it.

## The embed flow, in one line each
1. Owner creates a widget via the authenticated management API.
2. Owner copies the generated `<script src=".../widget.js?id={widget_id}">` snippet.
3. Visitor's browser loads widget.js, which fetches `GET /widgets/{id}/config` (public, cached, CORS-enabled).
4. The script renders a form from that config.
5. Visitor submits -> `POST /submissions` (public, CORS-enabled, validated, rate-limited).

## API contracts (summary - full detail added as each phase is built)
- Owner-authenticated: `POST/GET/PUT/DELETE /widgets`, `GET /dashboard/...` - require a bearer token, every query scoped to the token owner's tenant id.
- Public, cached: `GET /widgets/{id}/config`, `GET /widget.js` - no auth, `Cache-Control` headers, CORS allowed from any origin.
- Public, protected: `POST /submissions` - no auth, CORS allowed from any origin, but validated, rate-limited, spam-checked before anything is stored.

## Non-goal
This capstone will not implement real email delivery. Confirmation "emails" are logged to the console (or caught by Mailpit locally) - what's graded is that a failure in that step never blocks the submission from being stored, not that an email actually reaches an inbox.
