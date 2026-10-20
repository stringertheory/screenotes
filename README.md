# Screenotes

A browser for a folder of [Screenotate](https://screenotate.com) screenshots, with a note on each one. It's a fork of
[Orchard Photos](https://github.com/chaseleantj/orchard-photos), so it keeps Orchard's timeline grid, visual search
and map, and adds what Screenotate knows about each screenshot.

## What it adds to Orchard

- **Screenotate pages are screenshots.** Screenotate saves each screenshot as a `.png` and a `.html` page that
  embeds the same PNG. Screenotes reads the page, so the pair is one image, and a page whose PNG is gone still shows.
- **Where it came from.** The viewer shows the app, window title and URL Screenotate recorded, and the screenshot is
  dated by when it was taken.
- **Notes.** The viewer has a note box for why you took the screenshot. It saves as you type.
- **Text search.** With the search set to *Text and notes*, each word must appear in the file name, the screen text,
  the window, app or URL, or the note.

Notes live in `notes.sqlite` in the data folder (`~/Library/Application Support/screenotes` on a Mac), keyed by the
screenshot's content hash. They are kept apart from the per-folder cache, so they survive a cache reset, renames and
moves. Screenotes never changes your files.

## Running it

```bash
./orchard ~/Documents/Screenshots            # its own window
./orchard ~/Documents/Screenshots --browser  # or http://127.0.0.1:4410
```

The first run installs the Python packages into `.venv`. Visual search downloads a ~500 MB model once, when you set
it up; text search and notes work without it.

The rest of the documentation in [`docs/`](docs/) is Orchard's and still describes the base app, including
[how it works](docs/how-it-works.md) and [development](docs/development.md). Orchard's own README is
[`docs/orchard-readme.md`](docs/orchard-readme.md).

## License

[MIT](LICENSE), as Orchard is.
