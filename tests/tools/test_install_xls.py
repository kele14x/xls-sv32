"""Exercise installer recovery offline without modifying workspace tools."""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ("interpreter_main", "ir_converter_main", "opt_main", "codegen_main")

CURL = '''#!/usr/bin/env python3
import os
import shutil
import sys
from pathlib import Path

with open(os.environ["CURL_LOG"], "a") as log:
    log.write("download\\n")
output = Path(sys.argv[sys.argv.index("-o") + 1])
mode = os.environ.get("CURL_MODE", "success")
if mode != "success":
    output.write_bytes(b"partial or corrupt archive")
    sys.exit(18 if mode == "interrupted" else 0)
shutil.copyfile(os.environ["RELEASE_ARCHIVE"], output)
'''


class XLSInstallerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xls-installer-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.project = self.folder / "project"
        for directory in ("scripts", "bin", "config/tools", "tools", "downloads", "mock-bin"):
            (self.project / directory).mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "scripts/install-xls.sh", self.project / "scripts/install-xls.sh")
        shutil.copy2(ROOT / "bin/xls", self.project / "bin/xls")
        curl = self.project / "mock-bin/curl"
        curl.write_text(CURL)
        curl.chmod(0o755)
        self.log = self.folder / "curl.log"
        self.archive = self.folder / "release.tar.gz"
        self.installed = self.project / "tools/xls-test"
        self.link = self.project / "tools/xls"
        self.cache = self.project / "downloads/release.tar.gz"
        self.make_archive()

    def populate(self, directory):
        stdlib = directory / "xls/dslx/stdlib"
        stdlib.mkdir(parents=True)
        (stdlib / "std.x").write_text("// fixture standard library\n")
        for tool in TOOLS:
            path = directory / tool
            path.write_text("#!/usr/bin/env bash\necho 'XLS fixture version'\n")
            path.chmod(0o755)

    def make_archive(self, incomplete=False, unusable=False):
        source = self.folder / "release/xls-test"
        if source.exists():
            shutil.rmtree(source)
        self.populate(source)
        if incomplete:
            (source / "codegen_main").unlink()
        if unusable:
            (source / "interpreter_main").write_text("#!/usr/bin/env bash\nexit 1\n")
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(source, arcname=source.name)
        manifest = {
            "archive": self.cache.name, "download_url": "https://example.invalid/release",
            "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "installed_directory": "tools/xls-test",
        }
        (self.project / "config/tools/xls-install.json").write_text(json.dumps(manifest))

    def working_default(self):
        previous = self.project / "tools/xls-old"
        self.populate(previous)
        self.link.symlink_to(previous.name)
        return previous

    def install(self, mode="success"):
        environment = dict(os.environ,
                           PATH=str(self.project / "mock-bin") + os.pathsep + os.environ["PATH"],
                           CURL_LOG=str(self.log), RELEASE_ARCHIVE=str(self.archive), CURL_MODE=mode)
        result = subprocess.run(["bash", str(self.project / "scripts/install-xls.sh")],
                                cwd=self.project, env=environment, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(list((self.project / "tools").glob(".xls-install.*")), [])
        self.assertEqual(list((self.project / "downloads").glob(".xls-download.*")), [])
        return result

    def assert_installed(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.link.resolve(), self.installed)
        for tool in TOOLS:
            self.assertTrue(os.access(self.installed / tool, os.X_OK))
        self.assertEqual(self.cache.read_bytes(), self.archive.read_bytes())

    def test_fresh_install_and_verified_cache_reuse(self):
        self.assert_installed(self.install())
        self.assert_installed(self.install())
        self.assertEqual(self.log.read_text().splitlines(), ["download"])
        self.assertEqual(len((self.project / "downloads/SHA256SUMS").read_text().splitlines()), 1)

    def test_incomplete_directory_is_repaired_before_switching_default(self):
        previous = self.working_default()
        self.installed.mkdir()
        (self.installed / "incomplete").write_text("interrupted extraction")
        self.assert_installed(self.install())
        self.assertFalse((self.installed / "incomplete").exists())
        self.assertTrue((previous / "interpreter_main").exists())

    def test_missing_standard_library_is_repaired(self):
        shutil.copytree(self.folder / "release/xls-test", self.installed)
        (self.installed / "xls/dslx/stdlib/std.x").unlink()
        self.assert_installed(self.install())
        self.assertTrue((self.installed / "xls/dslx/stdlib/std.x").is_file())

    def test_invalid_cached_archive_is_redownloaded(self):
        self.cache.write_bytes(b"corrupt cached archive")
        self.assert_installed(self.install())
        self.assertEqual(self.log.read_text().splitlines(), ["download"])

    def test_interrupted_download_preserves_default_and_retry_succeeds(self):
        previous = self.working_default()
        result = self.install("interrupted")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.link.resolve(), previous)
        self.assertFalse(self.cache.exists())
        self.assert_installed(self.install())
        self.assertEqual(len(self.log.read_text().splitlines()), 2)

    def test_checksum_failure_preserves_default_and_retry_succeeds(self):
        previous = self.working_default()
        result = self.install("corrupt")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)
        self.assertEqual(self.link.resolve(), previous)
        self.assertFalse(self.cache.exists())
        self.assert_installed(self.install())

    def test_incomplete_archive_preserves_default_and_existing_directory(self):
        previous = self.working_default()
        self.installed.mkdir()
        marker = self.installed / "marker"
        marker.write_text("existing installation")
        self.make_archive(incomplete=True)
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete or unusable", result.stderr)
        self.assertEqual(self.link.resolve(), previous)
        self.assertEqual(marker.read_text(), "existing installation")

    def test_unusable_executable_preserves_working_default(self):
        previous = self.working_default()
        self.make_archive(unusable=True)
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.link.resolve(), previous)
        self.assertFalse(self.installed.exists())

    def test_dangling_default_link_is_repaired(self):
        self.link.symlink_to("missing-version")
        self.assert_installed(self.install())

    def test_default_directory_is_not_silently_overwritten(self):
        self.link.mkdir()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected a symlink", result.stderr)
        self.assertEqual(list(self.link.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
