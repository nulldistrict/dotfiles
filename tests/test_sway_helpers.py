"""Exercise helpers with mocked desktop commands; no live session required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SwayHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.log = self.home / "calls.jsonl"
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.home / "config"),
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        TEST_CALLS=str(self.log))
        self.mock("notify-send", "pass")
        self.mock("slurp", "print('10,20 300x200')")
        self.mock("swaymsg", "print(os.environ.get('TEST_TREE', '{}'))")
        self.mock("grim", """
if os.environ.get('FAIL_GRIM'):
    sys.exit(1)
if sys.argv[-1] == '-':
    sys.stdout.buffer.write(b'PNG')
else:
    Path(sys.argv[-1]).write_bytes(b'PNG')
""")
        self.mock("wl-copy", "sys.stdin.buffer.read()")

    def mock(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" +
                        "import json, os, sys\nfrom pathlib import Path\n" +
                        "with open(os.environ['TEST_CALLS'], 'a') as f:\n" +
                        "    f.write(json.dumps(sys.argv) + '\\n')\n" + body + "\n")
        path.chmod(0o755)

    def run_helper(self, name, *args):
        return subprocess.run(["bash", str(ROOT / "dot_local/bin" / ("executable_" + name)), *args],
                              env=self.env, capture_output=True, text=True)

    def calls(self, name):
        if not self.log.exists():
            return []
        return [c[1:] for c in map(json.loads, self.log.read_text().splitlines())
                if Path(c[0]).name == name]

    def images(self):
        return list(self.home.glob("Pictures/Screenshots/*.png"))

    def test_cancelled_selection_creates_no_file(self):
        self.mock("slurp", "sys.exit(1)")
        self.assertEqual(self.run_helper("sway-screenshot", "area").returncode, 0)
        self.assertEqual(self.images(), [])
        self.assertEqual(self.calls("grim"), [])

    def test_area_and_repeated_screenshots_have_unique_names(self):
        for _ in range(2):
            result = self.run_helper("sway-screenshot", "area")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.images()), 2)
        self.assertEqual(self.calls("grim")[0][:2], ['-g', '10,20 300x200'])

    def test_clipboard_does_not_save_a_file(self):
        result = self.run_helper("sway-screenshot", "clipboard")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.images(), [])
        self.assertEqual(self.calls("wl-copy"), [['--type', 'image/png']])

    def test_focused_window_uses_its_rectangle(self):
        self.env['TEST_TREE'] = json.dumps({'nodes': [
            {'focused': True, 'pid': 42, 'rect': {'x': -200, 'y': 20, 'width': 400, 'height': 300}}]})
        result = self.run_helper("sway-screenshot", "window")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("grim")[0][:2], ['-g', '-200,20 400x300'])

    def test_no_focused_window_does_not_capture_screen(self):
        self.assertNotEqual(self.run_helper("sway-screenshot", "window").returncode, 0)
        self.assertEqual(self.calls("grim"), [])

    def test_capture_failure_removes_empty_file(self):
        self.env['FAIL_GRIM'] = '1'
        self.assertNotEqual(self.run_helper("sway-screenshot", "screen").returncode, 0)
        self.assertEqual(self.images(), [])

    def test_wallpaper_quotes_filename(self):
        directory = Path(self.env['XDG_CONFIG_HOME']) / 'backgrounds'
        directory.mkdir(parents=True)
        image = directory / 'a space "; exec unexpected.png'
        image.touch()
        result = self.run_helper("sway-wallpaper")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls('swaymsg'), [[f'output * bg {json.dumps(str(image))} fill']])

    def test_empty_wallpaper_directory_is_harmless(self):
        self.assertEqual(self.run_helper('sway-wallpaper').returncode, 0)
        self.assertEqual(self.calls('swaymsg'), [])

    def test_lock_uses_ready_notification(self):
        self.mock('swaylock', 'pass')
        self.assertEqual(self.run_helper('sway-lock').returncode, 0)
        self.assertEqual(self.calls('swaylock'), [['-f']])


if __name__ == '__main__':
    unittest.main()
