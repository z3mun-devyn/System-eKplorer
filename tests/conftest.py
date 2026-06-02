"""Session-scoped QApplication + between-test GC flush.

PyQt6 test suites can crash when Python's cyclic GC finalises old Qt-wrapper
objects mid-construction of a new widget (the C++ Qt layer is not re-entrant
for interleaved destruction). Two complementary fixes:

1. One QApplication lives for the entire pytest session so its destruction
   never races with other widget construction.
2. A function-scope autouse fixture forces gc.collect() BEFORE each test,
   draining any pending PyQt6-wrapper finalisation that accumulated during the
   previous test.  We do NOT collect after each test because some tests leave
   intentionally-live QThread workers whose Python wrappers must not be
   forcibly freed while the C++ thread is still running.
"""
import gc
import sys
import pytest


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """One QApplication for the whole test session."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        yield None
        return

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def _gc_before_test():
    """Drain pending PyQt6-wrapper finalisation BEFORE each test starts."""
    gc.collect()
    yield
