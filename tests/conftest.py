import os, tempfile
os.environ.update(ADMIN_EMAIL="admin@test.com", LS_WEBHOOK_SECRET="whsec", DATA_DIR=tempfile.mkdtemp(), SECRET_KEY="test-secret")
os.environ.pop("DATABASE_URL", None)
import pytest
from app import main as m

@pytest.fixture(autouse=True)
def _reset_limits(): m.HITS.clear()
