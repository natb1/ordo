#!/usr/bin/env python3
"""The horizon counts: at each stretch the Rule decides for, what the record says
against what was decided, as counts with their denominators and never as verdicts.

The Rule decides ahead and reads after at nested stretches (hypomnemata › horizon):
the day, the week, the month, the year, and each item in its own time. The end the
root states is read by these counts and by nothing else (hypomnemata › ti-esti, the
method), so this tool computes them from an export of the store and stores none;
the gate carries what a review read on the snapshot it writes (gate.py --counts).

    ORDO_RULE=<export> python3 tools/counts.py [--as-of DATE] [--week SUNDAY] [--record DIR] [--json]
    ORDO_RULE=<export> python3 tools/counts.py --window [--as-of DATE] [--week SUNDAY]

The export is the one /ordo makes (tools/ruledir.py): the Rule's documents and,
listed beside them, the record — `days/<date>`, `snapshots/<date>`, and the `todo`
and `periodic` items, which tell an undertaking's project and what it blocks.
--record names another directory holding the record, for a test over the frozen
Rule. --as-of pins today on the Rule's clock; the week under review is the
Sunday-to-Saturday that ended before it, or the one --week names by its Sunday.
--window prints the first date the counts read (`needs_from`, also in the report),
from the Rule alone: the export of `days` starts there, and the daily sync keeps a
passed event in the Rule until its last day is before it.

By day — of the focus slots a plan was taken for on the page, how many the closing
bell recorded as worked as planned (the plan held), worked otherwise, or not worked;
one whose bell has no record is unanswered, not unworked.
By week — each project's sessions, a slot shared by n projects charging each 1/n,
and its meetings, every one of the week's whether or not its day has come or has a
record (the page's meetingCounts: the supply is spent all the same), against its
allocation, the one edited on the project card for that week where one was (the
page's allocOf); the slots worked; and the week's record counts the weekly review
reads: anchors run, each floor item against its floor, drinks against the ration,
resume lines written and kept, bedtime, the whole-day fixtures and the meetings that
did not happen. A meeting is what the compiler and the page read as one (rule.py's
classify(), and the session it `takes` that weekday), or the event a closing bell
recorded it `closes`; the slot it took is the meeting's. A session counts for the
project an undertaking belongs to, as the page charges it, and a follow-up charges
nothing. A session a bell recorded on a day a fixture took whole is charged too, as
the page's focusCounts charges it.
By month — the backlog gate's five criteria over the weeks ending with the one
under review, each a line of facts: met or not met where a script can say, and
marked to be read at the sitting where it cannot (hypomnemata › gate). The numbers
a criterion is held to are read out of the Rule's own words for it (rule/gate ›
criteria); where the words give none the tool can read, the criterion is the sitting's.
A day a fixture takes whole is never a day with every bell answered, whatever it
keeps: it is named, as the page's Week view names it "not expected".
By year — each project's frontier against the end its notebook's root states.
Per item — how often an Office item held on the days its guard did not reach it,
beside how often it held on the days it did (hypomnemata › unprompted). A guard
does not reach a day a fixture takes whole, or, for an item the bell guards, a day
a fixture moved its bell or its bell went unanswered; an item guarded by nothing is
reached on no day. Left out: an item the day marked not applicable, one an open TODO
item blocked that day (blocked, not missed), one needed only when the ledger says,
and a floor item (owed a floor a week) on a day the floor did not need it: met by
the days before it that week, or still in reach on the days left (the page's
floorCanWait, as the day began).

Each week is read against the Rule it was lived under: the week under review
against the export, and each week before it against the dated snapshot the sitting
after it wrote (the Rule going into that review), where one holds a whole Rule; the
report says which (`read_by`). Every stretch is given twice, the period under review
and the one before it, so the review reads a trend and never an absolute. A day the
store lacks is a gap, named and never counted as a miss; so is a bell a day
backfilled from memory lacks, as the page's Week view has it, and a bell the page
withdrew (a null leaf) is no bell at all.
"""
import argparse
import json
import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate  # noqa: E402  (restored(): a snapshot read as the gate reads one)
import items  # noqa: E402
import rule  # noqa: E402
import ruledir  # noqa: E402

YMD = items.YMD
#: the fields of a day's document the page keeps as maps
MAPS = ("items", "times", "bells", "focus", "examen", "na", "pours", "cancelled")
#: how many consecutive weeks the gate reads where its words give no number
WEEKS = 4
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}


# ---- dates -------------------------------------------------------------------

def iso(d):
    return d.isoformat()


def span(first, last):
    """Every date from `first` to `last`, both in."""
    d, stop, out = rule.day_of(first), rule.day_of(last), []
    while d <= stop:
        out.append(iso(d))
        d += timedelta(days=1)
    return out


def sunday_of(d):
    """The Sunday that opens a date's week (rule/ledger › drink.week_starts)."""
    x = rule.day_of(d)
    return iso(x - timedelta(days=(x.weekday() + 1) % 7))


def week_before(as_of):
    """The Sunday-to-Saturday that ended before `as_of`: the week under review at
    a sitting, which never quotes the week it sits in."""
    d = rule.day_of(as_of, "--as-of")
    sat = d - timedelta(days=(d.weekday() - 5) % 7 or 7)
    return iso(sat - timedelta(days=6)), iso(sat)


def week_from(sunday):
    d = rule.day_of(sunday, "--week")
    if rule.weekday_of(d) != "sun":
        raise ValueError(f"--week names a week by its Sunday, and {sunday} is a {rule.weekday_of(d)}")
    return iso(d), iso(d + timedelta(days=6))


def shifted(week, days):
    lo, hi = week
    return iso(rule.day_of(lo) + timedelta(days=days)), iso(rule.day_of(hi) + timedelta(days=days))


def said(text, pattern):
    """A number the Rule's own words give — ">=6 of 7", "four consecutive weeks",
    ">=80%" — or None where they give none the tool can read."""
    m = re.search(pattern, text or "", re.I)
    if not m:
        return None
    g = m.group(1).lower()
    return int(g) if g.isdigit() else NUMBERS.get(g)


def window(backlog, end):
    """The weeks the gate reads and the first date of them, from rule/gate's words
    alone: the weeks its anchors_run names, and one before them for the trend (four
    where the words name none), ending with the Saturday `end`."""
    says = ((backlog.get("gate") or {}).get("criteria") or {})
    weeks = (said(says.get("anchors_run"), r"(\w+)\s+consecutive\s+weeks") or WEEKS) + 1
    return weeks, iso(rule.day_of(end) - timedelta(days=7 * weeks - 1))


# ---- the export --------------------------------------------------------------

def load(export, record=None):
    """The Rule as the tools read it (with its documents as exported, `docs`), and
    the record's documents: the export's own, or those of the directory `record`
    names."""
    docs = ruledir.read(export)
    r = ruledir.assemble(docs)
    r.docs = docs
    rec = ruledir.read(record) if record else docs
    return r, rec


def stripped(v):
    """A record value as the page reads it (hydrate's stripNulls): the page sends a
    leaf it removed, at any depth, as a null, and a null is nothing."""
    if isinstance(v, dict):
        return {k: stripped(x) for k, x in v.items() if x is not None}
    return v


def days_of(rec):
    """The record's days, {date: document}, each held to the shape the page writes:
    its maps are maps, and so is each bell and focus slot it records. A null leaf,
    at any depth, is dropped as the page drops it."""
    out = {}
    for (c, i), d in rec.items():
        if c != "days":
            continue
        for k in MAPS:
            if d.get(k) is not None and not isinstance(d[k], dict):
                raise ruledir.RuleDirError(f"days/{i}: {k} is not a map")
        for k in ("bells", "focus"):
            for leaf, v in (d.get(k) or {}).items():
                if v is not None and not isinstance(v, dict):
                    raise ruledir.RuleDirError(f"days/{i}: {k}.{leaf} is not a map")
        out[i] = stripped(d)
    return out


def bells_of(recd):
    """A day's bell records. The page sends a withdrawn bell as a null leaf, which
    is no bell at all."""
    return {k: v for k, v in (recd.get("bells") or {}).items() if isinstance(v, dict)}


def snapshots_of(rec, upto):
    """The weekly snapshots taken up to a date, oldest first."""
    return sorted((i, d) for (c, i), d in rec.items() if c == "snapshots" and YMD.fullmatch(i) and i <= upto)


def places(rec, docket):
    """Where an undertaking's work is charged, from the todo and periodic documents
    the export holds: each item's project (`owners`), the docket's projects
    (`known`), the default, and the dictations (a todo item of kind dictation, or an
    older page's canon one)."""
    owners, dictations = {}, set()
    for (c, i), d in rec.items():
        if c in ("todo", "periodic") and isinstance(d, dict):
            if d.get("project"):
                owners[i] = d["project"]
            if c == "todo" and (d.get("kind") == "dictation" or d.get("canon")):
                dictations.add(i)
    return SimpleNamespace(owners=owners, known={p["id"] for p in docket["projects"]},
                           default=rule.default_project(docket), dictations=dictations)


def drinks_of(recd):
    """A day's drinks as the page counts them: the plain count older pages kept, and
    the signed pours over it; None where nothing was poured or counted."""
    ps = recd.get("pours") or {}
    n = recd.get("drinks")
    if not isinstance(n, (int, float)) and not ps:
        return None
    t = n if isinstance(n, (int, float)) else 0
    t += sum(v for v in ps.values() if isinstance(v, (int, float)))
    return max(0, t)


def allocation_of(p, page, sunday, a):
    """The allocation a week is measured against, as the page's allocOf has it: the
    Rule's number, or the one edited on the project card (`allocation` beside the
    Rule in projects/<id>) for the week it names (`allocWeek`, its Sunday; an older
    page's edit, with none, for the week of its `at`). (allocation, edited)."""
    o = page or {}
    n = o.get("allocation")
    if not isinstance(n, (int, float)) or isinstance(n, bool):
        return p.get("allocation"), False
    wk = o.get("allocWeek")
    if not wk and o.get("at"):
        try:
            wk = sunday_of(rule.today(a, o["at"]))
        except (ValueError, rule.RuleError):
            wk = None
    return (n, True) if wk == sunday else (p.get("allocation"), False)


# ---- a day of the Rule -------------------------------------------------------

class Day:
    """What the Rule expects on one date: the events on it, the items and bells
    expected, the focus slots and the bell that closes each, the meetings and the
    slot each took. `today` is the date the events are classified as of (the
    sitting's; the date itself where not given) and `kinds` holds what is classified,
    shared by the days of one Rule."""

    def __init__(self, a, d, today=None, kinds=None):
        self.a, self.date, self.day = a, d, rule.weekday_of(d)
        self.today = today or d
        self.kinds = {} if kinds is None else kinds
        self.events = rule.events_on(a, d)
        self.hours = [c for c in self.events if not rule.whole_day(c)]
        self.wholes = [c for c in self.events if rule.whole_day(c)]
        self.moved = {c["sets_anchor_bell"] for c in self.hours if c.get("sets_anchor_bell")}
        self.skipped = {key for key, an in a["anchors"].items() if self.day in (an.get("skip_weekday") or [])}

    def on(self, key, it, part=None, whole=True):
        """rule.item_on, the one reading of an item on a date; `whole` False reads the
        day without its whole days."""
        return rule.item_on(self.a, it, self.date, self.events if whole else self.hours, key=key, part=part)

    def parts(self, key, it):
        """What of an item is expected: its parts (or the item itself, where it has
        none) — every one where it is expected, and where a whole day keeps only
        some of a group's parts by name, those."""
        kids = it.get("children") or []
        if self.on(key, it):
            return kids or [it]
        return [k for k in kids if self.on(key, it, part=k["id"])]

    def expected(self, key, it):
        return bool(self.parts(key, it))

    def items(self):
        for key, an in self.a["anchors"].items():
            for it in an["items"]:
                if self.expected(key, it):
                    yield key, it

    def bells(self):
        """The bells expected: a block not skipped that day; where a fixture takes
        the whole day, one with nothing on it that day or something kept of it (the
        page's bellNotExpected)."""
        out = []
        for key, an in self.a["anchors"].items():
            if key in self.skipped:
                continue
            if self.wholes:
                on = [it for it in an["items"] if self.on(key, it, whole=False)]
                if on and not any(self.expected(key, it) for it in on):
                    continue
            out.append(key)
        return out

    def breaks(self, key):
        an = self.a["anchors"][key]
        return (an.get("breaks_by_weekday") or {}).get(self.day, an.get("breaks"))

    def slots(self, every=False):
        """The focus slots of the day, each with the bell that closes it: the one
        that breaks it among the bells that ring that day. `every` gives those a
        whole day leaves unexpected too, where a bell can still record a session."""
        out = []
        for key, an in self.a["anchors"].items():
            for it in an["items"]:
                if it.get("kind") != "work":
                    continue
                if self.expected(key, it) or every and self.on(key, it, whole=False):
                    closer = next((k for k in self.a["anchors"] if k not in self.skipped and self.breaks(k) == it["id"]),
                                  None)
                    out.append((it["id"], closer))
        return out

    def kind(self, c):
        """rule.classify, as of the sitting, once per event of a Rule."""
        if c["id"] not in self.kinds:
            self.kinds[c["id"]] = rule.classify(self.a, c, self.today)
        return self.kinds[c["id"]]

    def meetings(self, docket, recd=None):
        """The meetings of the day, each with the project it spends a session of and
        the slot it took: an event the compiler and the page read as a meeting
        (classify()) and the session it `takes` this weekday; and, on a recorded day,
        an event a closing bell recorded it `closes`, which took the slot that bell
        breaks — the page's own reading of that day, which stands."""
        out = {}
        for c in self.hours:
            sort, _, takes = self.kind(c)
            if sort == "meeting":
                out[c["id"]] = (c, (takes or {}).get(self.day))
        if recd:
            ids = {c["id"]: c for c in self.hours}
            slots = {s for s, _ in self.slots(every=True)}
            for key, b in bells_of(recd).items():
                c = ids.get(b.get("closes"))
                if c and key in self.a["anchors"] and self.breaks(key) in slots:
                    out[c["id"]] = (c, self.breaks(key))
        return [(c["id"], rule.project(c, docket), out[c["id"]][1]) for c in self.hours if c["id"] in out]


def read_bells(day, recd):
    """The day's bells as the page's Week view reads them, over the bells expected:
    answered, missed, and the gaps. A day backfilled from memory with no bell of its
    own lacks a bell as a gap, never as unanswered."""
    bells = bells_of(recd)
    later = bool(recd.get("backfilled")) and all(b.get("backfilled") for b in bells.values())
    answered, missed, gaps = [], [], []
    for key in day.bells():
        (answered if key in bells else gaps if later else missed).append(key)
    return answered, missed, gaps


def project_of(u, pl):
    """The project an undertaking's work counts for, as the page charges it
    (workProject, homeProject): a frontier question (q:<project>:<id>) or an older
    canon:<project> for that project; an item for the project it names, where the
    docket knows it; anything else — an item the export does not hold, or one naming
    a project the docket does not carry — for the default project. None where
    there is no default."""
    u = str(u)
    if u.startswith("canon:"):
        return u[len("canon:"):] or None
    if u.startswith("q:"):
        return u.split(":")[1] or None
    pid = pl.owners.get(u)
    return pid if pid in pl.known else pl.default


def worked(recd, slot, closer, pl):
    """What a session worked, as the closing bell recorded it: the projects, those
    it named and those of the undertakings it picked; the undertakings; and how
    many of those the export could not place (charged to the default project, as
    the page does). A follow-up (then:<id>) rides along and charges nothing."""
    f = (recd.get("focus") or {}).get(slot) or {}
    ps, us = list(f.get("projects") or []), list(f.get("undertakings") or [])
    if not ps and not us and closer:
        b = bells_of(recd).get(closer) or {}
        if b.get("closes") in (None, slot):
            ps, us = list(b.get("projects") or []), list(b.get("undertakings") or [])
    us = [u for u in us if not str(u).startswith("then:")]
    out, unplaced = set(ps), 0
    for u in us:
        if not str(u).startswith(("q:", "canon:")) and pl.owners.get(u) not in pl.known:
            unplaced += 1
        p = project_of(u, pl)
        if p:
            out.add(p)
    return out, set(us), unplaced


def spent(day, recd, docket):
    """The slots the day's meetings took, each the meeting's and no session; one
    marked cancelled on the page took none."""
    return {slot for mid, _, slot in day.meetings(docket, recd) if slot and not (recd.get("cancelled") or {}).get(mid)}


def sessions(day, recd, docket, pl):
    """The day's sessions: (slot, closer, projects, undertakings, unplaced) for each
    focus slot expected that no meeting took, and each one a whole day left
    unexpected on which a bell still recorded work (the page charges it)."""
    taken = spent(day, recd, docket)
    expected = {s for s, _ in day.slots()}
    for slot, closer in day.slots(every=True):
        if slot in taken:
            continue
        ps, us, n = worked(recd, slot, closer, pl)
        if slot in expected or ps:
            yield slot, closer, ps, us, n


def line_wanted(u, pl):
    """Whether the page asks for a next step on a pick (bellLine): never a follow-up
    (then:), a frontier question (q:, or an older canon:) or a dictation."""
    u = str(u)
    return not u.startswith(("then:", "q:", "canon:")) and u not in pl.dictations


# ---- the reading -------------------------------------------------------------

class Reading:
    """One report's reading of the record: the Rule each week is read against, each
    date's Day built once, and each stretch counted once however many sections ask."""

    def __init__(self, r, rec, as_of=None, sunday=None):
        self.r, self.rec = r, rec
        as_of = as_of or rule.today(r.anchors)
        if not YMD.fullmatch(str(as_of)):
            raise ValueError(f"--as-of is a date YYYY-MM-DD, not {as_of!r}")
        self.as_of = as_of
        self.now = week_from(sunday) if sunday else week_before(as_of)
        self.docs = getattr(r, "docs", None)
        self.record = days_of(rec)
        self.pl = places(rec, r.docket)
        self.blockers = [x for (c, i), x in rec.items() if c == "todo" and isinstance(x, dict) and x.get("blocks")]
        self.snaps = snapshots_of(rec, as_of)
        self.pages = {i: d for (c, i), d in (self.docs or {}).items() if c == "projects" and isinstance(d, dict)}
        self._rules, self._kinds, self._days, self._memo, self.read_by = {}, {}, {}, {}, {}

    # the Rule of a week
    def rule_of(self, d):
        """The Rule a date's week is read against, with the events it classified:
        the export for the week under review and after; for a week before it, the
        dated snapshot the sitting after it took (the earliest in the seven days
        after its Saturday), where that holds a whole Rule."""
        sun = sunday_of(d)
        if sun not in self._rules:
            sat = iso(rule.day_of(sun) + timedelta(days=6))
            ns, label = self.r, "the export"
            if sat < self.now[1]:
                nxt = iso(rule.day_of(sat) + timedelta(days=7))
                snap = next(((i, s) for i, s in self.snaps if sat < i <= nxt), None)
                if snap:
                    current = (self.docs or {}).get(("rule", "office"))
                    try:
                        ns = ruledir.assemble(gate.restored(snap[1], current))
                        label = f"snapshots/{snap[0]}"
                    except (ruledir.RuleDirError, KeyError, TypeError, AttributeError):
                        ns, label = self.r, f"the export (snapshots/{snap[0]} holds no whole Rule)"
            self._rules[sun] = ns
            self.read_by[sun] = label
        return self._rules[sun]

    def day(self, d):
        """The date's Day, built once, its events classified once per Rule."""
        if d not in self._days:
            ns = self.rule_of(d)
            self._days[d] = Day(ns.anchors, d, self.as_of, self._kinds.setdefault(id(ns), {}))
        return self._days[d]

    def present(self, dates):
        """The dates with a record, each with its Day; and the dates the store
        lacks, which are gaps."""
        out, gaps = [], []
        for d in dates:
            recd = self.record.get(d)
            if recd is None:
                gaps.append(d)
            else:
                out.append((d, recd, self.day(d)))
        return out, gaps

    def once(self, name, dates, f):
        k = (name, dates[0], dates[-1])
        if k not in self._memo:
            self._memo[k] = f(self, dates)
        return self._memo[k]

    def plan(self, dates):
        return self.once("plan", dates, plan)

    def week(self, dates):
        return self.once("week", dates, week)

    def record_counts(self, dates):
        return self.once("record", dates, record_counts)

    def week_bells(self, dates):
        return self.once("bells", dates, week_bells)

    def guarded(self, dates):
        return self.once("items", dates, guarded)


# ---- the counts --------------------------------------------------------------

def plan(rd, dates):
    """By day: the plans taken on the page, and whether each held, was overridden,
    was not worked, or went unanswered."""
    keys = ("taken", "held", "overridden", "unworked", "unanswered")
    days, totals = {}, dict.fromkeys(keys, 0)
    present, gaps = rd.present(dates)
    for d, recd, day in present:
        row = dict.fromkeys(keys, 0)
        bells = bells_of(recd)
        for slot, closer, ps, us, _ in sessions(day, recd, rd.rule_of(d).docket, rd.pl):
            planned = ((recd.get("focus") or {}).get(slot) or {}).get("planned")
            if not planned:
                continue
            row["taken"] += 1
            if planned in ps or planned in us:
                row["held"] += 1
            elif ps:
                row["overridden"] += 1
            elif closer in bells:
                row["unworked"] += 1
            else:
                row["unanswered"] += 1
        days[d] = row
        for k in keys:
            totals[k] += row[k]
    return {"from": dates[0], "to": dates[-1], "days": days, "totals": totals, "gaps": gaps}


def week(rd, dates):
    """By week: each project's sessions and meetings against its allocation, and the
    slots worked. A slot a meeting took is the meeting's and no session; one the
    bell closed with nothing picked was not worked; one ticked by hand with no bell
    answered was worked, and names no project. The meetings are every day's of the
    week, recorded or not."""
    docket = rd.rule_of(dates[0]).docket
    a = rd.rule_of(dates[0]).anchors
    projects = {}
    for p in docket["projects"]:
        n, edited = allocation_of(p, rd.pages.get(p["id"]), dates[0], a)
        projects[p["id"]] = {"sessions": 0.0, "meetings": 0, "allocation": n, "active": p.get("active", True)}
        if edited:
            projects[p["id"]]["edited"] = True

    def row(pid):
        return projects.setdefault(pid, {"sessions": 0.0, "meetings": 0, "allocation": None, "active": False,
                                         "unknown": True})

    cancelled = []
    for d in dates:
        recd = rd.record.get(d) or {}
        for mid, p, _ in rd.day(d).meetings(rd.rule_of(d).docket, recd):
            if (recd.get("cancelled") or {}).get(mid):
                cancelled.append(f"{mid} {d}")
            else:
                row(p or "?")["meetings"] += 1
    slots_worked = unnamed = unplaced = 0
    present, gaps = rd.present(dates)
    for d, recd, day in present:
        bells, ticks = bells_of(recd), recd.get("items") or {}
        for slot, closer, ps, _, n in sessions(day, recd, rd.rule_of(d).docket, rd.pl):
            unplaced += n
            if ps:
                slots_worked += 1
                for p in ps:
                    row(p)["sessions"] += 1 / len(ps)
            elif ticks.get(slot) and closer not in bells:
                slots_worked += 1
                unnamed += 1
    for v in projects.values():
        v["sessions"] = round(v["sessions"], 2)
        v["used"] = round(v["sessions"] + v["meetings"], 2)
    return {"from": dates[0], "to": dates[-1], "projects": projects, "slots_worked": slots_worked,
            "unnamed": unnamed, "unplaced": unplaced, "supply": docket["policy"].get("realistic_per_week"),
            "cancelled": cancelled, "gaps": gaps}


def record_counts(rd, dates):
    """The week's record as the sitting reads it: anchors run, each floor item
    against its floor, drinks against the ration, resume lines written and kept,
    bedtime, whole days and the meetings that did not happen."""
    r = rd.rule_of(dates[-1])
    a = r.anchors
    anchors = {k: {"answered": 0, "expected": 0} for k in a["anchors"]}
    floors = {it["id"]: {"ticked": 0, "floor": (it.get("when") or {}).get("floor_per_week")}
              for an in a["anchors"].values() for it in an["items"] if (it.get("when") or {}).get("floor_per_week")}
    drink = r.ledger.get("drink") or {}
    drinks = {"drunk": 0, "days": 0, "days_over": 0, "ration": drink.get("ration_per_week"),
              "most_per_day": drink.get("max_per_day")}
    resume = {"with_line": 0, "written": 0, "kept": 0, "closed_with_pick": 0}
    starts = rule.day_starts(a)
    anchor_gaps, wholes, cancelled, bed = [], [], [], []
    present, gaps = rd.present(dates)
    for d, recd, day in present:
        answered, missed, later = read_bells(day, recd)
        for key in answered:
            anchors.setdefault(key, {"answered": 0, "expected": 0})
            anchors[key]["answered"] += 1
            anchors[key]["expected"] += 1
        for key in missed:
            anchors.setdefault(key, {"answered": 0, "expected": 0})
            anchors[key]["expected"] += 1
        anchor_gaps.extend(f"{d} {key}" for key in later)
        ticks = recd.get("items") or {}
        for i in floors:
            if ticks.get(i):
                floors[i]["ticked"] += 1
        n = drinks_of(recd)
        drinks["days"] += 1
        if n is not None:
            drinks["drunk"] += n
            if drinks["most_per_day"] is not None and n > drinks["most_per_day"]:
                drinks["days_over"] += 1
        focus = {slot for slot, _ in day.slots(every=True)}
        for key, b in bells_of(recd).items():
            if key not in day.a["anchors"]:
                continue
            closes = b.get("closes") or day.breaks(key)
            picks = list(b.get("projects") or []) + [u for u in b.get("undertakings") or [] if line_wanted(u, rd.pl)]
            if closes in focus and picks:
                resume["closed_with_pick"] += 1
                written, kept = bool(b.get("threads")), bool(b.get("kept"))
                resume["written"] += written
                resume["kept"] += kept
                resume["with_line"] += written or kept
        t = (recd.get("times") or {}).get("sleep")
        at = rule.minutes_of(t, starts) if t else None
        if at is not None:
            bed.append((at, t))
        wholes.extend(f"{c['id']} {d}" for c in day.wholes)
        cancelled.extend(f"{c['id']} {d}" for c in day.hours if (recd.get("cancelled") or {}).get(c["id"]))
    bedtime = {"days": len(bed), "earliest": min(bed)[1] if bed else None, "latest": max(bed)[1] if bed else None}
    return {"from": dates[0], "to": dates[-1], "anchors": anchors, "anchor_gaps": anchor_gaps, "floors": floors,
            "drinks": drinks, "resume_lines": resume, "bedtime": bedtime, "whole_days": wholes,
            "cancelled": cancelled, "gaps": gaps}


def week_bells(rd, dates):
    """One week for the gate: the days with every expected bell answered, read as
    the Week view reads them. A day a fixture takes whole is never one of them,
    whatever bells it keeps (the Week view's "not expected"), and a day a bell is a
    gap on is named; neither is a miss."""
    present, gaps = rd.present(dates)
    all_answered, bell_gaps, whole = 0, [], []
    for d, recd, day in present:
        answered, missed, later = read_bells(day, recd)
        if day.wholes or not (answered or missed or later):
            whole.append(d)
        elif later:
            bell_gaps.append(d)
        elif not missed:
            all_answered += 1
    return {"from": dates[0], "to": dates[-1], "all_answered": all_answered,
            "days": len(present) - len(whole) - len(bell_gaps), "whole_days": whole, "bell_gaps": bell_gaps,
            "gaps": gaps}


def meets(w, need):
    """Whether a week meets the gate's days with every bell answered: met, not met,
    or None where what the store lacks (a gap, a whole day) could decide it."""
    if need is None:
        return None
    if w["all_answered"] >= need:
        return True
    if w["all_answered"] + len(w["gaps"]) + len(w["bell_gaps"]) + len(w["whole_days"]) < need:
        return False
    return None


def verdict(votes):
    """One reading over several: not met if any is, else the sitting's if any is, else met."""
    if any(v is False for v in votes):
        return False
    if any(v is None for v in votes):
        return None
    return True


def by_collection(docs):
    out = {}
    for (c, i), v in docs.items():
        out.setdefault(c, {})[i] = v
    return out


def stable(snaps, docs, as_of):
    """The Rule as the weekly snapshots hold it, newest last, each read as the gate
    restores one (gate.restored: a snapshot with no docs is refused, and an Office
    item it gives no guard takes the one rule/office gives it now): its `rule`
    documents (what a review proposes changes to) apart from the rest (the
    calendar's events, the week's allocations, the backlog's counts), which change
    without one. Where no snapshot is dated as_of, the export's own Rule is the
    newest point: at a sitting the counts run before the snapshot is written. Where
    the newest snapshot is less than a week old, the export is not a week of its own
    and is no point."""
    def parts(rule_docs):
        cs = by_collection(rule_docs)
        return cs.pop("rule", {}), cs

    current = (docs or {}).get(("rule", "office"))
    points = [(i, *parts(gate.restored(snap, current))) for i, snap in snaps]
    # the export stands for the sitting's own snapshot only where a week has passed
    # since the newest one: a day after Sunday's snapshot it is no week of its own
    newest = snaps[-1][0] if snaps else None
    if docs is not None and (newest is None or rule.day_of(newest) + timedelta(days=7) <= rule.day_of(as_of)):
        points.append((f"{as_of} (the export)", *parts(ruledir.raw(docs))))
    unchanged, elsewhere = 0, []
    for k in range(len(points) - 1, 0, -1):
        if points[k][1] != points[k - 1][1]:
            break
        unchanged += 1
    if len(points) > 1:
        a, b = points[-1][2], points[-2][2]
        elsewhere = sorted(c for c in set(a) | set(b) if a.get(c) != b.get(c))
    return [i for i, _, _ in points], unchanged, elsewhere


def month(rd):
    """By month: the backlog gate's five criteria over the weeks ending with the
    week under review, each as the facts the sitting reads, held to the numbers the
    Rule's own words for the criterion give. Each week is the one the other sections
    counted, read once."""
    backlog = rd.r.backlog
    says = ((backlog.get("gate") or {}).get("criteria") or {})
    unread = "rule/gate gives no number the tool can read; read at the sitting"
    need_days = said(says.get("anchors_run"), r">=\s*(\d+)\s*of\s*7")
    need_weeks = said(says.get("anchors_run"), r"(\w+)\s+consecutive\s+weeks")
    end = rd.now[1]
    weeks_read, first = window(backlog, end)
    days = span(first, end)
    weeks, rc = [], {"with_line": 0, "written": 0, "kept": 0, "closed_with_pick": 0}
    for n in range(weeks_read):
        dates = days[7 * n:7 * n + 7]
        w = dict(rd.week_bells(dates))
        w["slots_worked"] = rd.week(dates)["slots_worked"]
        w["met"] = meets(w, need_days)
        weeks.append(w)
        for k, v in rd.record_counts(dates)["resume_lines"].items():
            rc[k] += v
    last = weeks[-(need_weeks or WEEKS):]
    anchors_run = {"says": says.get("anchors_run"), "weeks": weeks, "met": verdict([w["met"] for w in last]),
                   "undecided": [w["from"] for w in last if w["met"] is None],
                   "note": None if need_days is not None and need_weeks is not None else unread}
    need_rate = said(says.get("resume_lines"), r">=\s*(\d+)\s*%")
    rate = rc["with_line"] / rc["closed_with_pick"] if rc["closed_with_pick"] else None
    resume_lines = {"says": says.get("resume_lines"), **rc, "rate": None if rate is None else round(rate, 2),
                    "met": None if rate is None or need_rate is None else rate >= need_rate / 100,
                    "note": None if need_rate is not None else unread}
    need_still = said(says.get("rule_stable"), r"(\w+)\s+consecutive\s+weeks")
    ids, unchanged, elsewhere = stable(rd.snaps, rd.docs, rd.as_of)
    enough = need_still is not None and len(ids) > need_still
    rule_stable = {"says": says.get("rule_stable"), "snapshots": ids, "weeks_unchanged": unchanged,
                   "changed_elsewhere": elsewhere, "met": unchanged >= need_still if enough else None,
                   "note": unread if need_still is None
                   else None if enough else f"fewer than {need_still + 1} weekly snapshots in the export"}
    before = [w for w in weeks[:-1] if w["days"]]
    this = weeks[-1]
    not_in_desolation = {
        "says": says.get("not_in_desolation"), "met": None,
        "read": "at the sitting: no promotion on a good week's high, no deletion on a bad week's low",
        "this_week": {"all_answered": this["all_answered"], "slots_worked": this["slots_worked"]},
        "weeks_before": {"all_answered_mean": round(sum(w["all_answered"] for w in before) / len(before), 2) if before else None,
                         "slots_worked_mean": round(sum(w["slots_worked"] for w in before) / len(before), 2) if before else None,
                         "weeks": len(before), "omitted": [w["from"] for w in weeks[:-1] if not w["days"]]}}
    slot_empty = {"says": says.get("slot_empty"), "met": None,
                  "read": "at the sitting: whether the named slot is free",
                  "items": [{"id": x["id"], "slot": x.get("slot"), "displaces": x.get("displaces"),
                             "named": bool(x.get("slot") and x.get("displaces"))}
                            for x in backlog.get("items") or []]}
    return {"from": days[0], "to": end,
            "criteria": {"anchors_run": anchors_run, "not_in_desolation": not_in_desolation,
                         "resume_lines": resume_lines, "rule_stable": rule_stable, "slot_empty": slot_empty}}


def year(docket):
    """By year: each project's frontier against the end its notebook's root states,
    as the sync carries both to the project's document."""
    out = {}
    for p in docket["projects"]:
        h = p.get("hypomnemata")
        if not isinstance(h, dict) or not p.get("active", True):
            continue
        fr = [q for q in h.get("frontier") or [] if isinstance(q, dict)]
        pressure = sum(q.get("pressure", 0) for q in fr if isinstance(q.get("pressure", 0), (int, float)))
        out[p["id"]] = {"end": h.get("end"), "frontier": len(fr), "pressure": pressure,
                        "questions": [q.get("id") for q in fr]}
    return out


def floor_can_wait(rd, key, it, d):
    """Whether a floor item (when.floor_per_week) could wait on a date, as the page's
    floorCanWait reads it when the day begins: the floor met by the week's days
    before it, or still in reach on the days left in the week that offer it. The
    day's own tick is not counted: it is what the day did, not what it owed."""
    floor = it["when"]["floor_per_week"]
    sun, sat = sunday_of(d), iso(rule.day_of(sunday_of(d)) + timedelta(days=6))
    n = sum(1 for x in span(sun, d)[:-1] if ((rd.record.get(x) or {}).get("items") or {}).get(it["id"]))
    if n >= floor:
        return True
    later = span(iso(rule.day_of(d) + timedelta(days=1)), sat) if d < sat else []
    return sum(1 for x in later if rd.day(x).expected(key, it)) >= floor - n


def guarded(rd, dates):
    """Per item: how often it held on the days its guard reached it, and on the days
    it did not. See the top of the file for what a guard does not reach, and what is
    left out."""
    out = {}
    present, gaps = rd.present(dates)
    for d, recd, day in present:
        answered, missed, later = read_bells(day, recd)
        ticks, na = recd.get("items") or {}, recd.get("na") or {}
        blocked = items.blocked_on(rd.blockers, d, rd.as_of)
        for key, it in day.items():
            w = it.get("when") or {}
            if not rule.office(it) or "ledger" in w or na.get(it["id"]) or key in later:
                continue
            if "floor_per_week" in w and floor_can_wait(rd, key, it, d):
                continue
            # a part an open TODO blocks is not owed: the page ticks and counts the
            # open parts only (openLeaves, groupState)
            kids = it.get("children") or []
            open_kids = [k for k in day.parts(key, it) if k is not it and k["id"] not in blocked]
            if it["id"] in blocked or (kids and not open_kids):
                continue
            held = bool(ticks.get(it["id"])) or (bool(open_kids) and all(ticks.get(k["id"]) for k in open_kids))
            g = it.get("guard")
            unreached = (bool(day.wholes) or g == "none"
                         or g == "bell" and (key in day.moved or key in missed))
            row = out.setdefault(it["id"], {"guard": g or "not stated", "blocks": [],
                                            "reached": {"held": 0, "days": 0}, "unreached": {"held": 0, "days": 0}})
            if key not in row["blocks"]:
                row["blocks"].append(key)
            side = row["unreached" if unreached else "reached"]
            side["days"] += 1
            side["held"] += int(held)
    return {"from": dates[0], "to": dates[-1], "items": out, "gaps": gaps}


def report(r, rec, as_of=None, sunday=None):
    """Every count, for the period under review and the one before it."""
    rd = Reading(r, rec, as_of, sunday)
    now = rd.now
    before = shifted(now, -7)
    both = lambda f: {"now": f(span(*now)), "before": f(span(*before))}  # noqa: E731
    out = {
        "as_of": rd.as_of, "under_review": {"from": now[0], "to": now[1]},
        "day": both(rd.plan),
        "week": both(rd.week),
        "record": both(rd.record_counts),
        "month": month(rd),
        "year": year(r.docket),
        "items": both(rd.guarded),
    }
    out["needs_from"] = out["month"]["from"]
    out["read_by"] = dict(sorted(rd.read_by.items()))
    return out


# ---- printing ----------------------------------------------------------------

def _n(x):
    return f"{x:g}" if isinstance(x, float) else str(x)


def _gaps(gaps, what="gaps"):
    return f" · {what}: " + ", ".join(gaps) if gaps else ""


def _met(v):
    return {True: "met", False: "not met", None: "read at the sitting"}[v]


def _note(c):
    return f" ({c['note']})" if c.get("note") else ""


def _week_gaps(w):
    """What a gate week lacks, named: the days the store has no record of, the
    bells recorded later, the whole days."""
    if len(w["gaps"]) == 7:
        return f" · week of {w['from']}: no record"
    named = _gaps(w["gaps"]) + _gaps(w["bell_gaps"], "bells recorded later") + _gaps(w["whole_days"], "whole days")
    return f" · week of {w['from']}" + named if named else ""


def text(out):
    """The report as lines, one stretch each, the period before it beneath."""
    u = out["under_review"]
    lines = [f"counts as of {out['as_of']} · week under review {u['from']} to {u['to']} · read from {out['needs_from']}"]
    by = [f"week of {w} by {src}" for w, src in out["read_by"].items() if src != "the export"]
    if by:
        lines.append("rule · " + " · ".join(by) + " · every other week by the export")
    for label in ("now", "before"):
        p = out["day"][label]
        t = p["totals"]
        lines.append(f"day {label} ({p['from']} to {p['to']}) · plans taken {t['taken']} · held {t['held']}"
                     f" · overridden {t['overridden']} · not worked {t['unworked']} · unanswered {t['unanswered']}"
                     + _gaps(p["gaps"]))
    for label in ("now", "before"):
        w = out["week"][label]
        parts = [f"{pid}{'' if v['active'] else ' (inactive)'}{' (no such project)' if v.get('unknown') else ''}"
                 f" {_n(v['sessions'])} sessions + {v['meetings']} meetings = {_n(v['used'])} of {v['allocation']}"
                 + (" (edited for the week)" if v.get("edited") else "")
                 for pid, v in w["projects"].items() if v["active"] or v["used"]]
        lines.append(f"week {label} ({w['from']} to {w['to']}) · " + " · ".join(parts)
                     + f" · slots worked {w['slots_worked']} of {w['supply']}"
                     + (f" · {w['unnamed']} with no project named" if w["unnamed"] else "")
                     + (f" · {w['unplaced']} undertaking(s) the export does not place" if w["unplaced"] else "")
                     + _gaps(w["cancelled"], "did not happen") + _gaps(w["gaps"]))
    for label in ("now", "before"):
        c = out["record"][label]
        an = " ".join(f"{k} {v['answered']}/{v['expected']}" for k, v in c["anchors"].items())
        fl = " · ".join(f"{i} {v['ticked']} of {v['floor']}" for i, v in c["floors"].items()) or "no floor item"
        dk, rl, bt = c["drinks"], c["resume_lines"], c["bedtime"]
        lines.append(f"record {label} ({c['from']} to {c['to']}) · anchors {an}{_gaps(c['anchor_gaps'], 'bells recorded later')}"
                     f" · {fl}"
                     f" · drinks {_n(dk['drunk'])} of {dk['ration']} over {dk['days']} days, {dk['days_over']} over {dk['most_per_day']}"
                     f" · resume lines {rl['with_line']} of {rl['closed_with_pick']} ({rl['written']} written, {rl['kept']} kept)"
                     f" · bedtime {bt['earliest']} to {bt['latest']} over {bt['days']} days"
                     + _gaps(c["whole_days"], "whole days") + _gaps(c["cancelled"], "did not happen") + _gaps(c["gaps"]))
    m = out["month"]
    cr = m["criteria"]
    ar, rl, rs, nd = cr["anchors_run"], cr["resume_lines"], cr["rule_stable"], cr["not_in_desolation"]
    wk = " ".join(f"{w['all_answered']}/{w['days']}" for w in ar["weeks"])
    lines.append(f"month ({m['from']} to {m['to']}) · anchors_run: days with every bell answered, by week, {wk}: "
                 f"{_met(ar['met'])}{_note(ar)}" + _gaps(ar["undecided"], "weeks a gap could decide")
                 + "".join(_week_gaps(w) for w in ar["weeks"])
                 + f" · resume_lines: {rl['with_line']} of {rl['closed_with_pick']} ({rl['rate']}): {_met(rl['met'])}{_note(rl)}"
                 + f" · rule_stable: {rs['weeks_unchanged']} weeks unchanged over {len(rs['snapshots'])} snapshots:"
                 f" {_met(rs['met'])}{_note(rs)}" + _gaps(rs["changed_elsewhere"], "changed beside the rule")
                 + f" · not_in_desolation: this week {nd['this_week']['all_answered']} days,"
                 f" {nd['this_week']['slots_worked']} slots; the {nd['weeks_before']['weeks']} weeks before"
                 f" {nd['weeks_before']['all_answered_mean']} days,"
                 f" {nd['weeks_before']['slots_worked_mean']} slots: read at the sitting"
                 + _gaps(nd["weeks_before"]["omitted"], "weeks with no record")
                 + " · slot_empty: " + ", ".join(f"{x['id']} {'named' if x['named'] else 'unnamed'}"
                                                 for x in cr["slot_empty"]["items"]) + ": read at the sitting")
    for pid, v in out["year"].items():
        lines.append(f"year · {pid} · frontier {v['frontier']} question(s), pressure {_n(v['pressure'])} · end "
                     + (f"stated ({len(str(v['end']).split())} words)" if v["end"] else "not stated"))
    for label in ("now", "before"):
        it = out["items"][label]
        parts = [f"{i} ({v['guard']}) reached {v['reached']['held']}/{v['reached']['days']}"
                 f" unreached {v['unreached']['held']}/{v['unreached']['days']}" for i, v in it["items"].items()]
        lines.append(f"items {label} ({it['from']} to {it['to']}) · " + " · ".join(parts) + _gaps(it["gaps"]))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir", nargs="?", default=os.environ.get(ruledir.ENV))
    ap.add_argument("--record")
    ap.add_argument("--as-of")
    ap.add_argument("--week")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--window", action="store_true",
                    help="print the first date the counts read, from the Rule alone, and stop")
    args = ap.parse_args(argv)
    if not args.dir:
        print(f"needs the Rule: export the store with ArtifactData and set ${ruledir.ENV} to the directory",
              file=sys.stderr)
        return 2
    try:
        r, rec = load(args.dir, args.record)
        if args.window:
            as_of = args.as_of or rule.today(r.anchors)
            end = (week_from(args.week) if args.week else week_before(as_of))[1]
            print(window(r.backlog, end)[1])
            return 0
        out = report(r, rec, args.as_of, args.week)
    except (ruledir.RuleDirError, rule.RuleError, items.Refused, ValueError) as e:
        print("ERROR ", e, file=sys.stderr)
        return 1
    except (KeyError, TypeError, AttributeError) as e:
        print(f"ERROR  the export will not read as the Rule and its record: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("\n".join(text(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
