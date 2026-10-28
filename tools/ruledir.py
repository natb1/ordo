#!/usr/bin/env python3
"""Load the Rule from a directory of store documents, strictly.

The Rule lives in the Cadence page's store. /ordo exports it with ArtifactData and
`out_dir`, which leaves each document's fields at <dir>/<collection>/<doc_id>.json,
and every tool reads the Rule from such a directory through here.

    rule/office      meta, kinds, the blocks (`anchors`) and the variations
    rule/examen      the Examen's steps
    rule/exit_rite   the exit rite
    rule/ledger      the drink ration, the protein floor, the gated lists
    rule/policy      the docket's policy and the TODO list's
    rule/gloss       the page's short wording
    rule/gate        the backlog's gate
    commitments/<id> one calendar event
    backlog/<id>     one parked goal
    projects/<id>    the page's own fields, and the Rule's under `rule`

TODO items and periodic items are not the Rule's: they are the store's `todo` and
`periodic` collections, which the page and /ordo write directly.

The store keeps a map's keys sorted, not as written. So nothing in a document
depends on the order of a map: what is ordered is a list. The blocks are a list of
`{key: ...}`, the variations a list of `{name: ...}`, and each commitment, backlog
entry and project carries `seq`, its place among the others. load() gives the tools
the Rule as they read it, in that order.

    ORDO_RULE=<dir> python3 tools/<tool>.py     # the Rule as exported
    python3 tools/ruledir.py <dir>              # fail if it will not load
"""
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ENV = "ORDO_RULE"

# The documents of `rule` every load needs, and the collections of one document each.
SINGLE = ("office", "examen", "exit_rite", "ledger", "policy", "gloss", "gate")
# Where the Rule is beside `rule`: in OWNED the document is the Rule's; in NESTED the
# page writes beside it, and the Rule is the one field `rule`.
OWNED = ("commitments", "backlog")
NESTED = ("projects",)
FIXTURE = Path(__file__).resolve().parent / "fixture" / "rule"
# A collection or a document id as the store takes one: a single path segment.
NAME = re.compile(r"[A-Za-z0-9_.~:@+-]{1,200}")


class RuleDirError(Exception):
    """The directory does not hold a Rule."""


def named(s):
    """Whether this names a collection or a document. The name is a file's too, so
    one with a separator in it, or `..`, would be written outside the directory."""
    return isinstance(s, str) and bool(NAME.fullmatch(s)) and s not in (".", "..")


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise RuleDirError(f"found duplicate key {k!r}")
        out[k] = v
    return out


def loads(text):
    """JSON, with a key given twice in one object an error (as ruleyaml has it)."""
    return json.loads(text, object_pairs_hook=_pairs)


def read(path):
    """Every document under a directory: {(collection, doc_id): fields}."""
    path = Path(path)
    if not path.is_dir():
        raise RuleDirError(f"{path} is not a directory")
    docs = {}
    for f in sorted(path.glob("*/*.json")):
        try:
            data = loads(f.read_text(encoding="utf-8"))
        except (ValueError, RuleDirError) as e:
            raise RuleDirError(f"{f}: {e}")
        if not isinstance(data, dict):
            raise RuleDirError(f"{f}: a document is an object")
        docs[(f.parent.name, f.stem)] = data
    return docs


def write(path, docs):
    """Lay documents out as ArtifactData's `out_dir` does."""
    path = Path(path)
    for (collection, doc_id), data in docs.items():
        if not (named(collection) and named(doc_id)):
            raise RuleDirError(f"{collection!r}/{doc_id!r} is not a document's name")
        f = path / collection / (doc_id + ".json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _rule(doc):
    """The Rule's half of a document the page also writes to (projects): its `rule`
    field. A document without one is the page's alone."""
    return doc.get("rule")


def _each(docs, collection, nested=False):
    """A collection's documents as a list, by `seq` then id. The id
    is the document's name; a field that disagrees is an error."""
    rows = []
    for (c, doc_id), data in docs.items():
        if c != collection:
            continue
        r = _rule(data) if nested else data
        if r is None:
            continue
        if not isinstance(r, dict):
            raise RuleDirError(f"{collection}/{doc_id}: rule is not an object")
        if r.get("id") != doc_id:
            raise RuleDirError(f"{collection}/{doc_id}: its id is {r.get('id')!r}")
        if type(r.get("seq")) is not int:
            raise RuleDirError(f"{collection}/{doc_id}: seq {r.get('seq')!r} is not a whole number")
        rows.append(r)
    rows.sort(key=lambda r: (r["seq"], r["id"]))
    return [{k: v for k, v in r.items() if k != "seq"} for r in rows]


def _keyed(rows, key, where):
    out = {}
    for r in rows or []:
        if not isinstance(r, dict) or not r.get(key):
            raise RuleDirError(f"{where}: an entry has no {key}: {r!r}")
        if r[key] in out:
            raise RuleDirError(f"{where}: {r[key]} is given twice")
        out[r[key]] = {k: v for k, v in r.items() if k != key}
    return out


def assemble(docs):
    """The documents as the tools read the Rule: anchors (the Office and the
    calendar's events), docket (policy and projects), todo (its policy), backlog,
    ledger and gloss."""
    for name in SINGLE:
        if ("rule", name) not in docs:
            raise RuleDirError(f"rule/{name} is missing")
    office = docs[("rule", "office")]
    policy = docs[("rule", "policy")]
    anchors = dict(office)
    anchors["anchors"] = _keyed(office.get("anchors"), "key", "rule/office anchors")
    anchors["variations"] = _keyed(office.get("variations"), "name", "rule/office variations")
    anchors["commitments"] = _each(docs, "commitments")
    anchors["exit_rite"] = docs[("rule", "exit_rite")]
    anchors["examen"] = docs[("rule", "examen")].get("steps") or []
    anchors["examen_probes"] = docs[("rule", "examen")].get("probes") or []
    docket = {"policy": policy.get("docket") or {}, "projects": _each(docs, "projects", nested=True)}
    backlog = dict(docs[("rule", "gate")])
    backlog["items"] = _each(docs, "backlog")
    return SimpleNamespace(anchors=anchors, docket=docket, todo={"policy": policy.get("todo") or {}},
                           backlog=backlog, ledger=docs[("rule", "ledger")], gloss=docs[("rule", "gloss")])


def raw(docs):
    """The Rule's own documents out of an export, the page's fields left behind: what
    the gate checks and a snapshot holds (tools/gate.py), and what the counts compare
    a snapshot with (tools/counts.py)."""
    out = {}
    for (c, i), data in docs.items():
        if c == "rule" and i in SINGLE or c in OWNED:
            out[(c, i)] = data
        elif c in NESTED and data.get("rule") is not None:
            out[(c, i)] = {"id": i, "rule": data["rule"]}
    return out


def load(path):
    return assemble(read(path))


def current():
    """The Rule the tools run on: the export $ORDO_RULE names."""
    if not os.environ.get(ENV):
        sys.exit(f"needs the Rule: export the store with ArtifactData and set ${ENV} to the directory")
    try:
        return load(os.environ[ENV])
    except RuleDirError as e:
        sys.exit(f"ERROR  {e}")


def main():
    dirs = sys.argv[1:] or [os.environ[ENV]] if (sys.argv[1:] or os.environ.get(ENV)) else []
    if not dirs:
        print(f"usage: ruledir.py DIR...   (or set ${ENV})")
        return 2
    try:
        for d in dirs:
            load(d)
            print("ok", d)
    except RuleDirError as e:
        print("ERROR ", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
