import base64
from datetime import datetime
import io
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from server.api import App
from server.cache import connect
from server.library import Library
from server.notes import Notes
from server.screenotate import captured_at, parse
from server.semantic import Encoder


def png(color='red', size=(32, 24)):
    stream = io.BytesIO()
    Image.new('RGB', size, color).save(stream, 'PNG')
    return stream.getvalue()


def page(image: bytes, text='Disk full &amp; nothing written', window='Terminal — ssh buildhost', app='Terminal',
         url='https://example.com/a?b=1&amp;c=2', stamp='2022-01-25 at 11.33.14 PM'):
    """A page as Screenotate 3 writes it."""
    link = f'<dt>URL</dt><dd><a href="{url}">{url}</a></dd>\n' if url else ''
    return (f'<html>\n<head>\n<meta charset="UTF-8">\n<meta name="generator" content="Screenotate 3.0.0">\n'
            f'<title>{window}</title>\n</head>\n<body>\n<div>\n'
            f'<img height="350.0" src="data:image/png;base64,{base64.b64encode(image).decode()}">\n</div>\n<div>\n'
            f'<dl>\n{link}<dt>Timestamp</dt>\n<dd>{stamp}</dd>\n<dt>Window title</dt>\n<dd>{window}</dd>\n'
            f'<dt>App title</dt>\n<dd>{app}</dd>\n<dt>Text</dt>\n<dd><pre>{text}</pre></dd>\n</dl>\n</div>\n'
            '<div style="display: none">created-by-Screenotate</div>\n</body>\n</html>\n').encode()


def local(stamp: str) -> str:
    return datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S').astimezone().strftime('%Y-%m-%dT%H:%M:%S%z')


class ParseTests(unittest.TestCase):
    def test_a_page_gives_its_png_and_fields_with_entities_decoded(self):
        image = png()
        capture = parse(page(image))
        self.assertEqual(capture['png'], image)
        self.assertEqual((capture['url'], capture['window'], capture['app'], capture['text']),
                         ('https://example.com/a?b=1&c=2', 'Terminal — ssh buildhost', 'Terminal', 'Disk full & nothing written'))

    def test_a_missing_url_and_empty_text_are_none(self):
        capture = parse(page(png(), text='', url=None))
        self.assertEqual((capture['url'], capture['text']), (None, None))

    def test_the_timestamp_is_local_time_read_as_utc(self):
        expected = datetime.fromisoformat(local('2022-01-25 23:33:14'))
        for stamp in ('2022-01-25 at 11.33.14 PM', '2022-01-25 at 11.33.14 PM'):
            self.assertEqual(datetime.fromisoformat(captured_at(stamp).replace('Z', '+00:00')), expected)
        self.assertIsNone(captured_at('yesterday'))

    def test_other_pages_and_pages_without_a_screenshot_are_not_captures(self):
        self.assertIsNone(parse(b'<html><body><img src="data:image/png;base64,AAAA"></body></html>'))
        self.assertIsNone(parse(page(png()).replace(b'data:image/png;base64,', b'data:image/gif;base64,')))


class ScreenotateFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'Screenshots'
        self.folder.mkdir()
        self.notes = Notes(Path(self.temp.name) / 'notes.sqlite')
        self.library = self.open()

    def open(self):
        return Library(self.folder, Path(self.temp.name) / 'cache', Encoder(Path(self.temp.name) / 'models'), self.notes)

    def save(self, name, image, **fields):
        (self.folder / f'{name}.html').write_bytes(page(image, **fields))
        return image

    def scan(self):
        return self.library.scanner.scan()

    def ids(self, query):
        return [row['id'] for row in self.library.pictures({'q': query, 'mode': 'name'})['items']]

    def test_a_png_and_its_page_are_one_image_named_by_the_png_and_dated_by_the_capture(self):
        image = self.save('Screenshot A', png())
        (self.folder / 'Screenshot A.png').write_bytes(image)
        self.scan()
        [row] = self.library.pictures({})['items']
        self.assertEqual((row['path'], row['copies'], row['dated']), ('Screenshot A.png', 2, 'taken'))
        self.assertEqual(self.library.path(row['id']), 'Screenshot A.png')
        details = self.library.details(row['id'])
        self.assertEqual(details['capture']['app'], 'Terminal')
        self.assertEqual(details['size'], len(image))

    def test_a_page_without_its_png_shows_the_screenshot_it_embeds(self):
        image = self.save('Screenshot B', png('blue'))
        self.scan()
        [row] = self.library.pictures({})['items']
        self.assertEqual((row['path'], row['mime'], row['width']), ('Screenshot B.html', 'image/png', 32))
        self.assertEqual(self.library.display(row['id']).read_bytes(), image)
        self.assertEqual(self.library.original(row['id'], image=False), self.folder / 'Screenshot B.html')

    def test_other_html_is_not_listed(self):
        (self.folder / 'saved page.html').write_text('<html><body>Hello</body></html>')
        stats = self.scan()
        self.assertEqual((stats['found'], stats['unreadable']), (0, 0))

    def test_text_search_reads_screen_text_window_app_url_and_notes_with_every_word(self):
        self.save('one', png('red'))
        self.save('two', png('green'), text='Quarterly report', window='Budget', app='Safari', url='https://buildhost.example/')
        self.scan()
        [terminal_id, browser_id] = [self.library.pictures({'q': name, 'mode': 'name'})['items'][0]['id'] for name in ('one', 'two')]
        self.assertEqual(self.ids('disk FULL'), [terminal_id])
        self.assertEqual(self.ids('safari budget'), [browser_id])
        self.assertEqual(set(self.ids('buildhost')), {terminal_id, browser_id})
        self.assertEqual(self.ids('router'), [])
        self.library.save_note(browser_id, 'Why the router dropped again')
        self.assertEqual(self.ids('router'), [browser_id])
        self.assertEqual(self.ids('router quarterly'), [browser_id])
        self.assertEqual(self.ids('router disk'), [])

    def test_a_note_outlives_the_cache_and_its_file_and_blank_removes_it(self):
        image = self.save('Screenshot C', png())
        self.scan()
        image_id = self.library.pictures({})['items'][0]['id']
        self.assertEqual(self.library.save_note(image_id, 'Bug to report')['text'], 'Bug to report')
        (self.folder / 'Screenshot C.html').unlink()
        self.scan()
        with connect(self.library.directory) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM captures').fetchone()[0], 0)
        (self.folder / 'moved').mkdir()
        (self.folder / 'moved/Screenshot C.png').write_bytes(image)
        self.library = self.open()
        self.scan()
        self.assertEqual(self.library.details(image_id)['note']['text'], 'Bug to report')
        self.assertIsNone(self.library.save_note(image_id, '  \n'))
        self.assertIsNone(self.library.details(image_id)['note'])

    def test_one_screenshot_can_be_asked_for_by_id_as_its_tile(self):
        self.save('one', png('red'))
        self.save('two', png('green'))
        self.scan()
        rows = self.library.pictures({})['items']
        [row] = self.library.pictures({'id': rows[1]['id']})['items']
        self.assertEqual(row['id'], rows[1]['id'])
        with self.assertRaises(ValueError):
            self.library.pictures({'id': 'not-an-image'})

    def test_overlong_notes_are_refused(self):
        with self.assertRaises(ValueError):
            self.notes.save('a' * 64, 'x' * 10_001)

    def test_the_app_keeps_one_notes_file_for_every_folder(self):
        app = App(Path(self.temp.name) / 'data')
        self.assertEqual(app.notes.path, Path(self.temp.name).resolve() / 'data' / 'notes.sqlite')


if __name__ == '__main__':
    unittest.main()
