#!/usr/bin/env python3
"""The item contract: the shape of a `todo` or `periodic` document, held once.

Split from the record gate (tools/record.py, which takes its item check from here)
so that an owner outside this repository — another repository's own
tool, say — imports it as a flake input rather than copying it
(hypomnemata › record, the item contract). It needs only three lists, not the Rule:
the active projects, the policy's default project, and the ids an item may name in
`blocks`; and today on the Rule's clock, for a capture's date.

    python3 tools/items.py lists DIR                      the lists, from an export
    python3 tools/items.py check --lists FILE --docs FILE [--owner NAME] [--now ISO]

`lists` prints {"projects", "default_project", "known", "today"} from an export of
the store, as tools/record.py reads one. `check` takes those lists and a JSON list of
{"collection", "doc", "held"?} — `held` is the document as the store holds it, or
absent for a capture — and prints each document as it is to be written, or REFUSED
and nothing. A capture is of an id the lists do not know: one they know is held,
and its write is an update, with `held` given. An id is written once in a batch.
The batch's own ids count as known, so one item may block another captured with
it. Each is stamped `at`, the instant (--now, else the clock), as the
record gate stamps its own. With --owner the writes are that owner's, and the
protocol below is checked as well. An owner needs only `lists`' output and `check`:
never the Rule, the fixture or anything else of this repository's.

A document. Its id is lowercase letters, digits, `-` and `_`, at most 64. It has
`what`. Its project is an active project, the policy's default where none is given.
`blocks` is a list of ids the page carries, or q:<project>:<question>. Its dates
(captured, by, due, last, and an owner's doneAt) are YYYY-MM-DD. A periodic item's cadence is a whole
number of days, at least 1; its `then` is {what, sessions}; its history a map of
dates. A todo item's kind is dictation or nothing, and a capture is dated today.
`source`, where given, is {owner, url}: the owner a short id, the url https, and
on a todo item only, until the periodic card has an owned view. An item with a
source is owned: its owner closes it, it does not age while undated,
and the page offers only that it is not wanted.

The protocol for a write from outside (--owner). One writer per owner, which writes
in the step that commits what the item tracks.
  - Ids are stable and namespaced by the owner, `<owner>-<key>` (a garden repository's are
    garden-<key>), so a re-run updates and never duplicates.
  - Every write to a held document is an update, merged and never a set, pinned to
    the version read; a capture is a set of a document the store does not hold.
  - The owner writes its own source on every item, and never an item another owns
    or none owns.
  - It never writes removed (whether an item is wanted is the page's), next or
    nextAt (the line to resume by is the page's once written), and never moves an
    item to another project after capture.
  - It closes an item with done and doneAt, the date it closed; it never writes
    done false, and an item removed on the page is no longer its to write.
  - An update says only what changed: what, project and blocks are kept as held
    where unsaid; captured is written once, and kind never (an owned item is no
    dictation).
The store cannot refuse a write that skipped this, so the gate for an owner's
writes, as for /ordo's own, is convention and the weekly review's line per owner.
"""
import argparse
import copy
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

DOC_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}")
QUESTION = re.compile(r"q:[a-z0-9_-]+:[A-Za-z0-9_-]+")
YMD = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
OWNER = re.compile(r"[a-z][a-z0-9]{0,31}")
COLLECTIONS = ("todo", "periodic")
NEVER_BY_OWNER = ("removed", "next", "nextAt")


class Refused(Exception):
    """An item the contract does not let through; nothing is written. The one
    refusal of the gates: tools/gate.py and tools/record.py raise this class too."""


def blank_day(date):
    """A day as the page makes one (web/cadence.html blank()): the shape of a
    `days/<date>` document the store does not yet hold, held here once for every
    writer of one (tools/test_record.py holds it to the page's)."""
    return {"date": date, "items": {}, "times": {}, "bells": {}, "focus": {}, "examen": {},
            "na": {}, "pours": {}, "cancelled": {}, "drinks": None, "meds": None}


def ymd(v, what):
    if not (isinstance(v, str) and YMD.fullmatch(v)):
        raise Refused(f"{what}: {v!r} is not a date YYYY-MM-DD")
    try:
        date.fromisoformat(v)
    except ValueError:
        raise Refused(f"{what}: {v!r} is not a date")
    return v


def owner_of(doc):
    """The owner an item names in its source, or None."""
    s = (doc or {}).get("source")
    return s.get("owner") if isinstance(s, dict) else None


def check_source(doc, what):
    s = doc.get("source")
    if s is None:
        return None
    if not isinstance(s, dict) or set(s) - {"owner", "url"}:
        raise Refused(f"{what}: source is {{owner, url}}, not {s!r}")
    if not (isinstance(s.get("owner"), str) and OWNER.fullmatch(s["owner"])):
        raise Refused(f"{what}: source.owner is a short id of lowercase letters and digits, not {s.get('owner')!r}")
    u = s.get("url")
    if not (isinstance(u, str) and u.startswith("https://") and len(u) > len("https://") and not re.search(r"\s", u)):
        raise Refused(f"{what}: source.url is an https link, not {u!r}")
    return s


def check(collection, doc, *, projects, default_project, known, today, held=None, owner=None):
    """The document as it is to be written, or Refused.

    projects        the active projects' ids
    default_project the policy's default project
    known           the ids `blocks` may name (the doc's own excluded by the caller or here)
    today           YYYY-MM-DD on the Rule's clock
    held            the document as the store holds it, or None for a capture
    owner           the writer, where it is an owner outside this repository
    """
    if collection not in COLLECTIONS:
        raise Refused(f"an item is a todo or a periodic document, not {collection!r}")
    if not isinstance(doc, dict) or not isinstance(doc.get("id"), str) or not DOC_ID.fullmatch(doc["id"]):
        raise Refused(f"a {collection} fact carries a document with an id of lowercase letters and digits")
    what = f"{collection}/{doc['id']}"
    doc = copy.deepcopy(doc)
    if owner is not None:
        protocol(collection, doc, held, owner, what)
    if (held is None or "what" in doc) and not (isinstance(doc.get("what"), str) and doc["what"].strip()):
        raise Refused(f"{what}: needs what, the item's name")
    if check_source(doc, what) is not None and collection == "periodic":
        raise Refused(f"{what}: a periodic item has no owner yet; its card has no owned view, so only a todo item "
                      "carries a source")
    if held is None or "project" in doc:
        if doc.get("project") is not None and not (isinstance(doc["project"], str) and doc["project"]):
            raise Refused(f"{what}: project is a project's id, not {doc['project']!r}")
        pid = doc.get("project") or default_project
        if pid not in set(projects):
            raise Refused(f"{what}: project {pid!r} is not an active project (" + ", ".join(sorted(projects)) + ")")
        doc["project"] = pid
    blocks = doc.get("blocks")
    if blocks is not None:
        if not isinstance(blocks, list) or not all(isinstance(b, str) for b in blocks):
            raise Refused(f"{what}: blocks is a list of ids, not {blocks!r}")
        for b in blocks:
            if (b not in known or b == doc["id"]) and not QUESTION.fullmatch(b):
                raise Refused(f"{what}: blocks names {b!r}, which the page does not carry")
    if held is None or "blocks" in doc:
        doc["blocks"] = blocks or []
    for k in ("captured", "by", "due", "last") + (("doneAt",) if owner is not None else ()):
        if doc.get(k) is not None:
            ymd(doc[k], f"{what} {k}")
    if collection == "periodic":
        if owner is None or held is None or "cadence" in doc:
            if type(doc.get("cadence")) is not int or doc["cadence"] < 1:
                raise Refused(f"{what}: cadence {doc.get('cadence')!r} is not a whole number of days, at least 1")
        t = doc.get("then")
        if t is not None and not (isinstance(t, dict) and isinstance(t.get("what"), str) and t["what"].strip()
                                  and type(t.get("sessions")) is int and t["sessions"] >= 1):
            raise Refused(f"{what}: then is {{what, sessions}}, a whole number of sessions at least 1, not {t!r}")
        h = doc.get("history")
        if h is not None:
            if not isinstance(h, dict):
                raise Refused(f"{what}: history is a map of dates to true")
            for k in h:
                ymd(k, f"{what} history")
    else:
        if doc.get("kind") not in (None, "dictation"):
            raise Refused(f"{what}: kind is dictation or nothing, not {doc['kind']!r}")
        if doc.get("captured") is None and held is None:
            doc["captured"] = today
    return doc


def protocol(collection, doc, held, owner, what):
    """What an owner outside this repository may write, beyond the shape."""
    if not (isinstance(owner, str) and OWNER.fullmatch(owner)):
        raise Refused(f"the owner is a short id of lowercase letters and digits, not {owner!r}")
    if not doc["id"].startswith(owner + "-"):
        raise Refused(f"{what}: an owner's ids are namespaced, {owner}-<key>, so a re-run updates and never duplicates")
    if owner_of(doc) != owner:
        raise Refused(f"{what}: {owner} writes its own source on every item, {{owner: {owner!r}, url}}")
    if held is not None and owner_of(held) != owner:
        raise Refused(f"{what}: the store holds it as {owner_of(held) or 'no owner'}'s, not {owner}'s; it is not this owner's to write")
    if held is not None and held.get("removed"):
        raise Refused(f"{what}: it was removed on the page as not wanted, and is no longer {owner}'s to write")
    if "done" in doc and doc["done"] is not True:
        raise Refused(f"{what}: an owner closes an item and never reopens it; done is true or not written")
    if doc.get("done") is True and doc.get("doneAt") is None:
        raise Refused(f"{what}: an owner's close carries doneAt, the date it closed, YYYY-MM-DD")
    for k in NEVER_BY_OWNER:
        if k in doc:
            raise Refused(f"{what}: an owner never writes {k}; "
                          + ("whether an item is wanted is the page's" if k == "removed"
                             else "the line to resume by is the page's"))
    if held is not None and "captured" in doc and doc["captured"] != held.get("captured"):
        raise Refused(f"{what}: an owner never re-dates a capture; captured is written once")
    if doc.get("kind") is not None:
        raise Refused(f"{what}: an owner's item is a TODO item, never a dictation")
    if held is not None and "project" in doc and doc["project"] != held.get("project"):
        raise Refused(f"{what}: an owner never moves an item to another project after capture "
                      f"({held.get('project')!r} to {doc['project']!r})")


def closed_on(x):
    """The date an item was closed on: its doneAt, an older page's dated done, or
    its closed stamp; None where it is open."""
    if x.get("doneAt"):
        return str(x["doneAt"])[:10]
    if isinstance(x.get("done"), str):
        return x["done"][:10]
    return str(x["closed"])[:10] if x.get("closed") else None


def open_on(x, day, today):
    """The page's openOn: whether a todo item was open on a day, and so blocked what
    it names. One closed is open until the day it closed, except today."""
    if not x.get("what") or x.get("removed"):
        return False
    if x.get("captured") and str(x["captured"])[:10] > day:
        return False
    if x.get("done"):
        shut = closed_on(x)
        if not shut or shut < day or day == today:
            return False
    return True


def lists_from(docs, now=None):
    """The three lists and today on the Rule's clock (`now` pins the instant), from
    an export as tools/ruledir.py reads one."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import rule  # noqa: E402  only the export needs the Rule; check() does not
    import ruledir  # noqa: E402
    r = ruledir.assemble(docs)
    today = rule.today(r.anchors, now)
    known = set()
    for an in r.anchors["anchors"].values():
        for it in an.get("items") or []:
            known.add(it["id"])
            known |= {k["id"] for k in it.get("children") or []}
    known |= {c["id"] for c in r.anchors.get("commitments") or []}
    known |= {i for (c, i) in docs if c in COLLECTIONS}
    return {"projects": sorted(p["id"] for p in r.docket["projects"] if p.get("active", True)),
            "default_project": (r.todo["policy"] or {}).get("default_project"),
            "known": sorted(known), "today": today}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("lists", help="the lists, from an export of the store")
    lp.add_argument("dir")
    lp.add_argument("--now", help="the instant, ISO 8601, in place of the clock: for a test")
    cp = sub.add_parser("check", help="check documents against the lists")
    cp.add_argument("--lists", required=True)
    cp.add_argument("--docs", required=True)
    cp.add_argument("--owner")
    cp.add_argument("--now", help="the instant, ISO 8601, stamped as `at`: for a test")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "lists":
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import ruledir  # noqa: E402
            print(json.dumps(lists_from(ruledir.read(args.dir), args.now), indent=2))
            return 0
        lists = json.loads(Path(args.lists).read_text())
        items = json.loads(Path(args.docs).read_text())
        if not isinstance(items, list):
            raise Refused('--docs is a JSON list of {"collection", "doc", "held"?}')
        if not all(isinstance(x, dict) for x in items):
            raise Refused("each item is {collection, doc, held?}")
        at = args.now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        ids = [(x.get("doc") or {}).get("id") if isinstance(x.get("doc"), dict) else None for x in items]
        known = set(lists["known"]) | set(ids) - {None}
        out = []
        for n, x in enumerate(items):
            try:
                i = ids[n]
                if i is not None and ids.index(i) != n:
                    raise Refused(f"{i} is written twice in one batch; say it once")
                if x.get("held") is None and i in set(lists["known"]):
                    # a set would replace the held document whole, past the protocol's
                    # guards: removed, another owner's, captured once
                    raise Refused(f"{i} is one the store holds (or the Rule names); a write to it is an update: "
                                  "give held, the document as the store holds it")
                out.append({"collection": x.get("collection"),
                            "op": "set" if x.get("held") is None else "update",
                            "doc": check(x.get("collection"), x.get("doc"), held=x.get("held"), owner=args.owner,
                                         projects=lists["projects"], default_project=lists["default_project"],
                                         known=known, today=lists["today"])})
                out[-1]["doc"].setdefault("at", at)
            except Refused as e:
                raise Refused(f"item {n}: {e}")
    except (Refused, OSError, ValueError, KeyError) as e:
        print("REFUSED ", e)
        print("REFUSED  nothing is to be written")
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
