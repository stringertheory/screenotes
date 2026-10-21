"""One folder's library: its scan, visual index, map, and the queries the API answers from them."""
from datetime import UTC, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import re
import threading
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image

from server import annotations, notes, photos, screenotate
from server.atlas import Atlas
from server.cache import connect, extracted_path, preview_path, thumbnail_path, while_open
from server.groups import Groups
from server.layout import Layout
from server.scanner import FolderUnavailable, ScanCancelled, Scanner, scaled
from server.semantic import SemanticIndex

PAGE_SIZE = 80
# The most one request returns, so a jump far down the timeline loads the pages above it in a few requests.
MAX_PAGE = 2500
IMAGE_ID = re.compile(r'^[a-f0-9]{64}$')
# The most images the map shows, the newest. Each is a decoded icon in the page, and drawn every frame.
MAP_LIMIT = 25_000
# Browsers show these directly. Anything else is viewed as a converted JPEG.
WEB_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/avif', 'image/bmp'}
PREVIEW_EDGE = 4096
# Text search reads each image's file names, Screenotate's details and its note.
CAPTURE_TEXT = ("coalesce((SELECT coalesce(c.text,'')||' '||coalesce(c.window,'')||' '||coalesce(c.app,'')||' '||"
                "coalesce(c.url,'') FROM captures c WHERE c.image_id=f.image_id),'')")
# A text search's terms: a "quoted phrase", straight or curly quotes, or a word. A lone quote mark is dropped.
TERMS = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]+)["\u201c\u201d]|([^\s"\u201c\u201d]+)')
# Of a screenshot's PNG and the Screenotate page that embeds it, the PNG is the file to show and name.
PAGE_LAST = "f.path LIKE '%.html'"
# The most a viewer's time zone can be from UTC, in minutes.
MAX_OFFSET = 1440
logger = logging.getLogger(__name__)


def utc_offset(params) -> int:
    """The viewer's offset from UTC in minutes, from the `tz` parameter."""
    try:
        return max(-MAX_OFFSET, min(MAX_OFFSET, int(params.get('tz') or 0)))
    except ValueError:
        raise ValueError('Use a valid date range.') from None


def terms(query: str) -> list[str]:
    """The words and quoted phrases a text search must each find."""
    return [term for phrase, word in TERMS.findall(query) if (term := (phrase or word).strip())]


class Library:
    def __init__(self, folder: Path, directory: Path, encoder):
        self.folder = Path(folder)
        self.directory = Path(directory)
        self.photos = photos.is_library(self.folder)
        self.scanner = Scanner(self.folder, self.directory, photos.PhotosLibrary(self.directory) if self.photos else None)
        # Each image's note text, for search. The note files are the notes; this is read again after every scan.
        self.notes = {}
        # The images with a drawing beside them, for the tiles' badges. Read with the notes.
        self.drawn = frozenset()
        self.semantic = SemanticIndex(self.directory, encoder)
        self.atlas = Atlas(self.directory)
        self.layout = Layout(self.semantic)
        self.groups = Groups(self.directory, self.semantic)
        # Vectors from another model can't be mixed with MODEL's, so they go with the map and stacks made from them.
        # The vectors go last, so an interrupted clean-up finishes on the next open.
        if self.semantic.has_other_models():
            self.layout.clear()
            self.groups.clear()
            self.semantic.discard_other_models()
        self.closed = threading.Event()
        self.scan_lock = threading.Lock()
        self.semantic_lock = threading.Lock()
        self.index_wanted = False
        self.scan_state = {'state': 'ready'}
        # Bumped whenever a scan commits or the groups change, so open pages know to refresh.
        self.revision = 0
        # The date-ordered tiles for the last filters asked, at the revision they were read, so scrolling, jumping
        # down the timeline and the timeline itself page through one list instead of each grouping every image.
        self._tiles = None
        self._tiles_lock = threading.Lock()
        self.stats_path = self.directory / 'scan-status.json'
        try:
            self.stats = json.loads(self.stats_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.stats = {}
        (self.directory / 'folder.txt').write_text(str(self.folder) + '\n', encoding='utf-8')
        self.read_notes()

    def close(self):
        """Stop background work for a folder that is no longer shown."""
        self.closed.set()

    def scan(self, retry=False):
        """Bring the index in line with the folder. `retry` also reads again the files that could not be read."""
        if not self.scan_lock.acquire(blocking=False):
            return
        self.scan_state = {'state': 'scanning'}
        try:
            def progress(stats):
                self.scan_state = {'state': 'scanning', 'found': stats['found'], 'done': stats['done'], 'changed': stats['changed']}

            def committed():
                self.revision += 1
            self.stats = self.scanner.scan(progress, committed, self.closed.is_set, retry)
            # Notes written or changed outside the app, or beside screenshots this scan found, are searchable now.
            self.read_notes()
            self.stats['updated'] = datetime.now(UTC).isoformat()
            self.stats_path.write_text(json.dumps(self.stats), encoding='utf-8')
            self.scan_state = {'state': 'ready'}
            # Once the model is on this computer, new images are indexed and grouped without asking.
            if self.semantic.encoder.downloaded():
                threading.Thread(target=self.index, daemon=True).start()
        except ScanCancelled:
            self.scan_state = {'state': 'ready'}
        except FolderUnavailable as error:
            self.scan_state = {'state': 'error', 'error': str(error)}
        except Exception:
            logger.exception('Scan failed')
            self.scan_state = {'state': 'error', 'error': 'The folder could not be read completely. Rescan to retry.'}
        finally:
            self.scan_lock.release()

    def index(self):
        """Prepare new images for visual search and group near-duplicates. A call made while this runs is folded
        into another round, so images a scan adds midway are not left waiting for the next scan."""
        self.index_wanted = True
        while self.index_wanted and not self.closed.is_set() and self.semantic_lock.acquire(blocking=False):
            try:
                self.index_wanted = False
                self.semantic.index(self.closed.is_set)
                if not self.closed.is_set() and self.groups.update():
                    self.revision += 1
            except Exception:
                logger.exception('Grouping near-duplicates failed')
            finally:
                self.semantic_lock.release()

    def status(self):
        with connect(self.directory, rows=True) as db:
            images = db.execute('SELECT count(*) FROM images').fetchone()[0]
            files = db.execute('SELECT count(*) FROM files WHERE image_id IS NOT NULL').fetchone()[0]
            unreadable_count = db.execute('SELECT count(*) FROM files WHERE error IS NOT NULL').fetchone()[0]
            near = db.execute('SELECT count(*) - count(DISTINCT group_id) FROM image_groups WHERE image_id IN (SELECT id FROM images)').fetchone()[0]
        return {'counts': {'images': images, 'files': files, 'duplicates': files - images, 'nearDuplicates': near, 'unreadable': unreadable_count},
                'unlistedFolders': self.stats.get('unlisted_folders', 0), 'unreached': self.stats.get('unreached', 0),
                'photoLibraries': self.stats.get('photo_libraries', []), 'skipped': self.stats.get('skipped', {}),
                'scan': self.scan_state, 'search': self.search_status(), 'updated': self.stats.get('updated'),
                'revision': self.revision}

    def search_status(self):
        """Visual search's status. It isn't ready while the scan still has files to read, which will need preparing too."""
        search = self.semantic.status()
        if search['state'] == 'ready' and self.scan_state.get('changed', 0) > self.scan_state.get('done', 0):
            search['state'] = 'idle'
        return search

    def filters(self, params):
        """Translate the folder, type and date filters into a WHERE clause over files joined to images."""
        where, values = ['f.image_id IS NOT NULL'], []
        folder = params.get('folder', '').strip('/')
        if folder:
            where.append('(f.folder=? OR substr(f.folder,1,?)=?)')
            values += [folder, len(folder) + 1, folder + '/']
        if params.get('type'):
            where.append('i.mime=?')
            values.append(params['type'])
        # Dates are the viewer's local days, so the stored UTC times are shifted by their offset before comparing.
        offset = utc_offset(params)
        for key, operator in [('from', '>='), ('to', '<=')]:
            if params.get(key):
                date = params[key]
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                    raise ValueError('Use a valid date range.')
                datetime.strptime(date, '%Y-%m-%d')
                where.append(f'substr(datetime(coalesce(i.taken,f.modified),?),1,10){operator}?')
                values += [f'{offset:+d} minutes', date]
        if params.get('from') and params.get('to') and params['from'] > params['to']:
            raise ValueError('The end date must follow the start date.')
        return where, values

    def tiles(self, where, values, collapse=True):
        """One row per near-duplicate group, fronted by its best matching image and described by that image's newest
        matching file, newest first. Without collapsing, every matching image of the groups, best first."""
        if not collapse:
            return self._read_tiles(where, values, collapse)
        # Read before the query, so rows a scan commits meanwhile are at worst read again.
        key = (self.revision, tuple(where), tuple(values))
        with self._tiles_lock:
            if self._tiles is None or self._tiles[0] != key:
                self._tiles = (key, self._read_tiles(where, values, collapse))
            return self._tiles[1]

    def _read_tiles(self, where, values, collapse):
        condition = ' AND '.join(where)
        # Photos are dated when they were taken, and anything without EXIF by when its file was modified.
        matching = f'''WITH matching AS (
            SELECT f.path, f.image_id, f.modified, coalesce(i.taken, f.modified) AS date,
                   coalesce(g.group_id, f.image_id) AS grp, coalesce(g.score, 0) AS score,
                   row_number() OVER (PARTITION BY f.image_id ORDER BY coalesce(i.taken, f.modified) DESC, {PAGE_LAST}, f.path) AS rank,
                   count(*) OVER (PARTITION BY f.image_id) AS copies
            FROM files f JOIN images i ON i.id=f.image_id LEFT JOIN image_groups g ON g.image_id=f.image_id WHERE {condition}
        ), pictures AS (
            SELECT image_id, date, path, copies, grp,
                   row_number() OVER (PARTITION BY grp ORDER BY score DESC, date DESC, image_id) AS place,
                   count(*) OVER (PARTITION BY grp) AS members
            FROM matching WHERE rank=1
        )'''
        shown = 'WHERE p.place=1 ORDER BY p.date DESC,i.id' if collapse else 'ORDER BY p.place'
        sql = f'''{matching} SELECT i.id,i.width,i.height,i.mime,i.size,p.date,CASE WHEN i.taken IS NULL THEN 'modified' ELSE 'taken' END AS dated,
                         p.path,p.copies,p.grp AS "group",p.members
                  FROM images i JOIN pictures p ON p.image_id=i.id {shown}'''
        # Grouping needs every matching row, so SQL can't page this any cheaper than slicing the whole list.
        with connect(self.directory, rows=True) as db:
            return db.execute(sql, values).fetchall()

    def require_search(self):
        search = self.semantic.status()
        if search['indexed'] == 0:
            raise ValueError('Visual search is still getting ready.' if search['state'] in ('downloading', 'loading', 'indexing')
                             else 'Visual search is not set up yet.')

    def pictures(self, params, image_bytes=None):
        where, values = self.filters(params)
        query = params.get('q', '').strip()[:1000]
        reference = params.get('similar', '')
        group = params.get('group', '')
        only = params.get('id', '')
        if any(value and not IMAGE_ID.fullmatch(value) for value in (reference, group, only)):
            raise ValueError('Choose an image from this folder.')
        if only:
            # One image as its grid tile, for a link to it from the menu bar.
            where.append('f.image_id=?')
            values.append(only)
        if group:
            where.append('coalesce(g.group_id, f.image_id)=?')
            values.append(group)
            rows = self.tiles(where, values, collapse=False)
            return {'items': self.marked(rows), 'total': len(rows), 'offset': 0, 'hasMore': False}
        offset = max(0, int(params.get('offset', '0')))
        limit = min(MAX_PAGE, max(1, int(params.get('limit', str(PAGE_SIZE)))))
        visual = bool(image_bytes or reference or (query and params.get('mode') == 'visual'))
        if not visual:
            for word in terms(query):
                pattern = '%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                where.append(f"(f.path LIKE ? ESCAPE '\\' OR {CAPTURE_TEXT} LIKE ? ESCAPE '\\' "
                             "OR f.image_id IN (SELECT value FROM json_each(?)))")
                values += [pattern, pattern, json.dumps(self.noted(word))]
            rows = self.tiles(where, values)
        else:
            self.require_search()
            ranking = dict(self.semantic.search(text=query, image_id=reference, image_bytes=image_bytes))
            # The reference and its near-duplicates come first.
            with connect(self.directory, rows=True) as db:
                own = db.execute('SELECT coalesce((SELECT group_id FROM image_groups WHERE image_id=?), ?)', (reference, reference)).fetchone()[0]
            rows = [row for row in self.tiles(where, values) if row['id'] in ranking]
            rows.sort(key=lambda row: (row['group'] == own, ranking[row['id']]), reverse=True)
        return {'items': self.marked(rows[offset:offset + limit]), 'total': len(rows), 'offset': offset,
                'hasMore': offset + limit < len(rows)}

    def marked(self, rows) -> list[dict]:
        """Tiles as sent, each with its image's note text, or None, for the tile's badge and tooltip. Added as sent
        rather than kept in the tile cache, since a note changes without the folder changing."""
        notes, drawn = self.notes, self.drawn
        return [{**dict(row), 'note': notes.get(row['id']), 'drawn': row['id'] in drawn} for row in rows]

    def timeline(self, params):
        """How many tiles the date-ordered grid shows in each month, newest first, in the viewer's time zone: the
        IANA `zone`, so months split where the browser's calendar does, or else the fixed `tz` offset in minutes."""
        where, values = self.filters(params)
        try:
            zone = ZoneInfo(params['zone']) if params.get('zone') else None
        except (ZoneInfoNotFoundError, ValueError):
            zone = None
        if zone is None:
            zone = timezone(timedelta(minutes=utc_offset(params)))
        months = []
        for row in self.tiles(where, values):
            month = datetime.fromisoformat(row['date'].replace('Z', '+00:00')).astimezone(zone).strftime('%Y-%m')
            if months and months[-1]['month'] == month:
                months[-1]['count'] += 1
            else:
                months.append({'month': month, 'count': 1})
        return {'months': months, 'total': sum(month['count'] for month in months)}

    def facets(self):
        """The subfolders and file types present, each with how many distinct images it holds."""
        with connect(self.directory, rows=True) as db:
            pairs = db.execute('SELECT DISTINCT f.folder, f.image_id FROM files f WHERE f.image_id IS NOT NULL').fetchall()
            types = [dict(row) for row in db.execute(
                'SELECT mime, count(*) AS count FROM images GROUP BY mime ORDER BY count DESC, mime')]
        folders: dict[str, set] = {}
        for folder, image_id in pairs:
            # A folder counts the images in its subfolders too.
            parts = folder.split('/') if folder else []
            for depth in range(1, len(parts) + 1):
                folders.setdefault('/'.join(parts[:depth]), set()).add(image_id)
        return {'folders': [{'path': path, 'count': len(ids)} for path, ids in sorted(folders.items(), key=lambda item: item[0].lower())],
                'types': types}

    def details(self, image_id):
        with connect(self.directory, rows=True) as db:
            image = db.execute('SELECT * FROM images WHERE id=?', (image_id,)).fetchone()
            if not image:
                return None
            files = [dict(row) for row in db.execute(
                'SELECT path, modified FROM files WHERE image_id=? ORDER BY modified DESC, path', (image_id,))]
            capture = db.execute('SELECT url, captured, window, app, text FROM captures WHERE image_id=?', (image_id,)).fetchone()
        return {**dict(image), 'root': photos.NAME if self.photos else str(self.folder), 'source': 'photos' if self.photos else 'folder',
                'files': files, 'preview': image['mime'] not in WEB_TYPES, 'capture': dict(capture) if capture else None,
                'note': self.note(image_id), 'annotation': self.annotation(image_id)}

    def shown_files(self, image_id) -> list[str]:
        """An image's files in the folder, the one it is shown by first."""
        if self.photos:
            return []
        with connect(self.directory, rows=True) as db:
            rows = db.execute(f'SELECT path FROM files f WHERE image_id=? ORDER BY {PAGE_LAST}, path', (image_id,)).fetchall()
        return [row['path'] for row in rows]

    def note_files(self, image_id) -> list[Path]:
        """Where an image's note can be: beside each of its files, the one it is shown by first."""
        return list(dict.fromkeys(notes.note_path(self.folder, path) for path in self.shown_files(image_id)))

    def note(self, image_id):
        """An image's note as {'text', 'file'}, file being its path in the folder, or None."""
        for path in self.note_files(image_id):
            if (text := notes.read(path)) is not None:
                return {'text': text, 'file': path.relative_to(self.folder).as_posix()}
        return None

    def save_note(self, image_id, text):
        """Write an image's note beside it, in the note file it already has or else beside the file it is shown by.
        Blank text removes the note."""
        if self.photos:
            raise ValueError('Notes are kept beside screenshots in a folder, so photos in Photos have none.')
        if not isinstance(text, str):
            raise ValueError('Write the note as text.')
        places = self.note_files(image_id)
        if not places:
            raise ValueError('Choose an image from this folder.')
        kept = {key: value for key, value in self.notes.items() if key != image_id}
        if text.strip():
            notes.write(next((path for path in places if path.exists()), places[0]), text)
            kept[image_id] = text
        else:
            for path in places:
                notes.write(path, '')
        # Replaced whole, not changed in place, so a search running meanwhile reads one or the other.
        self.notes = kept
        # Text search reads notes, so the grid's tiles are read again. The revision stays, so open pages aren't
        # refreshed under the note being written.
        with self._tiles_lock:
            self._tiles = None
        return self.note(image_id)

    def annotation_place(self, image_id) -> tuple[Path, str] | None:
        """Where an image's drawing is kept, and the name of the screenshot beside it that the drawing links to: the
        drawing it already has, or else beside the file the image is shown by."""
        files = self.shown_files(image_id)
        places = [(annotations.annotation_path(self.folder, path), Path(path).name) for path in files]
        return next((place for place in places if place[0].is_file()), places[0] if places else None)

    def annotation(self, image_id):
        """An image's drawing as {'file', 'image', 'box', 'modified'}: `file` its path in the folder, `image` the
        screenshot it links to, and `box` and `modified` None until there is a drawing. None for Photos."""
        place = self.annotation_place(image_id)
        if place is None:
            return None
        path, image = place
        box = annotations.box(path)
        return {'file': path.relative_to(self.folder).as_posix(), 'image': image, 'box': box,
                'modified': path.stat().st_mtime_ns if box else None}

    def annotation_file(self, image_id) -> Path | None:
        place = self.annotation_place(image_id)
        return place[0] if place and place[0].is_file() else None

    def save_annotation(self, image_id, svg):
        """Write an image's drawing beside it. An empty SVG removes the drawing."""
        if self.photos:
            raise ValueError('Drawings are kept beside screenshots in a folder, so photos in Photos have none.')
        place = self.annotation_place(image_id)
        if place is None:
            raise ValueError('Choose an image from this folder.')
        annotations.write(place[0], svg)
        annotation = self.annotation(image_id)
        # Replaced whole, as the notes are.
        self.drawn = self.drawn | {image_id} if annotation['box'] else self.drawn - {image_id}
        return annotation

    def read_notes(self):
        """Read every note beside the folder's images into the search index, and see which images have a drawing."""
        if self.photos:
            return
        found, drawn = {}, set()
        with connect(self.directory, rows=True) as db:
            rows = db.execute('SELECT path, image_id FROM files WHERE image_id IS NOT NULL').fetchall()
        # A png and its page share one note file and one drawing, so each is read once.
        for path, image_id in dict.fromkeys((notes.note_path(self.folder, row['path']), row['image_id']) for row in rows):
            if (text := notes.read(path)) is not None:
                found[image_id] = f'{found[image_id]}\n{text}' if image_id in found else text
            if image_id not in drawn and annotations.box(path.with_suffix(annotations.SUFFIX)):
                drawn.add(image_id)
        self.notes, self.drawn = found, frozenset(drawn)

    def noted(self, word: str) -> list[str]:
        """The images whose note contains the word, ignoring case."""
        word = word.casefold()
        return [image_id for image_id, text in self.notes.items() if word in text.casefold()]

    def path(self, image_id, relative=None):
        """An image's path in the folder: the named copy if given and it holds this image, else the first."""
        with connect(self.directory, rows=True) as db:
            if relative is not None:
                row = db.execute('SELECT path FROM files WHERE image_id=? AND path=?', (image_id, relative)).fetchone()
            else:
                row = db.execute(f'SELECT path FROM files f WHERE image_id=? ORDER BY {PAGE_LAST}, path LIMIT 1', (image_id,)).fetchone()
        return row['path'] if row else None

    def original(self, image_id, relative=None, image=True):
        """The file on disk for an image, as path() picks it. A photo in Photos is written out first, and is None if
        Photos can't provide it. A Screenotate page is the screenshot it embeds, unless `image` is False."""
        path = self.path(image_id, relative)
        if path is None:
            return None
        try:
            file = self.scanner.source.file(path)
            return self.extracted(image_id, file) if image and path.lower().endswith('.html') else file
        except OSError as error:
            logger.info('Could not read %s: %s', path, error)
            return None

    def extracted(self, image_id, page: Path):
        """The PNG a Screenotate page embeds, written out once and kept."""
        target = extracted_path(self.directory, image_id)
        if not target.is_file():
            capture = screenotate.parse(page.read_bytes())
            if capture is None:
                return None
            target.parent.mkdir(exist_ok=True)
            temporary = target.with_suffix(f'.{threading.get_ident()}.tmp')
            temporary.write_bytes(capture['png'])
            while_open(temporary.replace, target)
        return target

    def thumbnail(self, image_id):
        return thumbnail_path(self.directory, image_id)

    def display(self, image_id):
        """A file the browser can show: the original when it can, otherwise a JPEG drawn once and kept."""
        path = self.original(image_id)
        if path is None:
            return None
        with connect(self.directory, rows=True) as db:
            mime = db.execute('SELECT mime FROM images WHERE id=?', (image_id,)).fetchone()['mime']
        if mime in WEB_TYPES or not path.is_file():
            return path
        preview = preview_path(self.directory, image_id)
        if not preview.is_file():
            preview.parent.mkdir(exist_ok=True)
            with Image.open(path) as source:
                image = scaled(source, PREVIEW_EDGE)
                temporary = preview.with_suffix(f'.{threading.get_ident()}.tmp')
                (image.convert('RGB') if image.mode == 'RGBA' else image).save(temporary, 'JPEG', quality=90)
                while_open(temporary.replace, preview)
        return preview

    def map(self, params):
        """The newest MAP_LIMIT filtered images with a place on the map and an icon slot in the atlas."""
        where, values = self.filters(params)
        rows = self.tiles(where, values)
        self.require_search()
        positions = self.layout.positions()
        if positions is None:
            # The first fit runs in the background, and the page follows its progress.
            self.layout.start()
            return {'points': [], 'pending': 0, 'sheets': [], 'layout': self.layout.status()}
        shown = rows[:MAP_LIMIT]
        slots = self.atlas.ensure()
        points = []
        for row in shown:
            if row['id'] in positions and row['id'] in slots:
                x, y = positions[row['id']]
                points.append({**dict(row), 'x': round(x, 4), 'y': round(y, 4), 'slot': slots[row['id']]})
        return {'points': points, 'pending': len(shown) - len(points), 'omitted': len(rows) - len(shown),
                'sheets': self.atlas.versions(), 'layout': {'state': 'ready'}}
