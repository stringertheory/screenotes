"""Read the pages Screenotate saves: the screenshot itself, embedded as a PNG, and what Screenotate knew when it was
taken, the source URL, the window and app, and the text it read off the screen."""
import base64
from datetime import UTC, datetime
from html.parser import HTMLParser
import re

# Screenotate marks its pages in a hidden div, and its generator tag, within the first few hundred bytes.
SIGNATURE = b'Screenotate'
HEAD_BYTES = 2048
FIELDS = {'URL': 'url', 'Timestamp': 'captured', 'Window title': 'window', 'App title': 'app', 'Text': 'text'}
EMBEDDED = 'data:image/png;base64,'


def is_capture(head: bytes) -> bool:
    """Whether the first bytes of an .html file are a Screenotate page's."""
    return SIGNATURE in head[:HEAD_BYTES]


def captured_at(value: str) -> str | None:
    """Screenotate's local `2022-01-25 at 11.33.14 PM` as UTC. Newer macOS puts a narrow no-break space before PM."""
    text = ' '.join(value.split())
    try:
        moment = datetime.strptime(text, '%Y-%m-%d at %I.%M.%S %p').astimezone()
    except ValueError:
        return None
    return moment.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.png = None
        self.fields = {}
        self._label = None
        self._key = None
        self._in = None

    def handle_starttag(self, tag, attrs):
        if tag == 'img' and self.png is None:
            source = dict(attrs).get('src') or ''
            if source.startswith(EMBEDDED):
                self.png = source[len(EMBEDDED):]
        elif tag == 'dt':
            self._in, self._label = 'dt', []
        elif tag == 'dd':
            self._in, self._key = 'dd', FIELDS.get(''.join(self._label or []).strip())
            if self._key:
                self.fields[self._key] = []

    def handle_endtag(self, tag):
        if tag in ('dt', 'dd'):
            self._in = None

    def handle_data(self, data):
        if self._in == 'dt':
            self._label.append(data)
        elif self._in == 'dd' and self._key:
            self.fields[self._key].append(data)


def parse(page: bytes) -> dict | None:
    """The screenshot's PNG bytes and Screenotate's fields, or None when this isn't a Screenotate page with one."""
    if not is_capture(page):
        return None
    reader = _Page()
    reader.feed(page.decode('utf-8', errors='replace'))
    reader.close()
    if not reader.png:
        return None
    try:
        png = base64.b64decode(re.sub(r'\s', '', reader.png), validate=True)
    except ValueError:
        return None
    fields = {key: ''.join(parts).strip() or None for key, parts in reader.fields.items()}
    return {'png': png, 'url': fields.get('url'), 'captured': captured_at(fields.get('captured') or ''),
            'window': fields.get('window'), 'app': fields.get('app'), 'text': fields.get('text')}
