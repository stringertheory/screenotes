import unittest

from server.api import arguments
from server.menubar import action

URL = 'http://127.0.0.1:4410'
IMAGE = 'ab' * 32


class MenubarTests(unittest.TestCase):
    def test_a_screenshot_opens_in_the_browser_viewer(self):
        self.assertEqual(action({'action': 'open', 'value': IMAGE}, URL), ('browse', f'{URL}/?image={IMAGE}'))

    def test_a_search_opens_as_a_text_search_with_the_query_quoted(self):
        self.assertEqual(action({'action': 'search', 'value': ' disk full & more '}, URL),
                         ('browse', f'{URL}/?mode=name&q=disk%20full%20%26%20more'))

    def test_a_search_by_appearance_keeps_its_mode(self):
        self.assertEqual(action({'action': 'search', 'value': 'a cat', 'mode': 'visual'}, URL), ('browse', f'{URL}/?mode=visual&q=a%20cat'))
        self.assertEqual(action({'action': 'search', 'value': 'a cat', 'mode': 'other'}, URL), ('browse', f'{URL}/?mode=name&q=a%20cat'))

    def test_home_and_quit(self):
        self.assertEqual(action({'action': 'home'}, URL), ('browse', URL))
        self.assertEqual(action({'action': 'quit'}, URL), ('quit', None))

    def test_anything_else_is_ignored(self):
        for message in (None, 'open', {}, {'action': 'open', 'value': '../../etc'}, {'action': 'open', 'value': 'javascript:alert(1)'},
                        {'action': 'search', 'value': '  '}, {'action': 'run', 'value': 'ls'}):
            self.assertIsNone(action(message, URL), message)

    def test_menubar_is_a_way_to_show_the_app_and_the_last_one_wins(self):
        self.assertEqual(arguments(['--window', '--menubar']).show, 'menubar')
        self.assertEqual(arguments(['--menubar', '--browser']).show, 'browser')


if __name__ == '__main__':
    unittest.main()
