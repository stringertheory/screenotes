"""Drawings on screenshots, each an SVG beside its screenshot.

`Screenshot 2022-01-25 at 11.33.14 PM.svg` is the drawing on `Screenshot 2022-01-25 at 11.33.14 PM.png`, paired by
name as notes are. The page draws it in Excalidraw and saves Excalidraw's own SVG export, with the scene embedded so
excalidraw.com can open it again. The screenshot is in it only as a link to the PNG beside it, never a copy, so the SVG
opened on its own shows the screenshot with the drawing over it. Its coordinates are the screenshot's pixels: the
viewBox says where the drawing reaches, which can be past the screenshot's edges.
"""
import html
import os
from pathlib import Path
import re

# Room for pasted images, which the SVG holds itself.
ANNOTATION_LIMIT = 30 * 1024 * 1024
SUFFIX = '.svg'
# The root element and its viewBox come first, so a few kilobytes find them however large the drawing is.
HEAD = 4096
ROOT = re.compile(r'<svg\b[^>]*>', re.S)
VIEW_BOX = re.compile(r'\bviewBox\s*=\s*["\']\s*([-+\d.eE\s,]+?)\s*["\']')
# Excalidraw marks its exports just inside the root. Any other SVG of the screenshot's name is someone else's file.
SOURCE = '<!-- svg-source:excalidraw -->'
# Excalidraw draws each line of its text as one <text> element, with the text itself escaped.
TEXT = re.compile(r'<text\b[^>]*>([^<]*)</text>')


def annotation_path(folder: Path, relative: str) -> Path:
    """Where the drawing on the screenshot at `relative` in `folder` is kept."""
    return Path(folder, relative).with_suffix(SUFFIX)


def head(path: Path) -> str | None:
    try:
        with open(path, encoding='utf-8', errors='replace') as stream:
            return stream.read(HEAD)
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def box(path: Path) -> list[float] | None:
    """The part of the screenshot's pixel grid a drawing covers, as [x, y, width, height], or None when there is no
    drawing: no file, or an SVG that isn't Excalidraw's or has no viewBox."""
    text = head(path)
    if text is None or SOURCE not in text:
        return None
    root = ROOT.search(text)
    found = root and VIEW_BOX.search(root.group(0))
    try:
        values = [float(value) for value in re.split(r'[\s,]+', found.group(1))] if found else []
    except ValueError:
        return None
    return values if len(values) == 4 and values[2] > 0 and values[3] > 0 else None


def text(path: Path) -> str | None:
    """The words written in a drawing, a line each, for search: '' for a drawing without any, None for no drawing."""
    if box(path) is None:
        return None
    try:
        svg = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    return '\n'.join(line for match in TEXT.finditer(svg) if (line := html.unescape(match.group(1)).strip()))


def write(path: Path, svg: str):
    """Keep a drawing, or remove it when there is none. The new SVG replaces the old in one step. An SVG there that
    Excalidraw didn't make is never replaced or removed."""
    if not isinstance(svg, str) or len(svg) > ANNOTATION_LIMIT:
        raise ValueError(f'Keep the drawing under {ANNOTATION_LIMIT // 1024 // 1024} MB. Paste smaller images.')
    existing = head(path)
    if existing is not None and SOURCE not in existing:
        raise ValueError(f'{path.name} is already there and is not a drawing, so it was left alone.')
    if not svg.strip():
        path.unlink(missing_ok=True)
        return
    if not ROOT.match(svg.lstrip()) or SOURCE not in svg[:HEAD]:
        raise ValueError('The drawing could not be saved: it is not an SVG from Excalidraw.')
    temporary = path.with_name(f'.{path.name}.saving')
    temporary.write_text(svg, encoding='utf-8')
    os.replace(temporary, path)
