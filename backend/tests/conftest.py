import faulthandler
import os
import sys
import tempfile
from pathlib import Path

# If any test hangs, dump every thread's stack after 120 s instead of stalling silently.
faulthandler.dump_traceback_later(120, repeat=True, exit=False)
os.environ["SAAKH_UPLOADS"] = str(Path(tempfile.gettempdir()) / f"saakh_pytest_uploads_{os.getpid()}")

_db = Path(tempfile.gettempdir()) / f"saakh_pytest_{os.getpid()}.db"
os.environ["SAAKH_DB"] = str(_db)
os.environ["SAAKH_SEED"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_configure(config):
    config.addinivalue_line("markers", "api: drives the HTTP API through Starlette's TestClient (needs loopback sockets)")


def pytest_collection_modifyitems(config, items):
    """Auto-mark HTTP tests. TestClient runs the app on an AnyIO portal, which on Windows opens a loopback
    socket pair; sandboxes that block local sockets hang there. Run `pytest -m "not api"` in such environments."""
    import inspect

    import pytest
    for item in items:
        fn = getattr(item, "function", None)
        try:
            src = inspect.getsource(fn) if fn else ""
        except (OSError, TypeError):
            src = ""
        if "client()" in src or "TestClient(" in src:
            item.add_marker(pytest.mark.api)
