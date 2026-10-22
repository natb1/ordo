#!/usr/bin/env python3
"""Inline the shared web assets into the pages that declare them, or check them.

A published artifact is one file, so a page cannot link tokens.css or layout.js —
it has to carry a copy, and a copy is a second source of truth. So the copies are
generated and preflight fails when one has gone stale.

A page declares what it carries, which means this tool needs no manifest:

    /* @inline:begin web/tokens.css */
    ...generated, do not edit...
    /* @inline:end */

A themed sheet has a copy of its own to keep. Its dark values are written once,
under prefers-color-scheme, and the block a forced [data-theme="dark"] needs is
generated from them where the sheet declares it:

    /* @dark:begin */
    :root[data-theme="dark"]{ ...generated... }
    /* @dark:end */

CSS cannot share one body across a media-query boundary, and two hand-written
copies are where a value gets changed in one and forgotten in the other.

    python3 tools/sync_assets.py            # write the copies
    python3 tools/sync_assets.py --check    # fail if any copy is stale (preflight)
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted(ROOT.glob("web/*.html"))

BEGIN = "@inline:begin"
END = "/* @inline:end */"
# The leading indentation is part of the region, so rewriting is idempotent
# rather than indenting the block one more level on every run. A region may not
# run past another begin marker: with one end marker lost, the match would
# otherwise swallow the next region whole and a rewrite would delete it.
REGION = re.compile(
    r"([ \t]*)/\* " + re.escape(BEGIN) + r" (?P<src>\S+)[^*]*\*/\n"
    r"(?:(?!" + re.escape(BEGIN) + r").)*?[ \t]*" + re.escape(END),
    re.S,
)
# Any mention of a marker at all, however mangled, so that one the exact pattern
# above cannot read is reported rather than silently skipped.
MARKER = re.compile(r"@inline:(?:begin|end)")
# A source file explains itself at the top for whoever edits it. That prose is for
# the source, not for every byte of a published artifact, so it is left behind.
HEADER = re.compile(r"\A(?:\s*/\*.*?\*/\s*)+", re.S)

DARK_SOURCE = re.compile(
    r'@media \(prefers-color-scheme:\s*dark\)\{:root:not\(\[data-theme="light"\]\)\{(.*?)\}\}', re.S)
DARK_BEGIN, DARK_END = "/* @dark:begin", "/* @dark:end */"
DARK_REGION = re.compile(re.escape(DARK_BEGIN) + r"[^*]*\*/\n.*?" + re.escape(DARK_END), re.S)


def derive_dark(name, css, errors):
    """The sheet with its [data-theme="dark"] block regenerated from the
    prefers-color-scheme one. A sheet that mentions the media query without both
    is an error, as it always was: the artifact's dialect needs the pair."""
    if "prefers-color-scheme" not in css:
        return css
    src, region = DARK_SOURCE.search(css), DARK_REGION.search(css)
    if not src or not region:
        errors.append(f"{name}: mentions prefers-color-scheme but has no dark block under it "
                      "with a @dark region to derive the [data-theme=dark] block into")
        return css
    block = (f"{DARK_BEGIN} — generated from the prefers-color-scheme block above; edit that, not this */\n"
             f':root[data-theme="dark"]{{{src.group(1)}}}\n{DARK_END}')
    return css[:region.start()] + block + css[region.end():]


def main():
    args = sys.argv[1:]
    if args not in ([], ["--check"]):
        # an unknown flag must not fall through to the mode that rewrites files
        sys.exit(f"usage: sync_assets.py [--check]; not {' '.join(args)}")
    check = args == ["--check"]
    errors, stale, updates, sources, regions = [], [], {}, {}, 0

    def source(src):
        """A source as inlined: its derived block current, its header left behind."""
        if src not in sources:
            path = ROOT / src
            text = path.read_text()
            derived = derive_dark(src, text, errors)
            if derived != text:
                stale.append((src, "its [data-theme=dark] block is stale"))
                updates[src] = (path, derived)
            sources[src] = HEADER.sub("", derived).rstrip("\n")
        return sources[src]

    for page in PAGES:
        text = page.read_text()
        rel = str(page.relative_to(ROOT))

        def replace(m):
            indent, src = m.group(1), m.group("src")
            if not (ROOT / src).exists():
                errors.append(f"{rel}: inlines {src}, which does not exist")
                return m.group(0)
            lines = "\n".join((indent + l if l.strip() else "") for l in source(src).split("\n"))
            return (
                f"{indent}/* {BEGIN} {src} — generated; edit that file, not this */\n"
                f"{lines}\n{indent}{END}"
            )

        updated, n = REGION.subn(replace, text)
        regions += n
        markers = len(MARKER.findall(text))
        if markers != 2 * n:
            errors.append(f"{rel}: {markers} inline marker(s) but {n} well-formed region(s) — "
                          "a begin or end marker is missing or mistyped")
            continue
        if updated != text:
            stale.append((rel, "has drifted from the files it inlines"))
            updates[rel] = (page, updated)

    for e in errors:
        print("ERROR ", e)
    if errors:
        sys.exit(1)

    if check and stale:
        for rel, why in stale:
            print(f"ERROR  {rel} {why}")
        print("       run: python3 tools/sync_assets.py")
        sys.exit(1)

    for rel, _ in stale:
        path, updated = updates[rel]
        path.write_text(updated)
        print(f"wrote  {rel}")
    if not stale:
        print(f"ok  {regions} inlined region(s) across {len(PAGES)} page(s) are current")


if __name__ == "__main__":
    main()
