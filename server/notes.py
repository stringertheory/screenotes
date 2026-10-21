"""Notes on screenshots, each a plain text file beside its screenshot.

`Screenshot 2022-01-25 at 11.33.14 PM.txt` is the note on `Screenshot 2022-01-25 at 11.33.14 PM.png` and `.html`: they
go together by name, the way Screenotate's own two files do. The text file is the whole note, so it can be read,
edited, searched and backed up without this app, and the app keeps only an index of them for search.
"""
import os
from pathlib import Path

# Long enough for any note, and within what a JSON request may carry.
NOTE_LIMIT = 10_000
SUFFIX = '.txt'


def note_path(folder: Path, relative: str) -> Path:
    """Where the note on the screenshot at `relative` in `folder` is kept."""
    return Path(folder, relative).with_suffix(SUFFIX)


def read(path: Path) -> str | None:
    """A note's text, or None when there is no note."""
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def write(path: Path, text: str):
    """Keep a note, or remove it when the text is blank. The new text replaces the old in one step, so a note is never
    left half written."""
    if not isinstance(text, str) or len(text) > NOTE_LIMIT:
        raise ValueError(f'Keep the note under {NOTE_LIMIT:,} characters.')
    if not text.strip():
        path.unlink(missing_ok=True)
        return
    # Hidden, so Finder doesn't show it for the moment it exists.
    temporary = path.with_name(f'.{path.name}.saving')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)
