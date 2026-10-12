"""Execute the documented library recipe offline in isolated fixtures."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = b"verified fixture library\n"


class NangateInstallRecipeTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nangate-install-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        (self.folder / "config/tools").mkdir(parents=True)
        (self.folder / "tools/old").mkdir(parents=True)
        (self.folder / "tools/old/library.lib").write_bytes(b"old library")
        self.link = self.folder / "tools/nangate45"
        manifest = {
            "download_path": "downloads/library.lib", "source_path": "fixture.lib",
            "sha256": hashlib.sha256(LIBRARY).hexdigest(), "size_bytes": len(LIBRARY),
            "installed_directory": "tools/new", "filename": "library.lib",
            "library_path": "tools/nangate45/library.lib",
        }
        (self.folder / "config/tools/nangate45-install.json").write_text(json.dumps(manifest))

    def install(self):
        text = (ROOT / "docs/opensta.md").read_text().split("## Install the verification library")[1]
        recipe = re.search(r"python3 - <<'PY'\n(.*?)\nPY", text, re.S).group(1)
        # Run the exact recipe with only the network response replaced.
        script = ("import io, urllib.request\n"
                  f"urllib.request.urlopen = lambda url: io.BytesIO({LIBRARY!r})\n" + recipe)
        return subprocess.run([sys.executable, "-c", script], cwd=self.folder,
                              text=True, capture_output=True, timeout=15)

    def test_fresh_stale_and_dangling_links_select_verified_library(self):
        for target in (None, "old", "missing"):
            with self.subTest(target=target):
                if self.link.is_symlink():
                    self.link.unlink()
                if target is not None:
                    self.link.symlink_to(target)
                result = self.install()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(os.readlink(self.link), "new")
                self.assertEqual((self.link / "library.lib").read_bytes(), LIBRARY)
                self.assertEqual(list((self.folder / "tools").glob(".nangate45-link-*")), [])

    def test_existing_default_directory_is_reported(self):
        self.link.mkdir()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected a symlink", result.stderr)
        self.assertTrue(self.link.is_dir())


if __name__ == "__main__":
    unittest.main()
