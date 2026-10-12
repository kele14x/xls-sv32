"""Verify clocked cores and compatibility wrappers for both module names."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class WrapperBuildTest(unittest.TestCase):
    def test_default_and_custom_module_names(self):
        self.assertIsNotNone(shutil.which("iverilog"), "install Icarus Verilog for wrapper tests")
        with tempfile.TemporaryDirectory(prefix="sv32-wrapper-") as temporary:
            for module in ("sv32_core", "review_core"):
                with self.subTest(module=module):
                    output = Path(temporary) / module
                    result = subprocess.run([
                        sys.executable, str(ROOT / "scripts/build-sv32.py"),
                        "--module-name", module, "--output-dir", str(output),
                    ], cwd=ROOT, text=True, capture_output=True, timeout=120)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    # The public .v core remains usable with Verilog-2005 tools.
                    result = subprocess.run([
                        "iverilog", "-g2005", "-s", module, "-o", str(output / "core.vvp"),
                        str(output / "sv32_core.v"),
                    ], cwd=ROOT, text=True, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    for top in (module, "sv32_top"):
                        with self.subTest(top=top):
                            result = subprocess.run([
                                sys.executable, str(ROOT / "scripts/test-sv32.py"),
                                "--simulate-only", str(output), "--top-module", top,
                            ], cwd=ROOT, text=True, capture_output=True, timeout=120)
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
