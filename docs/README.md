# Web version

`index.html` runs `pubfingerprint` entirely in the visitor's browser with [Pyodide](https://pyodide.org): enter an ORCID iD, get the profile, download the two-page PDF. No server and no data storage; the browser fetches the public ORCID record and the matching OpenAlex works directly.

## Publish with GitHub Pages
1. Push the repository to GitHub.
2. Settings → Pages → "Deploy from a branch" → branch `main`, folder `/docs` → Save.
3. After a minute the page is at https://tgossmann.github.io/pubfingerprint/.

## Keep the code in sync
The page loads the Python files from `docs/py/`. After changing `pubfingerprint.py`, `publication_map.py` or `web_adapter.py`, run `sh docs/update_web.sh` from the repository root.

## Test locally
Web workers do not run from `file://`. Serve the folder instead: `python3 -m http.server -d docs 8000`, then open http://localhost:8000.

## Differences from the command line
The web version takes author lists from OpenAlex (the command line uses Crossref), so co-author counts can differ slightly. Shared first authorship and approaches are not available automatically; download the CSV, complete it and use the command line for the full profile.
