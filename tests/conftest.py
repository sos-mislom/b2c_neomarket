from __future__ import annotations

import os
import sys
import json
import base64
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


def make_auth_headers(user_id: str) -> dict[str, str]:
    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    token = f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode({'sub': user_id})}."
    return {"Authorization": f"Bearer {token}"}
