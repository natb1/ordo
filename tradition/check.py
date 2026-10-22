#!/usr/bin/env python3
"""Validate every appeal to tradition against tradition/sources.yaml.

Fails if a [KEY] citation is used but not registered, or if a REJECTED source is
cited anywhere: in any markdown file here, and in the Rule — which lives in the
Cadence page's store, so it is scanned from an export of it (hypomnemata ›
tradition: the check scans the Rule and the skill). Reports — without failing —
sources that are registered but never used, and the share of load-bearing
citations that are still un-audited.

    python3 tradition/check.py [--strict] [--rule DIR]
    ORDO_RULE=<export> python3 tradition/check.py

--rule DIR (or $ORDO_RULE) is the export, laid out as ArtifactData's `out_dir`
leaves it: <collection>/<doc_id>.json. Every string in every document is read, and
a finding there is named by the document and the field it stands in
(`rule/policy:todo.timebox.escalation`). Preflight runs it over the frozen copy,
tools/fixture/rule. --strict additionally fails when any cited source is
`unverified`. Not the default: un-audited is the honest starting state, not an error.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from ruleyaml import load  # strict: a key given twice fails, never wins
REGISTRY = ROOT / "tradition" / "sources.yaml"
# A citation is a bracketed all-caps key: [RB-5], [LEROY-GLOMB-2018]
CITE = re.compile(r"\[([A-Z][A-Z0-9.-]*[A-Z0-9])\]")
SKIP = {".git", "node_modules", "__pycache__"}


def scan_markdown():
    # Not sources.yaml itself: its keys are the registry, not citations.
    paths = sorted(ROOT.rglob("*.md"))
    for path in paths:
        if any(part in SKIP for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for key in CITE.findall(line):
                yield str(path.relative_to(ROOT)), str(lineno), key


def _strings(value, at=""):
    """Every string in a document, with the path of the field it stands in."""
    if isinstance(value, str):
        yield at, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{at}.{k}" if at else str(k))
    elif isinstance(value, list):
        for n, v in enumerate(value):
            yield from _strings(v, f"{at}[{n}]")


def scan_rule(export):
    """The Rule's documents, as an export lays them out."""
    for f in sorted(Path(export).glob("*/*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            print(f"ERROR  {f}: {e}")
            sys.exit(1)
        name = f"{f.parent.name}/{f.stem}"
        for field, text in _strings(doc):
            for key in CITE.findall(text):
                yield name, field, key


def scan(export=None):
    yield from scan_markdown()
    if export:
        yield from scan_rule(export)


def main() -> int:
    argv = sys.argv[1:]
    strict = "--strict" in argv
    export = os.environ.get("ORDO_RULE")
    if "--rule" in argv:
        export = argv[argv.index("--rule") + 1]
    if export and not Path(export).is_dir():
        print(f"ERROR  {export} is not a directory")
        return 1
    sources = load(REGISTRY)["sources"]

    # `unaudited` keeps each warning's key as the citation matched it: the warning's
    # own text names a field path (`steps[0]`) whose brackets are not a key's.
    used, errors, warnings, unaudited = {}, [], [], set()

    for where, at, key in scan(export):
        used.setdefault(key, []).append(f"{where}:{at}")
        entry = sources.get(key)
        if entry is None:
            errors.append(f"{where}:{at}: [{key}] is not in tradition/sources.yaml")
        elif str(entry.get("status", "")).upper() == "REJECTED":
            errors.append(
                f"{where}:{at}: [{key}] is REJECTED — {entry.get('note', '').strip()[:90]}"
            )
        elif entry.get("verified") == "unverified":
            warnings.append(f"{where}:{at}: [{key}] is un-audited")
            unaudited.add(key)

    unused = [
        k for k, v in sources.items()
        if k not in used and str(v.get("status", "")).upper() != "REJECTED"
    ]

    for e in errors:
        print(f"ERROR  {e}")
    if strict:
        for w in warnings:
            print(f"ERROR  {w}")
    elif warnings:
        distinct = sorted(unaudited)
        print(f"note   {len(warnings)} citation(s) to {len(distinct)} un-audited source(s): {', '.join(distinct)}")
    if unused:
        print(f"note   {len(unused)} registered but uncited: {', '.join(sorted(unused))}")

    cited = len(used)
    audited = sum(1 for k in used if sources.get(k, {}).get("verified", "").startswith("web-"))
    scanned = "the markdown" + (f" and the Rule at {export}" if export else "")
    print(f"\n{cited} distinct sources cited in {scanned}, {audited} audited, {cited - audited} un-audited.")

    failed = errors or (strict and warnings)
    print("FAIL" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
