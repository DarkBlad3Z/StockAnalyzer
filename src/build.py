#!/usr/bin/env python3
"""
Stage 3 - assemble the deck.

Injects data/derived/today.json and data/derived/forward.json into
src/template.html and writes a single self-contained index.html.

The output is deliberately ASCII-only. The template is authored with \\uXXXX
escapes for every non-ASCII glyph because some embedded webviews serve local
files without honouring the charset declaration, which turns em-dashes and
multiplication signs into mojibake. Escaping at source sidesteps it entirely.

No network access. Pure standard library.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DER = os.path.join(ROOT, "data", "derived")

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What you pay vs. what you get - S&amp;P 500 and Nasdaq-100, to 2035</title>
<meta name="description" content="Every company in the S&amp;P 500 and Nasdaq-100 mapped on price against business quality, then projected to 2030 and 2035.">
<style>html,body{margin:0;padding:0;background:#faf7f1}body{min-height:100vh}</style>
</head>
<body>
"""
TAIL = "\n</body>\n</html>\n"


def main():
    with open(os.path.join(SRC, "template.html")) as fh:
        tpl = fh.read()
    assert all(ord(c) < 128 for c in tpl), "template.html must be pure ASCII"

    for placeholder, fname in (("/*__DATA__*/", "today.json"),
                               ("/*__FWD__*/", "forward.json")):
        path = os.path.join(DER, fname)
        if not os.path.exists(path):
            raise SystemExit("missing %s - run src/prep.py and src/model.py first" % path)
        with open(path) as fh:
            blob = fh.read()
        json.loads(blob)          # fail loudly rather than emit a broken page
        assert all(ord(c) < 128 for c in blob), "%s must be pure ASCII" % fname
        assert placeholder in tpl, "placeholder %s not found in template" % placeholder
        tpl = tpl.replace(placeholder, blob)

    doc = HEAD + tpl + TAIL
    assert all(ord(c) < 128 for c in doc)
    for stray in ("__DATA__", "__FWD__"):
        assert stray not in doc, "placeholder %s left unreplaced" % stray

    out = os.path.join(ROOT, "index.html")
    with open(out, "w") as fh:
        fh.write(doc)
    print("wrote index.html  %.0f KB  (self-contained, no external requests)" % (len(doc) / 1024))


if __name__ == "__main__":
    main()
