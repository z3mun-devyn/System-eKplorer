"""Parser tests for PackagesBackend.

All tests feed fixture strings directly to _parse_line() — no subprocess.
list_installed() is covered by a monkeypatch test.
"""

import pytest
from backends.packages_backend import PackagesBackend, _parse_line
from models.package import Package
import strings


# ── _parse_line ───────────────────────────────────────────────────────────────

def test_parse_line_installed():
    pkg = _parse_line("bash\t5.1-6ubuntu1\t6608\tii \tshells")
    assert pkg is not None
    assert pkg.name == "bash"
    assert pkg.version == "5.1-6ubuntu1"
    assert pkg.installed_size_kb == 6608
    assert pkg.section == "shells"


def test_parse_line_skips_non_installed():
    # Status "rc" = removed but config files remain — should be skipped
    assert _parse_line("vim\t2:8.2\t3000\trc \tutils") is None


def test_parse_line_skips_half_installed():
    assert _parse_line("vim\t2:8.2\t3000\thi \tutils") is None


def test_parse_line_strips_area_prefix():
    pkg = _parse_line("libssl3\t3.0.2-0ubuntu1\t2048\tii \tnon-free/libs")
    assert pkg is not None
    assert pkg.section == "libs"


def test_parse_line_contrib_prefix():
    pkg = _parse_line("flashplugin\t1.0\t512\tii \tcontrib/web")
    assert pkg is not None
    assert pkg.section == "web"


def test_parse_line_size_zero_on_bad_value():
    pkg = _parse_line("foo\t1.0\t-\tii \tutils")
    assert pkg is not None
    assert pkg.installed_size_kb == 0


def test_parse_line_too_few_fields():
    assert _parse_line("bash\t5.1") is None


def test_parse_line_empty():
    assert _parse_line("") is None


def test_parse_line_whitespace_only():
    assert _parse_line("   \t\t\t\t") is None


# ── Package.size_str ──────────────────────────────────────────────────────────

def test_size_str_kb():
    assert Package("a", "1", 512, "utils").size_str == "512 KB"


def test_size_str_mb():
    pkg = Package("a", "1", 2048, "utils")
    assert pkg.size_str == "2.0 MB"


def test_size_str_gb():
    pkg = Package("a", "1", 1024 * 1024 * 2, "utils")
    assert pkg.size_str == "2.0 GB"


# ── Category mapping ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("section,expected", [
    ("utils",        "System Tools"),
    ("admin",        "System Tools"),
    ("libs",         "System Libraries"),
    ("oldlibs",      "System Libraries"),
    ("devel",        "Development"),
    ("libdevel",     "Development"),
    ("python",       "Development"),
    ("python3",      "Development"),
    ("net",          "Internet"),
    ("web",          "Internet"),
    ("games",        "Games"),
    ("fonts",        "Fonts"),
    ("sound",        "Audio & Video"),
    ("video",        "Audio & Video"),
    ("multimedia",   "Audio & Video"),
    ("gnome",        "Desktop"),
    ("kde",          "Desktop"),
    ("x11",          "Desktop"),
    ("mail",         "Email & Messaging"),
    ("news",         "Email & Messaging"),
    ("science",      "Science"),
    ("math",         "Science"),
    ("doc",          "Documentation"),
    ("localization", "Language"),
    ("misc",         "Other"),
    ("",             "Other"),
    ("unknown_xyz",  "Other"),
])
def test_package_category(section, expected):
    assert strings.package_category(section) == expected


# ── list_installed monkeypatch ────────────────────────────────────────────────

SAMPLE_DPKG_OUTPUT = (
    "bash\t5.1-6ubuntu1\t6608\tii \tshells\n"
    "vim\t2:8.2.3995-1ubuntu2\t3584\tii \teditors\n"
    "python3\t3.10.6-1~22.04\t178\tii \tpython\n"
    "oldpkg\t1.0\t100\trc \tutils\n"  # should be skipped
)


def test_list_installed(monkeypatch):
    import subprocess

    class FakeResult:
        stdout = SAMPLE_DPKG_OUTPUT
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())
    pkgs = PackagesBackend().list_installed()
    assert len(pkgs) == 3
    names = [p.name for p in pkgs]
    assert "bash" in names
    assert "vim" in names
    assert "python3" in names
    assert "oldpkg" not in names


def test_list_installed_timeout(monkeypatch):
    import subprocess
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("dpkg-query", 30)),
    )
    pkgs = PackagesBackend().list_installed()
    assert pkgs == []


def test_list_installed_not_found(monkeypatch):
    import subprocess
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )
    pkgs = PackagesBackend().list_installed()
    assert pkgs == []
