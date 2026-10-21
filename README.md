# Screenotes

Screenotes is the project; in its window, menu bar item and browser tab the app is just called Screenshots.

A browser for a folder of [Screenotate](https://screenotate.com) screenshots, with a note on each one. It's a fork of
[Orchard Photos](https://github.com/chaseleantj/orchard-photos), so it keeps Orchard's timeline grid, visual search
and map, and adds what Screenotate knows about each screenshot.

Screenotes is an independent project. It is not affiliated with or endorsed by Screenotate or its author; it only reads
the files Screenotate saves.

## What it adds to Orchard

- **Screenotate pages are screenshots.** Screenotate saves each screenshot as a `.png` and a `.html` page that
  embeds the same PNG. Screenotes reads the page, so the pair is one image, and a page whose PNG is gone still shows.
- **Where it came from.** The viewer shows the app, window title and URL Screenotate recorded, and the screenshot is
  dated by when it was taken.
- **Notes.** The viewer has a note box for why you took the screenshot. It saves as you type.
- **A menu bar item.** Recent screenshots and a search, as in Screenotate's menu, opening each one in the browser. Its settings choose whether searches are of text and notes (the default) or of appearance.
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

To run it from the menu bar instead, like Screenotate:

```bash
./orchard ~/Documents/Screenshots --menubar
```

The item lists recent screenshots and searches their text and notes. Clicking one opens it in the browser, with its
note box. Return in the search field opens the full search. If Screenotes is already running in its window, the item
uses that copy.

To start the item at login, run `scripts/install-login-item`. It fills in
[`scripts/login-item.plist.in`](scripts/login-item.plist.in) for this clone as a LaunchAgent named
`local.screenotes.menubar` (choose another with `--label`), links it into `~/Library/LaunchAgents` and starts it. The
item opens the folder last opened. A crash restarts it, and Quit keeps it quit until the next login. Its log is
`~/Library/Logs/<label>.log`. After pulling new code, restart it with
`launchctl kickstart -k gui/$(id -u)/<label>`; `scripts/install-login-item --remove` stops it starting at login.

The first run installs the Python packages into `.venv`. Visual search downloads a ~500 MB model once, when you set
it up; text search and notes work without it.

The rest of the documentation in [`docs/`](docs/) is Orchard's and still describes the base app, including
[how it works](docs/how-it-works.md) and [development](docs/development.md). Orchard's own README is
[`docs/orchard-readme.md`](docs/orchard-readme.md).

## Keeping screenshots out of the repo

The screenshots this app reads never belong in the repo, and three things keep them out. `.gitignore` ignores every
image and HTML page except the app's own. [`scripts/check-no-screenshots`](scripts/check-no-screenshots) refuses any
other image, by name or by contents, a file with an image embedded in it, as a Screenotate page has, and any file
over 1 MB. It runs before each commit once the hook is turned on, which each clone does once:

```bash
git config core.hooksPath .githooks
```

`tests/test_no_screenshots.py` runs the same check over every tracked file.

## License

[MIT](LICENSE), as Orchard is. Orchard's copyright notice stays in it, beside one for the Screenotes changes.
