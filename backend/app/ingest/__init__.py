"""MineralIQ ingestion adapters (Stage 2)."""
from .base import BaseAdapter  # noqa: F401  (re-export for convenience)
from .adapters import ADAPTERS, get_adapter  # noqa: F401
