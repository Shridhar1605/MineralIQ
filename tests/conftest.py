"""Make backend/app importable for the s2+ ingestion tests (stdlib-safe)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"))
