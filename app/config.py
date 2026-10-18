"""Configuration: file paths and settings."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Data files - change these paths to switch between fake and real scores
FEATURES_FILE = str(ROOT / "data" / "features_TX_2022.csv")
SCORES_FILE = str(ROOT / "data" / "scores_fake.csv")  # Switch to "scores_TX_2022.csv" when D's file arrives
LABELS_FILE = str(ROOT / "data" / "labels.csv")

# Settings
ENABLE_EXCLUSION_STATUS = False  # Toggle to show exclusion status in the app
