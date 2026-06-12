"""Runs the GNOME extension's JS unit tests (gjs) under pytest, so the whole
suite covers the extension's pure matching logic too. Skipped if gjs is absent."""

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_JS = ROOT / "gnome-extension" / "tests" / "test_purge.js"


@pytest.mark.skipif(shutil.which("gjs") is None, reason="gjs not installed")
def test_extension_match_logic_via_gjs():
    assert TEST_JS.exists(), TEST_JS
    r = subprocess.run(["gjs", "-m", str(TEST_JS)],
                       capture_output=True, text=True, timeout=20)
    output = r.stdout + r.stderr
    assert r.returncode == 0, output
    assert "ALL PASS" in r.stdout, output
