"""Shared isolated environment for the standard-library test suite."""

import os
import sys
import tempfile
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = API_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

TEST_ROOT = Path(tempfile.mkdtemp(prefix="onthespot-tests-"))
os.environ.setdefault("ONTHESPOTDIR", str(TEST_ROOT / "config"))
os.environ.setdefault("ONTHESPOTCACHEDIR", str(TEST_ROOT / "cache"))
os.environ.setdefault("HOME", str(TEST_ROOT / "home"))
os.environ.setdefault("USERPROFILE", str(TEST_ROOT / "home"))
