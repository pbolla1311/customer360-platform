import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASETS_DIR = PROJECT_ROOT / "datasets"
RAW_DATA_DIR = DATASETS_DIR / "raw"
PROCESSED_DATA_DIR = DATASETS_DIR / "processed"

DATABASE_FILE = PROJECT_ROOT / "customer360.db"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATABASE_FILE}",
)

API_TITLE = "Customer360 Platform"
API_VERSION = "1.0"

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8501",
    ).split(",")
    if origin.strip()
]

# Placeholder constant: no LinkedIn profile URL exists anywhere in this
# repository, so the landing page must not invent one. Left unset, the
# author's LinkedIn link renders as a clearly-marked, non-interactive
# placeholder instead of a fabricated or broken URL. Set this env var to
# the real profile URL to enable the link.
AUTHOR_LINKEDIN_URL = os.getenv("AUTHOR_LINKEDIN_URL", "").strip()

# Signs the Workspace's demo-tier session cookie (who you're signed in as,
# which organization/role) -- not a real security boundary (no passwords
# exist anywhere in this app), so an ephemeral per-process fallback is
# fine: sessions just don't survive a restart if this isn't set.
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY") or secrets.token_hex(32)