"""The two directories the application reads files from."""

from pathlib import Path

API_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = API_DIR.parents[1]
