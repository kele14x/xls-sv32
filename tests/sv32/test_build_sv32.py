"""Verify generated wrappers elaborate with default and custom core names."""

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
                    result = subprocess.run([
                        "iverilog", "-g2012", "-s", "sv32_top", "-o", str(output / "wrapper.vvp"),
                        str(output / "sv32_core.v"), str(output / "sv32_top.sv"),
                    ], cwd=ROOT, text=True, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
