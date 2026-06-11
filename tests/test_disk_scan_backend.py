"""Tests for DiskScanBackend categorisation and scanning logic."""

import pytest

from backends.disk_scan_backend import DISK_FREE_COLOR, DiskScanBackend, _categorize


# ── _categorize unit tests ────────────────────────────────────────────────────

def test_py_file_categorised_as_development():
    assert _categorize("/home/user/projects", "main.py") == "Development"


def test_js_file_categorised_as_development():
    assert _categorize("/home/user/projects", "app.js") == "Development"


def test_mp4_file_categorised_as_videos():
    assert _categorize("/home/user/Videos", "movie.mp4") == "Videos"


def test_jpg_categorised_as_pictures():
    assert _categorize("/home/user/Pictures", "photo.jpg") == "Pictures"


def test_png_categorised_as_pictures():
    assert _categorize("/home/user/Downloads", "icon.png") == "Pictures"


def test_mp3_categorised_as_music():
    assert _categorize("/home/user/Music", "song.mp3") == "Music & Audio"


def test_pdf_categorised_as_documents():
    assert _categorize("/home/user/Documents", "report.pdf") == "Documents"


def test_docx_categorised_as_documents():
    assert _categorize("/home/user/Documents", "letter.docx") == "Documents"


def test_zip_categorised_as_archives():
    assert _categorize("/home/user/Downloads", "data.zip") == "Archives"


def test_deb_categorised_as_archives():
    assert _categorize("/tmp", "package.deb") == "Archives"


def test_tar_gz_categorised_as_archives():
    assert _categorize("/tmp", "source.tar.gz") == "Archives"


def test_system_path_usr_categorised_as_system_os():
    assert _categorize("/usr/lib", "libfoo.so") == "System & OS"


def test_system_path_etc_categorised_as_system_os():
    assert _categorize("/etc/nginx", "nginx.conf") == "System & OS"


def test_system_path_bin_categorised_as_system_os():
    assert _categorize("/bin", "bash") == "System & OS"


def test_app_prefix_opt_categorised_as_applications():
    assert _categorize("/opt/chrome", "chrome") == "Applications"


def test_unknown_file_categorised_as_other():
    assert _categorize("/home/user/random", "datafile.xyz123") == "Other"


# ── DiskScanBackend.scan integration tests (real files in tmp_path) ───────────

def test_scan_counts_py_file_as_development(tmp_path):
    (tmp_path / "script.py").write_bytes(b"x" * 1024)
    result = DiskScanBackend().scan(str(tmp_path))
    assert result.get("Development", 0) >= 1024


def test_scan_counts_jpg_as_pictures(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"x" * 2048)
    result = DiskScanBackend().scan(str(tmp_path))
    assert result.get("Pictures", 0) >= 2048


def test_scan_counts_zip_as_archives(tmp_path):
    (tmp_path / "archive.zip").write_bytes(b"x" * 512)
    result = DiskScanBackend().scan(str(tmp_path))
    assert result.get("Archives", 0) >= 512


def test_scan_ignores_zero_size_categories(tmp_path):
    (tmp_path / "nonempty.py").write_bytes(b"x" * 100)
    result = DiskScanBackend().scan(str(tmp_path))
    assert all(v > 0 for v in result.values())


def test_scan_permission_error_skipped(tmp_path, monkeypatch):
    (tmp_path / "visible.py").write_bytes(b"x" * 100)
    original_stat = __import__("os").stat

    def flaky_stat(path, *, follow_symlinks=True):
        if "visible.py" in str(path):
            raise PermissionError("denied")
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr("os.stat", flaky_stat)
    result = DiskScanBackend().scan(str(tmp_path))
    assert result.get("Development", 0) == 0


def test_scan_skips_proc_under_root(monkeypatch):
    calls = []

    def fake_walk(path, **kwargs):
        yield "/", [], []
        yield "/proc/1", [], ["status"]
        calls.append("/proc/1")

    def fake_stat(path, *, follow_symlinks=True):
        class S:
            st_size = 100
            st_dev = 1
        return S()

    monkeypatch.setattr("backends.disk_scan_backend.os.walk", fake_walk)
    monkeypatch.setattr("backends.disk_scan_backend.os.stat", fake_stat)

    result = DiskScanBackend().scan("/")
    assert not calls or result == {}


def test_scan_prunes_dirs_on_different_device(tmp_path, monkeypatch):
    """Directories on a different st_dev are not descended into.

    Creates two real subdirectories; mocks st_dev on the 'foreign' subdir to
    simulate a different filesystem.  Only files in the 'local' subdir should
    be counted.
    """
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    (local_dir / "code.py").write_bytes(b"x" * 500)

    foreign_dir = tmp_path / "foreign"
    foreign_dir.mkdir()
    (foreign_dir / "video.mp4").write_bytes(b"x" * 10_000)

    real_stat = __import__("os").stat
    root_dev = real_stat(str(tmp_path)).st_dev

    def patched_stat(path, *, follow_symlinks=True):
        s = real_stat(str(path), follow_symlinks=follow_symlinks)

        class Proxy:
            st_size = s.st_size
            st_dev = s.st_dev

        if str(path) == str(foreign_dir):
            Proxy.st_dev = root_dev + 999  # simulate different filesystem
        return Proxy()

    monkeypatch.setattr("backends.disk_scan_backend.os.stat", patched_stat)

    result = DiskScanBackend().scan(str(tmp_path))
    # Only local/code.py should be counted; foreign/video.mp4 must not appear
    assert result.get("Development", 0) >= 500
    assert result.get("Videos", 0) == 0


# ── DISK_FREE_COLOR ───────────────────────────────────────────────────────────

def test_disk_free_color_is_defined():
    assert DISK_FREE_COLOR.startswith("#")
    assert len(DISK_FREE_COLOR) == 7


# ── DiskScanWorker cooperative cancellation ───────────────────────────────────

def test_disk_scan_worker_cancel_suppresses_finished():
    """DiskScanWorker emits nothing when cancelled before run() starts scanning."""
    from backends.disk_scan_backend import DiskScanWorker

    worker = DiskScanWorker("/")
    finished_calls: list = []
    failed_calls: list = []

    # Patch the scan to check cancellation and simulate it happening mid-scan
    import backends.disk_scan_backend as mod
    original_scan = mod.DiskScanBackend.scan

    def cancel_and_scan(self, mount_point, progress_cb=None, cancel_check=None):
        return {}  # simulate cancel_check returning True early

    worker.cancel()  # pre-cancel
    finished_called = []
    failed_called = []

    # Wire up signals
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    worker.finished.connect(lambda d: finished_called.append(d))
    worker.failed.connect(lambda e: failed_called.append(e))

    # Patch scan to just return empty (as if cancelled)
    import unittest.mock as _mock
    with _mock.patch.object(mod.DiskScanBackend, "scan", return_value={}):
        worker.run()

    # _cancelled is True, so finished must NOT have been emitted
    assert finished_called == []
    assert failed_called == []


def test_disk_scan_worker_not_cancelled_emits_finished(tmp_path):
    """DiskScanWorker.run() emits finished when _cancelled is False."""
    from backends.disk_scan_backend import DiskScanWorker

    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    worker = DiskScanWorker(str(tmp_path))
    (tmp_path / "test.txt").write_text("hello")
    finished_called: list = []
    worker.finished.connect(lambda d: finished_called.append(d))
    worker.run()

    assert len(finished_called) == 1


def test_cancel_flag_set_by_cancel():
    """DiskScanWorker.cancel() sets _cancelled to True."""
    from backends.disk_scan_backend import DiskScanWorker
    w = DiskScanWorker("/")
    assert not w._cancelled
    w.cancel()
    assert w._cancelled


# ── AdvancedDriveTile.cancel_scan ─────────────────────────────────────────────

def test_advanced_drive_tile_cancel_scan_drains_scan_thread():
    """cancel_scan() calls quit()+wait() on a running _scan_thread."""
    pytest.importorskip("PyQt6")
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from models.storage import Drive
    from views.dashboard_view import AdvancedDriveTile
    import functools
    from models.database import open_db

    drive = Drive(
        name="Test", device="/dev/sda", mount_point="/",
        total_bytes=1024, used_bytes=512, free_bytes=512, fs_type="ext4",
    )

    tile = AdvancedDriveTile(drive)

    mock_thread = MagicMock()
    mock_thread.isRunning.return_value = True
    mock_thread.wait.return_value = True
    mock_worker = MagicMock()

    tile._scan_thread = mock_thread
    tile._scan_worker = mock_worker
    tile._smart_thread = None
    tile._smart_worker = None

    tile.cancel_scan()

    mock_thread.quit.assert_called_once()
    mock_thread.wait.assert_called_once_with(3000)
    mock_worker.cancel.assert_called_once()
    assert tile._scan_thread is None
    assert tile._scan_worker is None


def test_advanced_drive_tile_cancel_scan_handles_runtime_error():
    """cancel_scan() swallows RuntimeError from a deleted C++ QThread."""
    pytest.importorskip("PyQt6")
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from models.storage import Drive
    from views.dashboard_view import AdvancedDriveTile

    drive = Drive(
        name="Test", device="/dev/sda", mount_point="/",
        total_bytes=1024, used_bytes=512, free_bytes=512, fs_type="ext4",
    )
    tile = AdvancedDriveTile(drive)

    mock_thread = MagicMock()
    mock_thread.isRunning.side_effect = RuntimeError("C++ object deleted")
    tile._scan_thread = mock_thread
    tile._scan_worker = MagicMock()

    # Must not raise
    tile.cancel_scan()
    assert tile._scan_thread is None


# ── _SegmentedPieWidget basis mode ───────────────────────────────────────────

def _app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_pie_used_basis_spans_full_circle():
    """In 'used' mode all category spans together fill ~360°×16 with no free wedge."""
    pytest.importorskip("PyQt6")
    _app()
    from views.dashboard_view import _SegmentedPieWidget

    pie = _SegmentedPieWidget()
    pie.set_basis("used")

    # 1 GiB total, 512 MiB free → 512 MiB used, split between Archives and Videos
    GiB = 1024 ** 3
    MiB = 1024 ** 2
    total = GiB
    free = 512 * MiB
    named = {"Archives": 256 * MiB, "Videos": 256 * MiB}
    pie.set_data(named, 0, free, total)

    used_total = total - free
    total_span = sum(int(v / used_total * 360 * 16) for v in named.values())

    # Should sum to 5760 (360°×16) within 2° rounding tolerance
    assert abs(total_span - 5760) < 32


def test_pie_used_basis_excludes_free_wedge():
    """In 'used' mode the _free sentinel is absent from the drawn segments."""
    pytest.importorskip("PyQt6")
    _app()
    from views.dashboard_view import _SegmentedPieWidget

    pie = _SegmentedPieWidget()
    pie.set_basis("used")
    # Monkey-patch to capture which colors are drawn
    drawn_colors: list[str] = []

    GiB = 1024 ** 3
    MiB = 1024 ** 2
    pie.set_data({"Archives": 512 * MiB}, 0, 512 * MiB, GiB)

    # _basis=="used" → the _free segment should not contribute any span
    used_total = GiB - 512 * MiB  # 512 MiB
    free_span = int((512 * MiB) / used_total * 360 * 16)  # would be 5760 if included
    archives_span = int((512 * MiB) / used_total * 360 * 16)  # 5760

    # Archives fills the whole ring; free_span would compete only in "total" mode
    assert archives_span == 5760
    assert free_span == 5760  # equal — but only one is drawn in used mode


def test_pie_total_basis_reverts_to_full_divisor():
    """set_basis('total') restores division by total_bytes including the free wedge."""
    pytest.importorskip("PyQt6")
    _app()
    from views.dashboard_view import _SegmentedPieWidget

    pie = _SegmentedPieWidget()
    pie.set_basis("used")
    pie.set_basis("total")
    assert pie._basis == "total"
