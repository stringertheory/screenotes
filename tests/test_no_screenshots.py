import base64
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# Run through Python, since Windows can't start a script by its #! line.
SCRIPT = ROOT / 'scripts' / 'check-no-screenshots'
loader = SourceFileLoader('check_no_screenshots', str(SCRIPT))
check = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(check)


def png() -> bytes:
    out = io.BytesIO()
    Image.new('RGB', (64, 64), (200, 40, 40)).save(out, 'PNG')
    return out.getvalue()


def page() -> bytes:
    return (b'<html><head><meta name="generator" content="Screenotate 3.0.0"></head><body><img src="data:image/png;'
            b'base64,' + base64.b64encode(png() * 4) + b'"></body></html>')


@unittest.skipUnless(shutil.which('git') and (ROOT / '.git').exists(), 'needs the git checkout')
class RepoTests(unittest.TestCase):
    def test_nothing_tracked_is_a_screenshot(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_commit_with_a_renamed_screenshot_is_stopped(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                return subprocess.run(['git', '-C', folder, *args], check=True, capture_output=True)
            git('init', '-q')
            Path(folder, 'notes.txt').write_bytes(png())
            Path(folder, 'readme.md').write_text('Fine.\n')
            git('add', '.')
            result = subprocess.run([sys.executable, str(SCRIPT), '--staged'], cwd=folder, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('notes.txt: is an image by its contents', result.stderr)
            self.assertNotIn('readme.md', result.stderr)


class RuleTests(unittest.TestCase):
    def test_images_and_pages_are_refused_by_name_or_contents(self):
        self.assertEqual(check.problems('shots/a.png', b''), ['is an image or page by its name'])
        self.assertEqual(check.problems('a.txt', png()), ['is an image by its contents'])
        self.assertIn('is an image or page by its name', check.problems('Screenshot 2022.html', page()))

    def test_an_image_inside_a_text_file_is_refused(self):
        self.assertEqual(check.problems('capture.txt', page()), ['has an image embedded in it'])

    def test_a_large_file_is_refused(self):
        self.assertEqual(check.problems('data.json', b'0' * (check.LARGEST + 1)),
                         [f'is {check.LARGEST + 1:,} bytes, over the {check.LARGEST:,} limit'])

    def test_built_scripts_may_be_large_and_hold_tiny_images_but_not_screenshots(self):
        tiny = b'var probe="data:image/jpeg;base64,' + b'A' * 800 + b'";'
        self.assertEqual(check.problems('dist/assets/pica-BQoUpkxG.js', tiny + b'0' * (check.LARGEST + 1)), [])
        self.assertEqual(check.problems('dist/assets/index-wQ7eQ060.js', tiny.replace(b'A' * 800, b'A' * 5000)), ['has an image embedded in it'])
        self.assertEqual(check.problems('web/src/probe.js', tiny), ['has an image embedded in it'])
        self.assertEqual(check.problems('dist/assets/big.js', b'0' * (check.BUILT_LARGEST + 1)),
                         [f'is {check.BUILT_LARGEST + 1:,} bytes, over the {check.BUILT_LARGEST:,} limit'])

    def test_the_apps_own_images_and_ordinary_text_pass(self):
        self.assertEqual(check.problems('public/favicon-32.png', png()), [])
        self.assertEqual(check.problems('server/screenotate.py', b'SIGNATURE = b"Screenotate"\n'), [])
        self.assertEqual(check.problems('notes.md', b'BMW and RIFF are words.\n'), [])


if __name__ == '__main__':
    unittest.main()
