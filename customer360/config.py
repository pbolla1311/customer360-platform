from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = PROJECT_ROOT / "datasets"
RAW_DATA_DIR = DATASETS_DIR / "raw"
PROCESSED_DATA_DIR = DATASETS_DIR / "processed"

DATABASE_FILE = PROJECT_ROOT / "customer360.db"

API_TITLE = "Customer360 Platform"
API_VERSION = "1.0.0"
