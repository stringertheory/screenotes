# Screenotes

Screenotes lets you look through, search, and annotate screenshots you take with
[Screenotate](https://screenotate.com). The photo browsing and search is built on [Orchard](https://github.com/chaseleantj/orchard-photos).

Screenotate saves each screenshot together with the text on the screen and where it came from: the app, the window
title and, for web pages, the URL. Screenotes reads that folder and shows every screenshot in one place, newest first.
You can search by any of that text, and write a note on each screenshot, such as why you took it. The note is saved as
you type.

It also puts an item in the menu bar, like Screenotate's: your recent screenshots and a search box, one click away.
Clicking a screenshot opens it with its note.

In the menu bar, the window and the browser tab, the app is called **Screenshots**.

## What you can do

- **Browse.** Every screenshot in the folder, in a grid by date. Click one to see it full size, with the app, window
  and URL it came from, the text Screenotate read from it, and your note.
- **Write notes.** Each screenshot has a note box. Notes are saved as you type, and searching finds them too.
- **Search by text.** Type a few words. A screenshot matches when every word appears somewhere in its screen text,
  window title, app, URL, file name or note.
- **Search by appearance.** Optionally, describe what a screenshot looked like ("a bar chart", "a map"), or find
  screenshots that look like another one or like an image file. This needs a one-time download of about 500 MB, and
  runs entirely on your Mac.
- **See them on a map.** Screenshots laid out by how they look, so similar ones sit together. This also needs the
  appearance download.

Screenotes never changes, moves or deletes your screenshots. The only files it writes are your notes.

## Getting started

You need a Mac with Python 3.12, 3.13 or 3.14 (`brew install python@3.13`), and Screenotate saving screenshots to
a folder.

```bash
git clone https://github.com/stringertheory/screenotes.git
cd screenotes
./orchard ~/Documents/Screenshots --menubar
```

Use the folder Screenotate saves to, which is set in Screenotate's preferences. The first run takes a minute
or two to install what it needs, then reads the whole folder. After that, it only reads new screenshots. Next time,
`./orchard --menubar` opens the folder you used last.

Other ways to open it:

```bash
./orchard ~/Documents/Screenshots            # in its own window
./orchard ~/Documents/Screenshots --browser  # in your browser, at http://127.0.0.1:4410
```

All three share one copy. If one is already running, the others just open it.

## The menu bar item

Click the item to see your most recent screenshots and a search box. Start typing to search. Press Return to see all
the results in the browser. Click a screenshot to open it in the browser with its note.

The gear button has the settings: whether searches are by text and notes (the default) or by appearance, how many
screenshots the menu shows, and Quit.

### Starting it at login

```bash
scripts/install-login-item           # start at login, and start it now
scripts/install-login-item --remove  # stop starting at login
```

If it crashes, it restarts itself. If you quit it, it stays quit until you next log in. After updating the code,
run `scripts/install-login-item` again to restart it on the new version.

## Where your data is

- **Your screenshots** stay where Screenotate saves them. Screenotes keeps no copies.
- **Your notes** are plain text files next to the screenshots: the note on `Screenshot 2022-01-25 at 11.33.14 PM.png`
  is `Screenshot 2022-01-25 at 11.33.14 PM.txt`. You can read or edit them in any text editor. Backing up the screenshot folder backs up the notes too. A note goes with its
  screenshot by name, so if you rename a screenshot in Finder, rename its `.txt` the same way.
- **Everything else** the app keeps, in `~/Library/Application Support/screenotes`, can be rebuilt, so you don't need
  to back it up: the thumbnails, the search index and the appearance model.

## Privacy

Everything runs on your Mac. The app is reachable only from your own computer, never from other devices on your
network, and it turns away requests from other websites. Nothing about your screenshots is sent anywhere.

## Credits

Screenotes is built on [Orchard Photos](https://github.com/chaseleantj/orchard-photos), an app for browsing and searching a folder of photos. The grid, the appearance search and the map come from Orchard; Screenotes adds reading Screenotate's screenshots, the notes and the menu bar item. Orchard's own documentation is in
[`docs/`](docs/), starting with [`docs/orchard-readme.md`](docs/orchard-readme.md).

## Ideas for later

- **Fuzzy text search**, so a typo or a partial word still finds a screenshot (SQLite FTS5 with the trigram
  tokenizer, over screen text, titles, URL and notes).
- **One search box** for both kinds of search: merge the text and appearance results into one list (reciprocal rank
  fusion: each result scores `1/(60 + rank)` in each list, summed).
- **Notes found by meaning**, not just their exact words (embed note text with the same model appearance search uses).
- **A keyboard shortcut** to open the menu bar item from anywhere, like Screenotate's.
- **One browser tab** reused for screenshots opened from the menu, instead of a new tab per click.

## For development

Screenshots must never be committed to this repo. Each clone turns on a check that runs before every commit and
refuses images, pages with images inside them, and large files:

```bash
git config core.hooksPath .githooks
```

The tests run the same check over the whole repo. Tests, linting and the build are listed in [`AGENTS.md`](AGENTS.md).

## License

[MIT](LICENSE), the same as Orchard. The license keeps Orchard's copyright notice alongside the one for the Screenotes
changes.
