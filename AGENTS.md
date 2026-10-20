# Working on Screenotes

Screenotes is a fork of Orchard Photos (`upstream` remote, github.com/chaseleantj/orchard-photos) for browsing and
annotating a folder of Screenotate screenshots. Keep the fork's changes small and in Orchard's style, so upstream
fixes still merge: `git fetch upstream && git merge upstream/main`.

## Layout of the fork's changes

- `server/screenotate.py`: parses Screenotate 3 pages (`<img src="data:image/png;base64,…">` plus a `<dl>` of URL,
  Timestamp, Window title, App title, Text). The Timestamp is local time, with a U+202F before AM/PM on newer macOS.
- `server/scanner.py`: lists `.html` files only when their first 2 KB say Screenotate; hashes the embedded PNG, so a
  page and its `.png` are one image; writes the `captures` table, and dates the image by the capture.
- `server/library.py`: prefers the `.png` over the page for naming and showing (`PAGE_LAST`); writes out the embedded
  PNG for a page with no PNG beside it; text search matches path, `captures` fields and notes.
- `server/notes.py`: notes in `<data dir>/notes.sqlite`, not in the per-folder cache, which is disposable.
- `server/menubar.py` and `web/src/Menu.tsx`: `--menubar` runs an NSStatusItem whose NSPopover holds a WKWebView of
  `/menu`. The page sends `{action, value}` string messages through `window.webkit.messageHandlers.screenotes`;
  `menubar.action()` validates them and opens `/?image=<id>` or `/?mode=name&q=…` in the default browser. With a
  server already on the port, the item attaches to it.
- `web/src/Note.tsx`: the autosaving note box. Saving a note clears the tile cache but doesn't bump the revision, so
  the grid doesn't reload under the viewer.

## Checks

```bash
npm run test    # Python tests
npm run lint    # ruff, ESLint, tsc
npm run build   # rebuild dist/, which is committed
```

Never print screenshot contents (OCR text, window titles, URLs) from the real folder while testing: report counts.

## Next

- Fuzzy text search: SQLite FTS5 with the trigram tokenizer over screen text, titles, URL and notes.
- One search box: merge the text and visual rankings with reciprocal rank fusion (`1/(60 + rank)` summed).
- Embed note text with SigLIP's text encoder, so a note matches by meaning too.
- Menu bar: a global hotkey to open it, launch at login (a LaunchAgent named `local.screenotes`), and reusing one
  browser tab instead of opening a new one per click.
