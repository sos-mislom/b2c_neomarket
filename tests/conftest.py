from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test_b2c.sqlite")
os.environ.setdefault("AUTO_SEED", "true")
os.environ.setdefault("TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
os.environ.setdefault("B2B_SERVICE_KEY", "secret-b2c-to-b2b")

TEST_DB = Path("test_b2c.sqlite")
if TEST_DB.exists():
    TEST_DB.unlink()
