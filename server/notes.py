"""Notes written about images, kept apart from any folder's cache: a cache can be deleted and rebuilt, and a note can't.

Notes are keyed by the image's content hash, so one follows its image through renames and moves, into any folder that
holds it, and stays when its file is gone for a while.
"""
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

# Long enough for any note, and within what a JSON request may carry.
NOTE_LIMIT = 10_000


class Notes:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS notes (
                    image_id TEXT PRIMARY KEY, text TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL
                );
            ''')

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, image_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute('SELECT text, created, updated FROM notes WHERE image_id=?', (image_id,)).fetchone()
        return dict(row) if row else None

    def save(self, image_id: str, text: str) -> dict | None:
        """Keep a note, or remove it when the text is blank. Returns the note as kept."""
        if not isinstance(text, str) or len(text) > NOTE_LIMIT:
            raise ValueError(f'Keep the note under {NOTE_LIMIT:,} characters.')
        with self._connect() as db:
            if not text.strip():
                db.execute('DELETE FROM notes WHERE image_id=?', (image_id,))
                return None
            now = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
            db.execute('INSERT INTO notes VALUES (?,?,?,?) ON CONFLICT(image_id) DO UPDATE SET text=excluded.text, '
                       'updated=excluded.updated', (image_id, text, now, now))
        return self.get(image_id)

    def matching(self, word: str) -> list[str]:
        """The images whose note contains the word, ignoring case."""
        pattern = '%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        with self._connect() as db:
            return [row[0] for row in db.execute("SELECT image_id FROM notes WHERE text LIKE ? ESCAPE '\\'", (pattern,))]
