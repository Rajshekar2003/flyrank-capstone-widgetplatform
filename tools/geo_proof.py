import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(stream=sys.stdout, level=logging.WARNING, format="  log: %(levelname)s %(message)s")
import geo


def run(title, ip, a, b):
    os.environ["GEO_MOCK_A"] = a
    os.environ["GEO_MOCK_B"] = b
    print(f"\n== {title} (A={a}, B={b}, ip={ip})")
    print("  result:", geo.lookup_with_fallback(ip))


run("A answers", "8.8.8.8", "ok", "ok")
run("A fails, B answers", "8.8.8.8", "fail", "ok")
run("both fail", "8.8.8.8", "fail", "fail")
run("private IP skips providers", "127.0.0.1", "ok", "ok")

