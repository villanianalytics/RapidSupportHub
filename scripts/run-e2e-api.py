"""Start an isolated local test server. Never uses the production database."""

import os
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
temp = Path(tempfile.mkdtemp(prefix="rsh-e2e-"))
os.environ["DATABASE_URL"] = "sqlite:///" + str(temp / "e2e.db")
os.environ["UPLOAD_DIR"] = str(temp / "uploads")
os.environ["ADMIN_PASSWORD"] = os.getenv("E2E_PASSWORD", "Local-e2e-password-123!")
os.environ["APP_ORIGIN"] = "http://127.0.0.1:5173"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SSO_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
import uvicorn

uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
