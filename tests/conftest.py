import os
import tempfile

# Must be set before the app is imported so it never touches a real database.
_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["APP_ENV"] = "test"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.core.cache import analytics_cache, clear_all_caches, qa_cache, search_cache  # noqa: E402
from app.db import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_state():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clear_all_caches()
    for cache in (qa_cache, search_cache, analytics_cache):
        cache.reset_stats()
    yield


@pytest.fixture()
def client():
    from main import app

    # No `with` block: skips the lifespan so tests never load ML models.
    return TestClient(app)


@pytest.fixture()
def admin_headers():
    return {"X-API-Key": "test-admin-key"}
