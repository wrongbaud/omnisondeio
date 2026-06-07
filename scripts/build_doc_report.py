#!/usr/bin/env python3
"""Render the technical-docs Markdown into a single self-contained, themed HTML report.

Source of truth is ``docs/omnisonde-documentation.md`` (copied from the app's
auto-generated ``docs/generated/DOCUMENTATION.md``). Screenshots live in
``docs/screenshots/`` and are embedded as base64 data URIs so the output is one
portable file. Output: ``docs/omnisonde-documentation.html``.

Usage::

    python scripts/build_doc_report.py

Requires the ``markdown`` package (``pip install markdown``).
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "omnisonde-documentation.md"
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "omnisonde-documentation.html"

CSS = """
:root{
  --bg-void:#08060a;--bg-plate:#0f0c10;--bg-panel:#16121a;--bg-raised:#1e1824;
  --text-primary:#e8e4ec;--text-secondary:#a89cb0;--text-dim:#6a5e72;
  --brass:#c8a24e;--brass-bright:#e0c060;--brass-dim:#8a7030;--brass-glow:rgba(200,162,78,.15);
  --crimson:#a83232;--phosphor:#30e878;
  --border:rgba(200,162,78,.18);--border-soft:rgba(200,162,78,.08);
  --mono:'JetBrains Mono','Share Tech Mono',monospace;
  --disp:'Rajdhani',-apple-system,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg-void);color:var(--text-primary);
  font-family:var(--disp);font-size:17px;line-height:1.65;-webkit-font-smoothing:antialiased;
  background-image:radial-gradient(circle at 12% 6%,rgba(200,162,78,.04) 0%,transparent 42%),
    radial-gradient(circle at 88% 92%,rgba(168,50,50,.04) 0%,transparent 42%);
  background-attachment:fixed;}
.wrap{max-width:920px;margin:0 auto;padding:48px 24px 96px;}
.doc-head{border-bottom:1px solid var(--border);padding-bottom:24px;margin-bottom:8px;}
.doc-head .eyebrow{font-family:var(--mono);font-size:.72rem;letter-spacing:.28em;
  text-transform:uppercase;color:var(--brass);}
.doc-head h1.doc-title{font-family:var(--disp);font-weight:700;font-size:clamp(2rem,5vw,3rem);
  margin:10px 0 6px;border:0;padding:0;}
.doc-head .meta{font-family:var(--mono);font-size:.8rem;color:var(--text-dim);}
h1,h2,h3,h4{font-family:var(--disp);font-weight:600;line-height:1.2;letter-spacing:-.01em;}
h1{font-size:2rem;margin:56px 0 16px;padding-bottom:8px;border-bottom:1px solid var(--border-soft);color:var(--brass);}
h2{font-size:1.5rem;margin:40px 0 12px;color:var(--brass-bright);}
h3{font-size:1.2rem;margin:28px 0 10px;color:var(--text-primary);}
p{color:var(--text-secondary);}
a{color:var(--brass);text-decoration:none;}a:hover{color:var(--brass-bright);text-decoration:underline;}
strong{color:var(--text-primary);}
code{font-family:var(--mono);font-size:.86em;color:var(--brass);background:var(--bg-plate);
  border:1px solid var(--border-soft);border-radius:3px;padding:1px 5px;}
pre{background:var(--bg-plate);border:1px solid var(--border-soft);border-left:3px solid var(--brass-dim);
  padding:16px 18px;overflow-x:auto;margin:18px 0;}
pre code{background:none;border:0;padding:0;color:var(--text-primary);font-size:.82rem;line-height:1.55;}
ul,ol{color:var(--text-secondary);}li{margin:4px 0;}
table{border-collapse:collapse;width:100%;margin:20px 0;font-size:.92rem;display:block;overflow-x:auto;}
th,td{border:1px solid var(--border-soft);padding:8px 12px;text-align:left;vertical-align:top;}
th{background:var(--bg-raised);color:var(--brass);font-family:var(--mono);font-size:.78rem;
  letter-spacing:.06em;text-transform:uppercase;}
td{color:var(--text-secondary);}tr:nth-child(even) td{background:rgba(255,255,255,.012);}
figure{margin:24px 0;}
img{display:block;width:100%;height:auto;border:1px solid var(--border-soft);
  box-shadow:0 8px 28px rgba(0,0,0,.45);}
figcaption{font-family:var(--mono);font-size:.78rem;color:var(--text-dim);
  margin-top:8px;text-align:center;}
.generated-note{background:linear-gradient(180deg,rgba(48,232,120,.05),transparent 70%),var(--bg-panel);
  border:1px solid var(--border-soft);border-left:3px solid var(--phosphor);
  padding:14px 18px;margin:24px 0;font-size:.92rem;color:var(--text-secondary);}
.generated-note em{color:var(--text-primary);font-style:normal;}
.toc{background:var(--bg-panel);border:1px solid var(--border-soft);padding:18px 24px;margin:28px 0 12px;}
.toc>ul{margin:0;padding-left:0;}
.toc ul{list-style:none;padding-left:16px;}
.toc li{margin:3px 0;}
.toc a{color:var(--text-secondary);font-size:.92rem;}
.toc a:hover{color:var(--brass);}
.backlink{display:inline-block;margin:40px 0 0;font-family:var(--mono);font-size:.8rem;
  letter-spacing:.08em;text-transform:uppercase;color:var(--brass);
  border:1px solid var(--brass-dim);padding:8px 16px;}
.backlink:hover{background:var(--brass-glow);text-decoration:none;}
"""


def _embed_image(match: re.Match) -> str:
    alt, name = match.group(1), match.group(2)
    p = SHOTS / name
    if not p.exists():
        return match.group(0)
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return (f'<figure><img alt="{alt}" src="data:image/png;base64,{b64}">'
            f'<figcaption>{alt}</figcaption></figure>')


def build() -> Path:
    raw = SRC.read_text(encoding="utf-8")

    # Pull the date out of the pandoc YAML frontmatter, then strip the block.
    date = ""
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    if m:
        dm = re.search(r'date:\s*"([^"]+)"', m.group(1))
        if dm:
            date = dm.group(1)
        raw = raw[m.end():]

    # Drop pandoc-only directives and convert the fenced div to real HTML.
    raw = raw.replace("\\newpage", "")
    raw = re.sub(r"^:::\s*\{\.generated-note\}\s*$", '<div class="generated-note">', raw, flags=re.M)
    raw = re.sub(r"^:::\s*$", "</div>", raw, flags=re.M)

    # Embed screenshots as base64 so the report is a single portable file.
    raw = re.sub(r"!\[([^\]]*)\]\(\.\./screenshots/([A-Za-z0-9_]+\.png)\)", _embed_image, raw)

    # Inject a table of contents right after the first heading.
    raw = re.sub(r"(^# .*$)", r"\1\n\n[TOC]\n", raw, count=1, flags=re.M)

    body = markdown.markdown(
        raw,
        extensions=["extra", "tables", "fenced_code", "toc", "sane_lists", "admonition"],
        output_format="html5",
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Omnisonde — Technical Documentation</title>
<meta name="description" content="Auto-generated technical documentation for Omnisonde — hardware observability and experiment orchestration.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="doc-head">
    <div class="eyebrow">Omnisonde · Technical Documentation</div>
    <h1 class="doc-title">Omnisonde</h1>
    <div class="meta">Auto-generated from the codebase{(' · ' + date) if date else ''}</div>
  </div>
{body}
  <a class="backlink" href="../index.html">&larr; Back to omnisonde.com</a>
</div>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"Wrote {out.relative_to(ROOT)} ({out.stat().st_size:,} bytes)")
