"""Environment-driven settings. More settings move in here as their modules move."""
import os

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get("DB_PATH", "widgets.db")
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24

RATE_LIMIT_IP_MAX = int(os.environ.get("RATE_LIMIT_IP_MAX", "5"))
RATE_LIMIT_IP_WINDOW_SECONDS = float(os.environ.get("RATE_LIMIT_IP_WINDOW_SECONDS", "10"))
RATE_LIMIT_WIDGET_MAX = int(os.environ.get("RATE_LIMIT_WIDGET_MAX", "30"))
RATE_LIMIT_WIDGET_WINDOW_SECONDS = float(os.environ.get("RATE_LIMIT_WIDGET_WINDOW_SECONDS", "10"))
TRUST_PROXY = os.environ.get("TRUST_PROXY", "false").lower() == "true"
