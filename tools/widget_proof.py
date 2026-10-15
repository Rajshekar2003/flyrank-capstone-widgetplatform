import http.client
import json

WIDGET = "6243574c-3b9c-4df6-af03-ab8a67978566"


def get(path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
    conn.request("GET", path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, hdrs, body


def show(title, status, hdrs, body, names):
    print("== " + title)
    print("  status:", status, "| body bytes:", len(body))
    for n in names:
        print("  " + n + ":", hdrs.get(n))


JS = ["content-type", "cache-control", "etag"]
s, h, b = get("/widget.js?id=" + WIDGET)
version = h["etag"].strip('"')
show("1 widget.js, no version in URL", s, h, b, JS)
s, h, b = get("/widget.js?id=" + WIDGET + "&v=" + version)
show("2 widget.js, current version in URL", s, h, b, JS)
s, h, b = get("/widget.js?id=" + WIDGET + "&v=stale123")
show("3 widget.js, stale version in URL", s, h, b, JS)
s, h, b = get("/widget.js?id=" + WIDGET + "&v=" + version, {"If-None-Match": '"' + version + '"'})
show("4 widget.js, conditional request", s, h, b, ["etag", "cache-control"])

s, h, b = get("/widgets/" + WIDGET + "/config", {"Origin": "http://localhost:9000"})
show("5 public config, from another origin", s, h, b,
     ["content-type", "cache-control", "etag", "access-control-allow-origin", "access-control-expose-headers"])
cfg = json.loads(b)
print("  keys:", sorted(cfg))
print("  owner_id exposed:", "owner_id" in cfg)
s2, h2, b2 = get("/widgets/" + WIDGET + "/config", {"If-None-Match": h["etag"]})
show("6 public config, conditional request", s2, h2, b2, ["etag"])
s, h, b = get("/widgets/does-not-exist/config")
show("7 unknown widget", s, h, b, [])
