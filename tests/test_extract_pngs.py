import contextlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import os
from pathlib import Path
import tempfile
import unittest

from tests.test_screenotate import page, png

ROOT = Path(__file__).resolve().parents[1]
loader = SourceFileLoader('extract_pngs', str(ROOT / 'scripts' / 'extract-pngs'))
extract = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(extract)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def run_script(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = extract.main([str(self.folder), *args])
        return code, out.getvalue()

    def files(self):
        return sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob('*') if path.is_file())

    def test_a_dry_run_counts_and_writes_nothing(self):
        (self.folder / 'A.html').write_bytes(page(png()))
        code, out = self.run_script()
        self.assertEqual(code, 0)
        self.assertIn('1  pages without a PNG beside them', out)
        self.assertEqual(self.files(), ['A.html'])

    def test_write_puts_the_exact_embedded_bytes_beside_the_page_with_its_time(self):
        image = png('blue')
        (self.folder / 'sub').mkdir()
        (self.folder / 'sub' / 'A.html').write_bytes(page(image))
        os.utime(self.folder / 'sub' / 'A.html', (1_600_000_000, 1_600_000_000))
        self.assertEqual(self.run_script('--write')[0], 0)
        self.assertEqual(self.files(), ['sub/A.html', 'sub/A.png'])
        self.assertEqual((self.folder / 'sub' / 'A.png').read_bytes(), image)
        self.assertEqual((self.folder / 'sub' / 'A.png').stat().st_mtime, 1_600_000_000)

    def test_existing_pngs_other_pages_and_hidden_folders_are_left_alone(self):
        image = png()
        (self.folder / 'Same.html').write_bytes(page(image))
        (self.folder / 'Same.png').write_bytes(image)
        (self.folder / 'Other.html').write_bytes(page(image))
        (self.folder / 'Other.PNG').write_bytes(png('green'))
        (self.folder / 'plain.html').write_text('<html><body>Hello</body></html>')
        (self.folder / '.hidden').mkdir()
        (self.folder / '.hidden' / 'B.html').write_bytes(page(image))
        before = {path: path.read_bytes() for path in self.folder.rglob('*') if path.is_file()}
        code, out = self.run_script('--write')
        self.assertEqual(code, 0)
        self.assertIn('1  pages with the same PNG beside them already', out)
        self.assertIn('1  pages beside a different PNG of their name, left alone', out)
        self.assertEqual({path: path.read_bytes() for path in self.folder.rglob('*') if path.is_file()}, before)

    def test_a_name_taken_while_writing_is_not_overwritten(self):
        page_path = self.folder / 'A.html'
        page_path.write_bytes(page(png()))
        (self.folder / 'A.png').write_bytes(b'not mine')
        self.assertFalse(extract.write(page_path, png()))
        self.assertEqual((self.folder / 'A.png').read_bytes(), b'not mine')
        self.assertEqual(self.files(), ['A.html', 'A.png'])


if __name__ == '__main__':
    unittest.main()
