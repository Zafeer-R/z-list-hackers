"""Configuration: file paths and settings."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Data files - change these paths to switch between fake and real scores
FEATURES_FILE = str(ROOT / "data" / "features_TX_2022.csv")
SCORES_FILE = str(ROOT / "data" / "scores_TX_2022.csv")
LABELS_FILE = str(ROOT / "data" / "labels.csv")
PSEUDONYMS_FILE = str(ROOT / "data" / "pseudonyms.csv")  # private: contains NPIs, never committed

# Settings
ENABLE_EXCLUSION_STATUS = False  # Toggle to show exclusion status in the app
