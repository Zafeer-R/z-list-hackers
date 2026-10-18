"""Configuration: file paths and settings."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Data files - change these paths to switch between fake and real scores
FEATURES_FILE = str(ROOT / "data" / "features_TX_2022.csv")
SCORES_FILE = str(ROOT / "data" / "scores_TX_2022.csv")
LABELS_FILE = str(ROOT / "data" / "labels.csv")
PSEUDONYMS_FILE = str(ROOT / "data" / "pseudonyms.csv")  # private: contains NPIs, never committed

GRANITE_URL = "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-05-29"
GRANITE_MODEL = "ibm/granite-4-h-small"
GRANITE_PROJECT_ID = "e0263420-028b-4c63-b991-94686ee77d77"  # project id, not a credential
