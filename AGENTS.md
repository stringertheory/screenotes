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
- `server/notes.py` and `Library.note`/`save_note`/`read_notes`: a note is a plain UTF-8 text file beside its
  screenshot, `<name>.txt` for `<name>.png`/`.html`, paired by name only, as Screenotate pairs its two files. The file
  is the whole note (no header). A new note goes beside the file the image is shown by; clearing it deletes the file;
  saves go through a hidden temporary file and `os.replace`. `Library.notes` is only a search index (image id → text),
  read when the library opens and after every scan, so edits made outside the app show up on the next scan. Renames
  aren't followed: a `.txt` with no screenshot of its name is ignored. Photos libraries have no notes.
- `server/menubar.py` and `web/src/Menu.tsx`: `--menubar` runs an NSStatusItem whose NSPopover holds a WKWebView of
  `/menu`. The page sends `{action, value}` string messages through `window.webkit.messageHandlers.screenotes`;
  `menubar.action()` validates them and opens `/?image=<id>` or `/?mode=name&q=…` in the default browser. With a
  server already on the port, the item attaches to it.
- `web/src/Note.tsx`: the autosaving note box. Saving a note clears the tile cache but doesn't bump the revision, so
  the grid doesn't reload under the viewer. The viewer reloads an image's details, and so remounts the note box, only
  when `item.id` changes: depending on anything that changes on every render (the status poll re-renders App every
  1–4 s) wipes the note being typed.
- `web/src/Panels.tsx` `SearchControls`: the Text and notes | Appearance switch and Like a file… under the search
  bar. The mode is saved in localStorage (`screenotes.search.mode`, text by default). The menu's WKWebView has its own
  storage, so the menu and the browser remember their modes separately.
- Orchard's update check (`server/updates.py`, `/api/updates`) asks about Orchard's releases, so its checkbox is
  left out of Info and it never runs. The code stays untouched so upstream changes to it merge cleanly.

## Names, versions and ports

- `app.json`: `name` is what the app shows (`Screenshots`); `slug` (`screenotes`) names the data dir
  (`~/Library/Application Support/screenotes`) and localStorage keys. Don't change the slug: notes would be left in
  the old dir. Port 4410 and dev port 5183, so it runs beside Orchard (4400/5173).
- Bump the version in `app.json` and `package.json` together (a test checks they agree) whenever the server's API
  changes. A launch that finds an older version already serving the port exits with "Quit it" instead of attaching,
  since an old server silently ignores newer requests (that is how the menu once opened the wrong screenshot).
- The favicon and Dock icon are the Screenotes mark (`public/`, `assets/screenotes.*`); the header shows only the
  name. `docs/orchard-logo*.svg` are kept for `docs/orchard-readme.md`. `scripts/install-app` still builds an
  `Orchard.app`.
- The rest of `docs/` is Orchard's and describes the base app.

## Login item

`scripts/install-login-item [--label name] [--remove]` fills in `scripts/login-item.plist.in` as `<label>.plist` in the
repo root (gitignored; default label `local.screenotes.menubar`), symlinks it into `~/Library/LaunchAgents` and
bootstraps it. It runs `.venv/bin/python -m server.api --menubar` with no folder, so the last one opened. `KeepAlive`
is `SuccessfulExit=false`: a crash restarts it, Quit (a clean exit) doesn't. Log: `~/Library/Logs/<label>.log`.
`launchctl bootout` returns before the old process exits, and bootstrapping the same label before then fails with
"Input/output error", so the script waits for the label to disappear first.

## Security

The server binds to `127.0.0.1` only. Orchard's `Handler.allowed()` checks the exact Host (against DNS rebinding) and
Origin / Sec-Fetch-Site (against other websites, even on other local ports), and POSTs must be JSON. The menu page
asks the native side for things (opening a URL, Quit) through the WebKit message handler rather than HTTP, so no web
page can ask for them; `menubar.action()` accepts only known actions and a valid image id.

## Checks

```bash
npm run test    # Python tests
npm run lint    # ruff, ESLint, tsc
npm run build   # rebuild dist/, which is committed
npm run test:ui # Playwright smoke test (once: npx playwright install chromium)
```

Never print screenshot contents (OCR text, window titles, URLs) from the real folder while testing: report counts.

The repo is public, and no screenshot may ever be committed: not the real folder's, and not a copy made to reproduce
a bug. Test images are made in code. `scripts/check-no-screenshots` runs as the pre-commit hook (`git config
core.hooksPath .githooks`) and in the tests; a new image the app itself needs goes in its `ALLOWED` list and in
`.gitignore`. Keep personal paths, hostnames and labels out of committed files: the login item's plist is made from
`scripts/login-item.plist.in` by `scripts/install-login-item`.

## Merging Orchard

`git fetch upstream && git merge upstream/main`, never a rebase. Expect conflicts in `dist/` (take either side, then
`npm run build`), `app.json` (keep ours) and wherever both edited the header (`App.tsx`, `styles.css`). Orchard's
`.github/workflows/release.yml` is deleted here, since it builds and drafts Orchard-named releases for `v*` tags (its
description in `docs/development.md` is Orchard's); if a merge brings changes to it, keep it deleted with `git rm`. Run every
check before committing the merge.

Never rewrite Orchard's commits: some are GitHub-signed merges, and `git filter-repo` strips signatures by default,
which changes their ids and makes every later merge replay Orchard's history. Limit any rewrite to the fork with
`--refs main ^upstream/main`. Push only `main`: the repo also holds Orchard's tags and remote branches.

## Next

The list of planned work is in the README, under "Ideas for later".
