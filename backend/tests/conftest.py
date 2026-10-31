import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("FINN_DATA_MODE", "fixture")   # importing the API module never goes live in tests

from finn.factory import FIXTURE_NOW, build_pipeline  # noqa: E402


@pytest.fixture
def pipe():
    p = build_pipeline("fixture")
    p.refresh_all()
    return p


@pytest.fixture
def now():
    return FIXTURE_NOW
