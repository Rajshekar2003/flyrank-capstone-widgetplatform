"""Environment-driven settings. More settings move in here as their modules move."""
import os

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get("DB_PATH", "widgets.db")
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24
