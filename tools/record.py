#!/usr/bin/env python3
"""The record gate: what /ordo writes to the record, checked, as a pinned batch.

The Rule has its gate (gate.py). The record — the `days`, `todo`, `periodic` and
`synclog` documents the page writes and /ordo writes beside it — had its rules in
the skill's prose and nothing that held them. This holds them once (hypomnemata ›
record): today and the time now on the Rule's clock, the item on that date and its
parts, blocked on that day, a pour's bounds and key, and the shape of a `todo` or
`periodic` document, which it takes from the item contract, tools/items.py. /ordo says what happened as facts; this says what is written,
or refuses.

    python3 tools/record.py DIR --facts FILE --versions FILE --out DIR [--now ISO]

DIR       an export of the store: the Rule (as gate.py takes it) and every record
          document a fact touches — days/<date>.json, todo/<id>.json,
          periodic/<id>.json, synclog/<date>.json, breakdowns/<id>.json — plus
          every todo document, for what blocks what. A document with no file is one
          the store does not hold.
--facts   a JSON list; each fact is one of
            {"fact": "tick", "date", "item", "time"?, "weight"?}
            {"fact": "pour", "date", "n", "key"}
            {"fact": "close", "id", "date"?}
            {"fact": "restore", "collection", "id"}
            {"fact": "todo", "doc": {...}}        a TODO item or a dictation, captured or edited
            {"fact": "periodic", "doc": {...}}    a periodic item, captured or edited
            {"fact": "periodic-done", "id", "date"?, "focus"?}
            {"fact": "synclog", "date", "text"}
--versions the export's versions, {"<collection>/<doc_id>": version}: every write to
          a document the export holds is pinned to it
--out     where the batch goes, as gate.py lays one out: OUT/batch.json, a file per
          document. Never the export.
--now     the instant, ISO 8601, in place of the clock: for a test

What it holds. A date is YYYY-MM-DD and not after today, where today is the Rule's
clock (rule.today: meta.timezone, the day turning at meta.day_starts). A tick names
an item of rule/office that is on that date — its block's weekday, its own
weekday and skip_weekday, the fixture it follows or avoids, the season, a whole-day
fixture's keep — and is written as each of its parts; never the Examen, which the
page answers, and never when a todo item open on that day names it or its group:
blocked, not missed. Today's tick takes the time now where no time is recorded; a
past day's takes none. A pour is a whole number 1–10, or a correction no deeper
than the day holds, never 0, under `b:<key>`: the same key is the same leaf, so a
fact written twice is written once, and two numbers under one key are refused. A
todo or periodic document names an active project, blocks only ids the page
carries, keeps its dates as YYYY-MM-DD, its cadence a whole number of days and its
`then` as {what, sessions} (tools/items.py). An item its owner holds — one with a
`source` — is closed by its owner, never by a close here. A document the store holds is updated, pinned; one it
does not is set, a day as the page's blank() with the fact's leaves.

What it cannot hold is the skill's: which key names a pour's fact, whether a
`ledger` or `floor` condition was on (both are taken as on), which project an item
is for, and whether the user said what the fact says.
"""
import argparse
import copy
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate  # noqa: E402
import items  # noqa: E402
import rule  # noqa: E402
import ruledir  # noqa: E402

Refused = gate.Refused

FACTS = ("tick", "pour", "close", "restore", "todo", "periodic", "periodic-done", "synclog")


def blank(date):
    """A day as the page makes one (cadence.html blank())."""
    return {"date": date, "items": {}, "times": {}, "bells": {}, "focus": {}, "examen": {},
            "na": {}, "pours": {}, "cancelled": {}}


def ymd(v, what):
    """A date YYYY-MM-DD, by the item contract's one rule for it."""
    try:
        return items.ymd(v, what)
    except items.Refused as e:
        raise Refused(str(e))


class Record:
    """One run: the Rule, the record as exported, today, and the writes gathered."""

    def __init__(self, docs, now=None):
        self.docs = docs
        self.r = ruledir.assemble(docs)
        self.a = self.r.anchors
        self.today = rule.today(self.a, now)
        self.now_text = rule.now_text(self.a, now)
        self.at = rule.clock_now(self.a, now).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.writes = {}   # (collection, id) -> patch, merged across facts
        self.said = []     # what was not written, and why it is not a refusal
        # item id -> [(block key, item, parent or None)]: an item may stand in two
        # blocks, each on its own days (dog_2 is in vespers on improv's days and in
        # the evening on the others), and a date takes whichever is on
        self.items = {}
        for key, an in self.a["anchors"].items():
            for it in an.get("items") or []:
                self.items.setdefault(it["id"], []).append((key, it, None))
                for k in it.get("children") or []:
                    self.items.setdefault(k["id"], []).append((key, k, it))

    # ---- what the record holds --------------------------------------------
    def doc(self, c, i):
        return self.docs.get((c, i))

    def of(self, c):
        return {i: d for (cc, i), d in self.docs.items() if cc == c}

    def patch(self, c, i, p):
        cur = self.writes.setdefault((c, i), {})
        _merge(cur, p)

    # ---- the clock -------------------------------------------------------------
    def date(self, v, what):
        d = ymd(v, what)
        if d > self.today:
            raise Refused(f"{what}: {d} is after today ({self.today} on the Rule's clock); it is not moved to today")
        return d

    # ---- the day ----------------------------------------------------------------
    def events_on(self, d):
        return [c for c in self.a.get("commitments") or [] if rule.on_date(c, d)]

    def on_that_date(self, item_id, d):
        """The item's parts that are expected on the date, or Refused with why not."""
        return self.entry_on(item_id, d)[1]

    def entry_on(self, item_id, d):
        """(the item where it stands on the date, its parts expected that day): the
        first of its places that is on, or Refused with why the first is not."""
        if item_id not in self.items:
            raise Refused(f"{item_id} is not an item of rule/office")
        why = None
        for entry in self.items[item_id]:
            try:
                return entry, self._parts_on(item_id, entry, d)
            except Refused as e:
                why = why or e
        raise why

    def _parts_on(self, item_id, entry, d):
        key, it, parent = entry
        dow = rule.weekday_of(d)
        anchor = self.a["anchors"][key]
        if dow in (anchor.get("skip_weekday") or []):
            raise Refused(f"{item_id} is not on {d}: the {key} block has no {dow}")
        top = parent or it
        if top.get("examen") or it.get("examen"):
            raise Refused(f"{item_id} is the Examen, which is answered on the page, not written from here")
        cs = self.events_on(d)
        timed = [c for c in cs if not rule.whole_day(c)]
        if not rule.applies(top, dow, timed):
            raise Refused(f"{item_id} is not on {d}: {top['id']} is off on {dow}, or follows a fixture that is not on that day")
        if (top.get("when") or {}).get("not_winter") and rule.winter(self.a, d):
            raise Refused(f"{item_id} is not on {d}: {top['id']} is off in winter")
        for c in cs:
            if rule.whole_day(c) and top["id"] not in (c.get("keep") or []) and item_id not in (c.get("keep") or []):
                raise Refused(f"{item_id} is not expected on {d}: {c['id']} takes the whole day and keeps "
                              + (", ".join(c.get("keep") or []) or "nothing of the Office"))
        return [k for k in (it.get("children") or [it])]

    def blocker_of(self, item_id, group_id, d):
        """The todo item open on the day that names the item or its group."""
        for i, x in self.of("todo").items():
            if not open_on(x, d, self.today):
                continue
            names = x.get("blocks") or []
            if not isinstance(names, list):
                names = [names] if isinstance(names, str) else []
            if item_id in names or (group_id and group_id in names):
                return x
        return None

    def tick(self, f):
        d = self.date(f.get("date"), "a tick's date")
        item_id = f.get("item")
        (key, it, parent), leaves = self.entry_on(item_id, d)
        group = parent["id"] if parent else (it["id"] if it.get("children") else None)
        b = self.blocker_of(item_id, parent["id"] if parent else None, d)
        if b:
            raise Refused(f"{item_id} was blocked on {d} by {b.get('id')} ({b.get('what')}): blocked, not missed")
        day = self.doc("days", d) or {}
        p = {"date": d, "items": {}}
        time = f.get("time")
        if time is not None and not (isinstance(time, str) and rule.CLOCK12.fullmatch(time)):
            raise Refused(f"a tick's time is written as the page writes one, \"9:40 AM\", not {time!r}")
        for k in leaves:
            b = self.blocker_of(k["id"], group, d)
            if b:
                self.said.append(f"{k['id']} was blocked on {d} by {b.get('id')}: not written, not missed")
                continue
            p["items"][k["id"]] = True
            recorded = (day.get("times") or {}).get(k["id"])
            if time:
                p.setdefault("times", {})[k["id"]] = time
            elif d == self.today and not recorded:
                p.setdefault("times", {})[k["id"]] = self.now_text
            if (day.get("na") or {}).get(k["id"]) is not None:
                p.setdefault("na", {})[k["id"]] = None
        if not p["items"]:
            raise Refused(f"every part of {item_id} was blocked on {d}: blocked, not missed")
        if group and (day.get("na") or {}).get(group) is not None:
            p.setdefault("na", {})[group] = None
        if item_id == "meds":
            p["meds"] = True
        if it.get("value") or (parent or {}).get("value") or item_id == "weight":
            w = f.get("weight")
            if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
                raise Refused("the weigh-in needs the number: weight, in lb, one decimal")
            # half up, as the page's Math.round(n*10)/10 rounds it, not to even
            p["weight"] = math.floor(float(w) * 10 + 0.5) / 10
        self.patch("days", d, p)

    def pour(self, f):
        d = self.date(f.get("date"), "a pour's date")
        n, key = f.get("n"), f.get("key")
        if type(n) is not int or n == 0 or n > 10 or n < -10:
            raise Refused(f"a pour is a whole number 1-10, negative to correct, never 0: not {n!r}")
        if not isinstance(key, str) or not key.strip():
            raise Refused("a pour needs its key: what, which day, and when it was told, so the same fact is the same leaf")
        leaf = "b:" + key.strip()
        day = self.doc("days", d) or {}
        pours = day.get("pours") or {}
        if leaf in pours:
            if pours[leaf] == n:
                self.said.append(f"{d}: {leaf} already holds {n}; the same fact is written once")
                return
            raise Refused(f"{d}: {leaf} already holds {pours[leaf]}, and one fact never takes a second number; a correction is its own key")
        held = (day.get("drinks") or 0) + sum(v for v in pours.values()
                                                     if isinstance(v, (int, float)) and not isinstance(v, bool))
        if n < 0 and held + n < 0:
            raise Refused(f"{d} holds {held} drink(s); a correction of {n} takes away more than that")
        self.patch("days", d, {"date": d, "pours": {leaf: n}})

    # ---- the TODO list and the periodic items ----------------------------------------------
    def known_ids(self, except_id=None):
        ids = set(self.items)
        ids |= {c["id"] for c in self.a.get("commitments") or []}
        ids |= set(self.of("periodic"))
        ids |= {i for i in self.of("todo") if i != except_id}
        return ids

    def item_doc(self, f, collection):
        doc = f.get("doc")
        i = doc.get("id") if isinstance(doc, dict) else None
        held = self.doc(collection, i) if isinstance(i, str) else None
        owner = items.owner_of(held) or items.owner_of(doc if isinstance(doc, dict) else None)
        if owner and (held is None or set(doc) - {"id", "next"}):
            raise Refused(f"{collection}/{i} is {owner}'s, written by its owner under the item contract; "
                          "a run here writes only its next step")
        try:
            doc = items.check(collection, doc, held=held, today=self.today,
                              projects=[p["id"] for p in self.r.docket["projects"] if p.get("active", True)],
                              default_project=(self.r.todo["policy"] or {}).get("default_project"),
                              known=self.known_ids(except_id=i))
        except items.Refused as e:
            raise Refused(str(e))
        doc.setdefault("at", self.at)
        if "next" in doc and doc["next"]:
            doc.setdefault("nextAt", doc["at"])
        self.patch(collection, doc["id"], doc)

    def close(self, f):
        i = f.get("id")
        x = self.doc("todo", i)
        if x is None:
            raise Refused(f"todo/{i} is not in the export; a close needs the document read")
        d = self.date(f.get("date"), "a close's date") if f.get("date") else self.today
        if x.get("done"):
            self.said.append(f"todo/{i} is already done ({closed_on(x) or 'no date'}); nothing changes")
            return
        if items.owner_of(x):
            raise Refused(f"todo/{i} is {items.owner_of(x)}'s, and its owner closes it; "
                          "if it is not wanted, say so on the page")
        self.patch("todo", i, {"id": i, "done": True, "doneAt": d, "at": self.at})
        b = self.doc("breakdowns", i)
        if b is not None and b.get("open") is not False:
            self.patch("breakdowns", i, {"open": False, "closed": d})

    def restore(self, f):
        c, i = f.get("collection"), f.get("id")
        if c not in ("todo", "periodic"):
            raise Refused(f"a restore is of a todo or a periodic item, not {c!r}")
        if self.doc(c, i) is None:
            raise Refused(f"{c}/{i} is not in the export; a restore needs the document read")
        p = {"id": i, "removed": False, "at": self.at}
        if c == "todo":
            p["done"] = False
            p["doneAt"] = None
        self.patch(c, i, p)

    def periodic_done(self, f):
        i = f.get("id")
        x = self.doc("periodic", i)
        if x is None:
            raise Refused(f"periodic/{i} is not in the export; a done needs the document read")
        d = self.date(f.get("date"), "a done's date") if f.get("date") else self.today
        p = {"id": i, "history": {d: True}, "due": None, "at": self.at}
        if isinstance(x.get("history"), list):
            # an older page kept a list, which a merge would replace whole: carry
            # its dates over into the map
            p["history"] = {**{h: True for h in x["history"] if isinstance(h, str)}, d: True}
        if x.get("then") and d == self.today:
            day = self.doc("days", d) or {}
            if not (day.get("items") or {}).get(i):
                focus = f.get("focus")
                if not isinstance(focus, str) or not focus:
                    raise Refused(f"periodic/{i} has a follow-up, so its done today needs focus: the session it went in")
                p["started"] = {"date": d, "focus": focus}
        self.patch("periodic", i, p)

    def synclog(self, f):
        d = self.date(f.get("date"), "a synclog's date")
        if not isinstance(f.get("text"), str):
            raise Refused("a synclog carries text")
        self.patch("synclog", d, {"date": d, "text": f["text"]})

    # ---- the run ------------------------------------------------------------------
    def take(self, facts):
        if not isinstance(facts, list):
            raise Refused("the facts are a JSON list")
        for n, f in enumerate(facts):
            if not isinstance(f, dict) or f.get("fact") not in FACTS:
                raise Refused(f"fact {n}: is one of " + ", ".join(FACTS))
            kind = f["fact"]
            try:
                {"tick": self.tick, "pour": self.pour, "close": self.close, "restore": self.restore,
                 "todo": lambda f: self.item_doc(f, "todo"),
                 "periodic": lambda f: self.item_doc(f, "periodic"),
                 "periodic-done": self.periodic_done, "synclog": self.synclog}[kind](f)
            except rule.RuleError as e:
                raise Refused(f"fact {n}: {e}")
            except Refused as e:
                raise Refused(f"fact {n} ({kind}): {e}")

    def writes_out(self):
        """(op, key, data) per document, as gate.emit takes them."""
        out = []
        for (c, i), p in sorted(self.writes.items()):
            if self.doc(c, i) is not None:
                out.append(("update", (c, i), p))
            elif c == "days":
                d = blank(i)
                _merge(d, p)
                if i < self.today:
                    d["backfilled"] = True
                out.append(("set", (c, i), d))
            else:
                out.append(("set", (c, i), p))
        return out


def _merge(into, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(into.get(k), dict):
            _merge(into[k], v)
        else:
            into[k] = copy.deepcopy(v)


# The page's openOn and the date an item closed are the item contract's (tools/items.py).
closed_on, open_on = items.closed_on, items.open_on


def run(docs, facts, now=None):
    rec = Record(docs, now)
    rec.take(facts)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("--facts", required=True)
    ap.add_argument("--versions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--now")
    args = ap.parse_args(argv)
    try:
        out, export = Path(args.out).resolve(), Path(args.dir).resolve()
        if out == export or export in out.parents:
            raise Refused(f"--out {args.out} is the export or inside it; give the batch a directory of its own")
        try:
            (out / "batch.json").unlink(missing_ok=True)
        except OSError as e:
            raise Refused(f"--out {args.out}: {e}")
        docs = ruledir.read(args.dir)
        facts = gate.given(args.facts, "--facts")
        versions = gate.given(args.versions, "--versions")
        if not isinstance(versions, dict):
            raise Refused('--versions is a JSON map {"<collection>/<doc_id>": version}')
        rec = run(docs, facts, args.now)
        writes = rec.writes_out()
        for line in rec.said:
            print("said    " + line)
        if not writes:
            print("ok  nothing to write")
            return 0
        batch = gate.emit(writes, versions, args.out, held=set(docs))
    except (Refused, ruledir.RuleDirError) as e:
        for line in str(e).splitlines():
            print("REFUSED ", line)
        print("REFUSED  nothing is to be written")
        return 1
    for e in batch:
        pin = f"  @{e['if_version']}" if "if_version" in e else "  (new)"
        print(f"{e['op']:<7}{e['collection']}/{e['doc_id']}{pin}")
    print(f"ok  {len(batch)} write(s) in {Path(args.out) / 'batch.json'}; today is {rec.today} on the Rule's clock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
