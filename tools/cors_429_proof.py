import http.client
import json

W = "6243574c-3b9c-4df6-af03-ab8a67978566"
body = json.dumps({"widget_id": W, "fields": {"email": "burst@example.com"}})
headers = {"Content-Type": "application/json", "Origin": "http://localhost:9000", "X-Forwarded-For": "9.9.9.50"}
for i in range(1, 8):
    conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
    conn.request("POST", "/submissions", body, headers)
    resp = conn.getresponse()
    resp.read()
    h = {k.lower(): v for k, v in resp.getheaders()}
    print(i, resp.status, "| retry-after:", h.get("retry-after"),
          "| expose:", h.get("access-control-expose-headers"),
          "| allow-origin:", h.get("access-control-allow-origin"))
    conn.close()
