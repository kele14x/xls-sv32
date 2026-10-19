"""Check that the C linker rejects firmware the Harvard SoC cannot execute."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = shutil.which("riscv32-unknown-elf-gcc")


@unittest.skipUnless(COMPILER, "RISC-V bare-metal GCC is optional for the Python firmware")
class FirmwareLinkerTest(unittest.TestCase):
    def link(self, source):
        with tempfile.TemporaryDirectory(prefix="sv32-firmware-") as temporary:
            folder = Path(temporary)
            program = folder / "main.c"
            program.write_text(source)
            result = subprocess.run([
                COMPILER, "-march=rv32i", "-mabi=ilp32", "-mno-relax",
                "-msmall-data-limit=0", "-ffreestanding", "-nostdlib",
                "-Wl,--no-relax,--build-id=none", "-T", str(ROOT / "programs/sv32.ld"),
                str(ROOT / "programs/crt0.S"), str(program), "-o", str(folder / "test.elf"),
            ], text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, "Unsupported firmware linked successfully")
        return result.stdout + result.stderr

    def test_rejects_initialized_data_and_constants(self):
        for source in (
            "volatile unsigned value = 1; int main(void) { return value; }",
            'const char message[] = "hello"; int main(void) { return message[0]; }',
        ):
            with self.subTest(source=source):
                self.assertIn("Initialized data/rodata require RAM-image support", self.link(source))

    def test_rejects_instruction_rom_overflow(self):
        source = 'asm(".section .text.extra\\n.space 1100\\n.previous"); int main(void) { return 0; }'
        self.assertRegex(self.link(source),
                         r"will not fit in region `IMEM'|region `IMEM' overflowed")

    def test_reserves_ram_for_the_stack(self):
        source = "volatile unsigned values[256]; int main(void) { return values[0]; }"
        self.assertIn("BSS overlaps the reserved 256-byte stack", self.link(source))


if __name__ == "__main__":
    unittest.main()
