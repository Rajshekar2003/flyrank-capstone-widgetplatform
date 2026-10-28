"""Loads static/widget.js and derives a content-hash version for cache busting."""
import hashlib
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "widget.js")
_cache = {"mtime": None, "body": b"", "version": ""}


def load():
    """Return (body_bytes, version). Re-reads the file only when it changed on disk."""
    mtime = os.path.getmtime(_PATH)
    if _cache["mtime"] != mtime:
        with open(_PATH, "rb") as f:
            raw = f.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        raw = raw.replace(b"\r\n", b"\n")
        _cache.update(mtime=mtime, body=raw, version=hashlib.sha256(raw).hexdigest()[:12])
    return _cache["body"], _cache["version"]
