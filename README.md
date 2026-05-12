# Omnisonde Landing Page

Static marketing site for Omnisonde. Decoupled from the Flask app — deployable
anywhere that serves static files (GitHub Pages, Netlify, Cloudflare Pages,
plain Nginx).

## Files
- `index.html` — single-page landing site
- `styles.css` — design system (matches the main app's dark theme)
- `assets/` — logo and screenshots copied from `docs/screenshots/` and `static/`

## Preview locally
```bash
cd landing
python -m http.server 8080
# open http://localhost:8080
```

## Updating screenshots
Re-run `docs/take_screenshots.py` to refresh the source captures, then copy the
ones you want into `landing/assets/` (filenames: `board.png`, `scan.png`,
`analyze.png`, `reports.png`).

## Contact email
The contact address is set in two places in `index.html`: the `mailto:` href and
the visible link text inside `<section id="contact">`. Update both when changing.
