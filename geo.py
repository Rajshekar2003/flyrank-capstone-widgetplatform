"""Geo enrichment: provider A, falling back to provider B. Never raises to callers."""
import ipaddress
import json
import logging
import os
import urllib.request

log = logging.getLogger("geo")


class GeoError(Exception):
    pass


def _cfg(name, default):
    return os.environ.get(name, default)


def _clean(value):
    if isinstance(value, str) and value.strip():
        return value.strip()[:100]
    return None


def _fetch_json(url):
    timeout = float(_cfg("GEO_TIMEOUT_SECONDS", "2"))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "widget-platform/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read(65536))
    except Exception as exc:
        raise GeoError(f"{type(exc).__name__}: {exc}") from exc


def _mock(name, mode):
    if mode == "ok":
        return {"country": f"Mockland-{name}", "city": f"Mockville-{name}"}
    raise GeoError(f"mock provider {name} forced to fail")


def provider_a(ip):
    mock = _cfg("GEO_MOCK_A", "")
    if mock:
        return _mock("A", mock)
    url = _cfg("GEO_A_URL", "https://ipapi.co/{ip}/json/").format(ip=ip)
    data = _fetch_json(url)
    if data.get("error"):
        raise GeoError(f"provider A error: {data.get('reason')}")
    return {"country": _clean(data.get("country_name")), "city": _clean(data.get("city"))}


def provider_b(ip):
    mock = _cfg("GEO_MOCK_B", "")
    if mock:
        return _mock("B", mock)
    url = _cfg("GEO_B_URL", "http://ip-api.com/json/{ip}").format(ip=ip)
    data = _fetch_json(url)
    if data.get("status") != "success":
        raise GeoError(f"provider B status: {data.get('status')}")
    return {"country": _clean(data.get("country")), "city": _clean(data.get("city"))}


PROVIDERS = (("A", provider_a), ("B", provider_b))


def is_public_ip(ip):
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def lookup_with_fallback(ip):
    """Return {country, city, provider} or None. Never raises."""
    if not is_public_ip(ip):
        return None
    for name, fn in PROVIDERS:
        try:
            result = fn(ip)
        except Exception as exc:
            log.warning("geo provider %s failed for %s: %s", name, ip, exc)
            continue
        if result.get("country") or result.get("city"):
            result["provider"] = name
            return result
        log.warning("geo provider %s returned no data for %s", name, ip)
    log.error("all geo providers failed for %s", ip)
    return None
