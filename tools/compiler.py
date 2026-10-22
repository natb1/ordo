#!/usr/bin/env python3
"""Compile the Rule into the constants the Cadence page reads, and refuse what it
cannot run.

The Rule lives in the page's store as raw documents (tools/ruledir.py). The page
reads one compiled document, rule/compiled, with a field for each constant: the
blocks and their items, the calendar's events (each a fixture or a meeting, as
tools/rule.py computes it), the projects and their frontiers, the backlog, and the
Rule's numbers and steps the page quotes. tools/gate.py runs this on every write.

    ORDO_RULE=<dir> python3 tools/compiler.py    # the refusals, or ok
"""
import re
import sys
from urllib.parse import quote_plus

import items
import rule
import ruledir

GLOSS = "rule/gloss"
LEDGER = "rule/ledger"

DOW = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
       "friday": "fri", "saturday": "sat", "sunday": "sun"}
# Google's code for a travel mode, in a directions link built from a fixture's addresses.
MODE = {"driving": 0, "bicycling": 1, "walking": 2, "transit": 3}
# A time of day as the page reads it: text, never a number. Given a number, the
# page's hm() dies on it with no Today at all.
CLOCK = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
# A plain date as the page does arithmetic on it (ymd()).
YMD = items.YMD   # the date rule is held once, in the item contract
# A project's repo: owner/name on GitHub, or an absolute path on a named device
# (desk:/srv/git/allotment), which the page names and never links. A URL is neither,
# nor a host or a path step: an owner has no dot, and a name is not all dots.
GITHUB = re.compile(r"[\w-]+/(?!\.+$)[\w.-]+")
LOCAL = re.compile(r"[A-Za-z0-9][\w-]*:/(?!/)\S+")

errors = []


def glossed(section, ids, allowed, entries):
    """One section of the gloss, {id: {field: value}}, held to the Rule: an entry for
    an id that is not there is drift, and a field the page does not read would be
    silently ignored, so both fail."""
    out = {}
    for i, g in (entries or {}).items():
        if i not in ids:
            errors.append(f"{GLOSS}: {section} has {i}, which is not in the Rule")
            continue
        for f in g or {}:
            if f not in allowed:
                errors.append(f"{GLOSS}: {section} {i} has {f}; the page reads only "
                              + ", ".join(sorted(allowed)))
        out[i] = g or {}
    return out


def clock(v, where):
    """A time the page or the checker reads, held to a quoted "HH:MM"."""
    if not (isinstance(v, str) and CLOCK.fullmatch(v)):
        errors.append(f"{where}: {v!r} is not a quoted \"HH:MM\"")
    return v


def days(v, where):
    """A weekday rule as the page runs it (onDay): a list of weekday names, or unset.
    A map passes rule.py's `in`, and on the page it has no indexOf: no Today at all."""
    if v is not None and not (isinstance(v, list) and all(x in rule.DAYS for x in v)):
        errors.append(f"{where}: {v!r} is not a list of " + ", ".join(rule.DAYS))
    return v


# ---- the anchors -------------------------------------------------------------

# The conditions an item's `when:` may carry, each of which the page runs. One it
# does not know would be dropped without a word — which is how gym and groceries came
# to be offered every day — so any other key fails.
WHEN = {"weekday", "not_winter", "ledger", "floor_per_week", "commitment"}
# What holds an Office item in place: the bell that opens its block, a Clock alarm
# of its own, a budget seen before the act, a plan made at a review, or nothing
# (hypomnemata › unprompted, the guard on each item). Every Office item names one,
# so the guarded region is computed from the Rule and never read off the runbook;
# the counts (tools/counts.py) read an item's days by whether its guard reached them.
GUARDS = ("bell", "alarm", "budget", "plan", "none")


def item(it, gloss, cs):
    """An item as the page runs it: what to do, when it applies, and what kind of row
    it gets. Minutes, ordering constraints and the notes stay in the Rule — the page
    does not read them; check_capacity.py does.

    A `ledger:` condition ("you noticed you are out") is one the page cannot see, so
    the item is optional there: not needed is the normal case, one tap, no reason.
    A `floor_per_week:` item is counted against its floor. `when: {commitment: X}`
    holds an item to the days fixture X is on, and `unless: {commitment: X}` keeps
    it off them, so an item a fixture causes goes when the fixture's `until` does.
    An item that IS a fixture with no travel carries that fixture's hours, the one
    stretch the toolbar names it for."""
    w = it.get("when") or {}
    u = it.get("unless") or {}
    for k in w:
        if k not in WHEN:
            errors.append(f"item {it['id']}: when has {k}, which the page does not run; "
                          "it reads " + ", ".join(sorted(WHEN)))
    for k in u:
        if k != "commitment":
            errors.append(f"item {it['id']}: unless has {k}; the page reads only commitment")
    out = {"id": it["id"], "do": it["do"], "sub": gloss.get("sub")}
    # An Office item names its guard; `none` is a guard named, an item that names
    # none at all is refused. A work item is the docket's and a fixture item the
    # calendar's, so neither names one. The page does not read it.
    if rule.office(it) and it.get("guard") not in GUARDS:
        errors.append(f"item {it['id']}: names no guard; each Office item names one of "
                      + ", ".join(GUARDS) + " (hypomnemata › unprompted)")
    if days(w.get("weekday"), f"item {it['id']} when.weekday"):
        out["when"] = w["weekday"]
    if days(it.get("skip_weekday"), f"item {it['id']} skip_weekday"):
        out["skipDay"] = it["skip_weekday"]
    if w.get("not_winter"):
        out["notWinter"] = True
    if w.get("ledger"):
        out["optional"] = True
        if it.get("nullable"):
            errors.append(f"item {it['id']}: optional (a ledger condition) and nullable both; "
                          "it is one or the other")
    if "floor_per_week" in w:
        if type(w["floor_per_week"]) is not int or w["floor_per_week"] < 1:
            errors.append(f"item {it['id']}: floor_per_week is a whole number of days, at least 1, "
                          f"not {w['floor_per_week']!r}")
        else:
            out["floor"] = w["floor_per_week"]
    for field, c in (("during", w.get("commitment")), ("unless", u.get("commitment"))):
        if not c:
            continue
        if c not in cs:
            errors.append(f"item {it['id']}: names commitment {c}, which is not a fixture")
        elif rule.whole_day(cs[c]):
            errors.append(f"item {it['id']}: names commitment {c}, which takes whole days; "
                          "what those keep is its keep:, not an item")
        out[field] = c
    fx = it.get("commitment")
    if fx:
        if fx not in cs:
            errors.append(f"item {it['id']}: is commitment {fx}, which is not a fixture")
        elif not cs[fx].get("derived_leave_by"):
            if cs[fx].get("start") and cs[fx].get("end"):
                out["window"] = [cs[fx]["start"], cs[fx]["end"]]
            else:
                errors.append(f"item {it['id']}: is commitment {fx}, which has no start and end "
                              "to give the item its hours")
    if it.get("nullable"):
        out["nullable"] = True
    if it.get("kind") == "work":
        out["focus"] = True
    if it.get("examen"):
        out["examen"] = True
    if it.get("value"):
        # The page records one value, and records it as the weight: a second value
        # item would write over the day's weight.
        if it["id"] != "weight":
            errors.append(f"item {it['id']} has value:, but the page records a value only as the weigh-in")
        out["value"] = it["value"]["unit"]
        out["step"] = it["value"].get("step")
    if it.get("children"):
        out["children"] = [{"id": k["id"], "do": k["do"]} for k in it["children"]]
    return out


def order(name, v, blocks, cs):
    """A declared variation may order a weekday's items differently — Tuesday's block
    ends in a departure, so the trash goes out before it (rule/office › variations).
    The page keeps one list per block, so the order rides along keyed by weekday and
    is applied on that day. The exit rite is not an item — the page records it as the
    bell's answer — so an exit_* entry is passed over. A variation a fixture causes
    names it (`commitment:`), and the order holds only on the days that fixture is
    on: when its `until` passes, the weekday goes back to the plain order."""
    ids = [i for i in v.get("item_order") or [] if not i.startswith("exit_")]
    if not ids:
        return
    dow = DOW.get(name)
    if not dow:
        errors.append(f"variation {name} orders items but is not named for a weekday")
        return
    known = {it["id"] for b in blocks for it in b["items"]}
    for i in ids:
        if i not in known:
            errors.append(f"variation {name} orders {i}, which no block has")
    homes = [b for b in blocks if any(it["id"] in ids for it in b["items"])]
    if len(homes) != 1:
        errors.append(f"variation {name} orders items of {len(homes)} blocks; the page orders one")
        return
    homes[0].setdefault("order", {})[dow] = ids
    c = v.get("commitment")
    if c:
        if c not in cs or rule.whole_day(cs[c]):
            errors.append(f"variation {name} names commitment {c}, which the page does not carry with hours")
        homes[0].setdefault("orderDuring", {})[dow] = c


def blocks(a, gloss):
    """The blocks in the Rule's order, each with its items in the Rule's order."""
    g = gloss.get("anchors") or {}
    cs = {c["id"]: c for c in a.get("commitments") or []}
    for key in g:
        if key not in a["anchors"]:
            errors.append(f"{GLOSS}: anchors has {key}, which is not a block")
    out = []
    for key, anchor in a["anchors"].items():
        items = anchor["items"]
        gi = glossed(f"anchors {key}", {it["id"] for it in items}, {"sub"}, g.get(key))
        out.append({"key": key, "name": anchor["name"],
                    "bell": clock(anchor.get("bell"), f"anchors {key} bell"),
                    "breaks": anchor["breaks"],
                    "skipDay": days(anchor.get("skip_weekday"), f"anchors {key} skip_weekday"),
                    "items": [item(it, gi.get(it["id"], {}), cs) for it in items]})
    for name, v in (a.get("variations") or {}).items():
        order(name, v, out, cs)
    return out


def directions(c):
    """The Rule's own link when it has one, else one built the way Google's share
    links are, from the addresses and travel mode the Rule records."""
    if c.get("directions"):
        return c["directions"]
    url = ("https://www.google.com/maps/dir/" + quote_plus(c["from"], safe=",")
           + "/" + quote_plus(c["to"], safe=","))
    if c.get("mode") in MODE:
        url += f"/data=!4m2!4m1!3e{MODE[c['mode']]}"
    return url


def commitment_keys(c):
    """The keys the tools read are the derived ones. A commitment written with the
    bare `leave_by:` or `bell:`, or with travel and no `derived_leave_by:`, would be
    dropped from the page below without a word, and check_capacity would count its
    travel as free time — so it fails instead."""
    for k in ("leave_by", "bell"):
        if k in c:
            errors.append(f"commitment {c['id']} has {k}:; the tools read derived_{k}")
    if c.get("travel_minutes") and not c.get("derived_leave_by"):
        errors.append(f"commitment {c['id']} has travel but no derived_leave_by "
                      "(start - travel_minutes); the page would drop it")
    # An event is on a weekday, once on a date, or over a range of dates: one of the
    # three (tools/rule.py).
    try:
        rule.when(c)
    except rule.RuleError as e:
        errors.append(str(e))
        return False
    # The page compares these with its own dates as text, so each is YYYY-MM-DD and
    # nothing else rule.day_of would also take (20261026, 2026-W44-1).
    for k in ("date", "first", "last"):
        if k in c:
            ymd(c[k], f"commitment {c['id']} {k}")
    # The calendar is the source of truth for every event, fixture and meeting alike:
    # one written here first is a copy of nothing, and the sync cannot carry a change
    # to it. So an event the calendar does not hold is refused, never written.
    if not c.get("calendar_event"):
        errors.append(f"commitment {c['id']} has no calendar_event; create the event on its "
                      "project's calendar first, and copy its id here")
    # The kind is where the event falls, so it is computed and never written.
    if "type" in c:
        errors.append(f"commitment {c['id']} has type:; a meeting or a fixture is decided by where "
                      "the event falls (tools/rule.py), so drop it")
    return True


def whole_days(a, blocks):
    """The fixtures that take whole days (`all_day: true`): a vacation, a sick day. Each
    names what it keeps of the Office (`keep:`), by the ids the Office gives the
    items; everything it does not keep is not expected on the page for those days,
    and a bell whose every item is not expected is not either. It has no hours, so
    no leave-by, no bell and nothing for the capacity check to count."""
    ids = {it["id"] for b in blocks for it in b["items"]}
    out = []
    for c in a.get("commitments") or []:
        if not rule.whole_day(c):
            continue
        where = f"commitment {c['id']}"
        try:
            if rule.when(c) == "weekday":
                errors.append(f"{where} takes whole days and needs date: or first:/last:, not a weekday")
                continue
        except rule.RuleError:
            continue    # commitments() has said so
        for k in ("start", "end", "travel_minutes", "derived_leave_by", "sets_anchor_bell"):
            if k in c:
                errors.append(f"{where} takes whole days and has {k}:; it has no hours")
        keep = c.get("keep")
        if not isinstance(keep, list):
            errors.append(f"{where} takes whole days and must say what it keeps of the Office "
                          "(keep: [item ids], or keep: [] for nothing)")
            continue
        for i in keep:
            if i not in ids:
                errors.append(f"{where} keeps {i}, which is not an item")
        out.append({"id": c["id"], "what": c["what"], "from": rule.first_day(c), "to": rule.last_day(c),
                    "keep": list(keep)})
    return out


def commitments(a, d, gloss):
    """Every calendar event with hours that the page has a use for. A fixture with a
    leave-by is a DEPARTURE, which the footer names with its leave-by and which can
    move a bell; one with no travel the footer names at its hour. A meeting, travel
    or none, takes the work session it falls in and is charged to its project. Which
    of the two an event is, tools/rule.py computes from where it falls. A fixture
    that takes whole days is not here: it has no
    hours (whole_days()).

    A fixture whose place varies week to week (`locations:`) gets no route: the
    calendar holds this week's place, so the page links to the day there instead of
    to one place it may not be."""
    cs = a.get("commitments") or []
    g = glossed("commitments", {c["id"] for c in cs}, {"short"}, gloss.get("commitments"))
    out = []
    for c in cs:
        if not commitment_keys(c) or rule.whole_day(c):
            continue
        try:
            sort, why = rule.kind(a, c)
        except rule.RuleError as e:
            errors.append(str(e))
            continue
        if c.get("must_be") and c["must_be"] != sort:
            errors.append(f"commitment {c['id']} must be a {c['must_be']} and is a {sort}: {why}")
        for f in ("start", "end", "derived_leave_by", "derived_bell", "derived_anchor_bell"):
            if f == "start" or c.get(f) is not None:
                clock(c.get(f), f"commitment {c['id']} {f}")
        start = a["meta"].get("day_starts")
        if (c.get("derived_anchor_bell") is not None and isinstance(start, str)
                and str(c["derived_anchor_bell"]) <= start):
            # a bell past midnight sorts before the day's first and never rings
            errors.append(f"commitment {c['id']} moves a bell to {c['derived_anchor_bell']}, not after "
                          f"meta.day_starts {start}; the page's day would ring it first, and never")
        if c.get("sets_anchor_bell") and c["sets_anchor_bell"] not in a["anchors"]:
            errors.append(f"commitment {c['id']} moves bell {c['sets_anchor_bell']!r}, which is not a block; "
                          "one of " + ", ".join(a["anchors"]))
        meeting = sort == "meeting"
        if c.get("sets_anchor_bell") and not c.get("derived_leave_by"):
            errors.append(f"commitment {c['id']} moves a bell but has no leave-by (derived_leave_by)")
        e = {"id": c["id"], "what": c["what"], "short": g.get(c["id"], {}).get("short"),
             "day": c.get("weekday"), "on": str(c["date"]) if c.get("date") else None,
             "first": rule.first_day(c) if "first" in c else None,
             "last": rule.last_day(c) if "first" in c else None,
             "start": c.get("start"), "end": c.get("end"),
             "until": ymd(c["until"], f"commitment {c['id']} until") if c.get("until") else None,
             "leaveBy": c.get("derived_leave_by")}
        if c.get("sets_anchor_bell"):
            if not c.get("derived_anchor_bell"):
                errors.append(f"commitment {c['id']} moves a bell but not to when (derived_anchor_bell)")
            e["moves"] = {"anchor": c["sets_anchor_bell"], "at": c.get("derived_anchor_bell")}
        if meeting:
            # A meeting is supply consumed: the page counts it against its project.
            e["meeting"] = True
            e["project"] = rule.project(c, d)
            if not e["project"]:
                errors.append(f"commitment {c['id']} is a meeting and names no project, and no project is the default")
            elif e["project"] not in {p["id"] for p in d["projects"] if p.get("active", True)}:
                errors.append(f"commitment {c['id']} is a meeting of {e['project']}, which is not an active project")
        if c.get("locations"):
            if c.get("to"):
                errors.append(f"commitment {c['id']} has locations and a single `to:`; "
                              "the calendar says which, so drop `to:`")
            e["varies"] = True
        # A link only where there is somewhere to go.
        elif c.get("directions") or (c.get("from") and c.get("to")):
            e["directions"] = directions(c)
        out.append(e)
    return out


# ---- the docket --------------------------------------------------------------

def projects(d, active=True):
    """A project is a repo (the docket), and the page calls it by its own name, its
    `what`, or else by the repo's last part. The repo is owner/name on GitHub, which
    the page links, or a path on one of the devices, which it shows and never links:
    a phone cannot open it. It carries its links — the repo, its one calendar if it
    has one, its notebook if it has one. Its next step is not the Rule's: the bell
    records it in the page's store (`thread`, beside `rule` in projects/<id>), so a
    `next_step:` here would seed a copy that only goes stale, and fails. One marked inactive competes for
    nothing, so it is kept apart: the docket shows it, and nothing that ranks or
    counts ever sees it."""
    out = []
    for p in d["projects"]:
        if p.get("active", True) != active:
            continue
        h = p.get("hypomnemata")
        h = h if isinstance(h, dict) else {}   # one that is not a map, frontier() refuses
        r = str(p.get("repo") or "")
        if GITHUB.fullmatch(r):
            link = "https://github.com/" + r
        elif LOCAL.fullmatch(r):
            link = None
        else:
            errors.append(f"project {p['id']} has repo {p.get('repo')!r}; a repo is owner/name on GitHub "
                          "or an absolute path on a named device, device:/path")
            link = None
        if type(p.get("allocation")) is not int or p["allocation"] < 0:
            errors.append(f"project {p['id']} has allocation {p.get('allocation')!r}; it is a whole number of slots")
        what = p.get("what")
        if what is None:
            what = r.rstrip("/").split("/")[-1]
        elif not (isinstance(what, str) and what.strip()):
            errors.append(f"project {p['id']} has what {what!r}; a project's name is text, or left out")
        e = {"id": p["id"], "what": what, "allocation": p.get("allocation"), "repo": link, "checkout": r,
             "calendar": p.get("calendar"), "notebook": h.get("notebook")}
        if p.get("default"):
            e["default"] = True
        if "next_step" in p:
            errors.append(f"project {p['id']} has next_step:; a project's next step lives in the page's store")
        out.append(e)
    return out


def frontier(d):
    """The frontier hypomnemata of each project with a notebook (hypomnemata ›
    kinds): its questions whose lineage is in canon and which are not canon
    themselves, by pressure. /ordo reads them off the notebook, only when its
    revision has changed, and keeps them in projects/<id> › rule.hypomnemata
    (revision, frontier, and `end`: the end the notebook's root states, as text,
    which the year's count reads each frontier against); each frontier question is
    a work item the page links to the notebook."""
    out = []
    for p in d["projects"]:
        h = p.get("hypomnemata")
        if not h:
            continue
        if not isinstance(h, dict):
            errors.append(f"project {p['id']}: hypomnemata is {h!r}; it is a map with a notebook, a revision and a frontier")
            continue
        if not p.get("active", True):
            continue
        if "frontier" in h and h.get("revision") is None:
            errors.append(f"project {p['id']}: a frontier with no revision; /ordo writes both, from one read of the notebook")
        if "frontier" in h and not h.get("notebook"):
            errors.append(f"project {p['id']}: a frontier with no notebook; each question is read and answered there")
        if "end" in h and not (isinstance(h["end"], str) and h["end"].strip()):
            errors.append(f"project {p['id']}: hypomnemata.end is {h['end']!r}; it is the end the notebook's "
                          "root states, as text, or is left out where the root states none")
        seen = set()
        for q in h.get("frontier") or []:
            if not isinstance(q, dict) or not q.get("id") or not q.get("headline"):
                errors.append(f"project {p['id']}: a frontier question needs an id and a headline: {q!r}")
                continue
            if q["id"] in seen:
                errors.append(f"project {p['id']}: frontier question {q['id']} is listed twice")
                continue
            seen.add(q["id"])
            pr = q.get("pressure", 0)
            if not isinstance(pr, (int, float)) or isinstance(pr, bool):
                errors.append(f"project {p['id']}: frontier question {q['id']} has pressure {pr!r}, not a number")
                pr = 0
            out.append({"id": f"q:{p['id']}:{q['id']}", "project": p["id"], "question": q["id"],
                        "what": q["headline"], "pressure": pr, "notebook": h.get("notebook")})
    return out


def ymd(v, what):
    """A plain date, YYYY-MM-DD, as a string: the page does arithmetic on it, and
    any other shape would rank as NaN."""
    s = str(v)
    if not YMD.fullmatch(s):
        errors.append(f"{what} is {v!r}, not a date YYYY-MM-DD")
    return s


def backlog(b):
    """The backlog, for the docket's closed section: what each goal is, where it would
    go and what it would cost. The gate and the review counts stay in the Rule; the
    page does not read them."""
    return [{"id": x["id"], "what": x["what"], "status": x["status"],
             "slot": x.get("slot"), "cost": x.get("cost")}
            for x in b.get("items") or []]


# ---- what the page quotes ----------------------------------------------------

def examen(a, gloss):
    """The Examen's steps in the Rule's order, each with the page's title and
    second-person prompt, and the key its answer is stored under — the Rule's id
    unless the gloss keeps an older one, so answers already written stay found."""
    steps = []
    for s in a.get("examen") or []:
        if not (isinstance(s, dict) and len(s) == 1):
            errors.append(f"rule/examen: {s!r} is not one `id: text` step")
            continue
        steps.append(next(iter(s.items())))
    g = glossed("examen", {i for i, _ in steps}, {"title", "prompt", "store"}, gloss.get("examen"))
    return [{"id": i, "t": g.get(i, {}).get("title") or i.replace("_", " ").capitalize(),
             "p": g.get(i, {}).get("prompt") or text, "k": g.get(i, {}).get("store") or i}
            for i, text in steps]


def exit_rite(a, gloss):
    """The exit rite's steps, each with the page's short wording, which the gloss
    gives in the Rule's order — so a step added or dropped fails here. The first is
    the resume line, the one step only work takes: the page leaves it off the rest."""
    steps = (a.get("exit_rite") or {}).get("steps") or []
    short = gloss.get("exit_rite") or []
    if steps and "resume line" not in str(steps[0]).lower():
        errors.append("rule/exit_rite: steps must begin with the resume line, the step only work takes")
    if len(short) != len(steps):
        errors.append(f"{GLOSS}: exit_rite has {len(short)} step(s), the Rule {len(steps)}")
        short = []
    return [{"do": s, "short": short[n] if short else None} for n, s in enumerate(steps)]


def ration(ledger):
    """rule/ledger › drink: the week's ration and the day's most. The page counts the
    week from Sunday, the sitting, and nothing else."""
    dk = ledger.get("drink") or {}
    r = {"week": dk.get("ration_per_week"), "day": dk.get("max_per_day")}
    for k, v in r.items():
        if type(v) is not int or v < 0:
            errors.append(f"rule/ledger drink: the {k}'s ration {v!r} is not a whole number")
    if dk.get("week_starts") != "sun":
        errors.append(f"rule/ledger drink: week_starts {dk.get('week_starts')!r}; the page counts the week from sun")
    return r


def timebox(u):
    """rule/policy › todo.timebox: a repair's diagnostic session, and how many."""
    t = (u.get("policy") or {}).get("timebox") or {}
    r = {"minutes": t.get("diagnostic_minutes"), "sessions": t.get("max_sessions")}
    for k, v in r.items():
        if type(v) is not int or v < 1:
            errors.append(f"rule/policy todo.timebox: {k} {v!r} is not a whole number, at least 1")
    return r


def bell_lead(a):
    """rule/office › meta.warning_bell_minutes: the Cadence calendar's warning before
    each bell, read by notifiers.py for the events and carried to the page, where
    inside it the bell has as good as rung."""
    v = (a.get("meta") or {}).get("warning_bell_minutes")
    if type(v) is not int or v < 0:
        errors.append(f"rule/office: meta.warning_bell_minutes {v!r} is not a whole number of minutes")
    return v


def due_after(u):
    """rule/policy › todo.due_after_days: when a TODO item with no date falls due,
    counted from its capture — the cadence the order ranks it by."""
    v = (u.get("policy") or {}).get("due_after_days")
    if type(v) is not int or v < 1:
        errors.append(f"rule/policy todo.due_after_days: {v!r} is not a whole number, at least 1")
    return v


# ---- writing -----------------------------------------------------------------

def day_starts(a):
    """When the page's day begins, by the wall clock (rule/office › meta.day_starts).
    Quoted HH:MM, and before every bell: a bell before it would be rung on the
    previous day."""
    v = a["meta"].get("day_starts")
    if not isinstance(v, str) or not CLOCK.fullmatch(v):
        errors.append(f"rule/office: meta.day_starts is {v!r}; it must be a quoted \"HH:MM\"")
        return "00:00"
    for key, anchor in a["anchors"].items():
        if str(anchor.get("bell")) <= v:
            errors.append(f"rule/office: {key} rings at {anchor.get('bell')}, not after meta.day_starts {v}")
    return v


def compile(r=None):
    """The Rule as the page reads it: each constant by name, in the page's order.
    Every refusal above lands in `errors`; the caller decides what a refusal stops."""
    r = r or ruledir.current()
    a, d, u, b, ledger, gloss = r.anchors, r.docket, r.todo, r.backlog, r.ledger, r.gloss or {}
    for s in gloss:
        if s not in ("anchors", "commitments", "examen", "exit_rite"):
            errors.append(f"{GLOSS}: has a section {s} the page does not read")
    ps = projects(d)
    # The page charges an item that names no project to the one marked default,
    # and the record gate files it under the policy's default_project: one project,
    # active, named the same in both places, or the two would part ways.
    marked = [p["id"] for p in d["projects"] if p.get("default")]
    said = ((u or {}).get("policy") or {}).get("default_project")
    if len(marked) != 1:
        errors.append(f"{len(marked)} projects are marked default ({', '.join(marked) or 'none'}); the Rule marks one")
    elif marked[0] not in {p["id"] for p in ps}:
        errors.append(f"the default project {marked[0]} is not active; an item that names none would go nowhere")
    if said is None and marked:
        errors.append(f"the policy names no todo.default_project; the project marked default is {marked[0]}")
    if said is not None and marked and said not in marked:
        errors.append(f"the policy's default_project is {said}, but the project marked default is {marked[0]}")
    # The allocations share the realistic supply; more than it leaves some project
    # short however the week is worked, and the review reads that as a wrong number.
    supply, total = d["policy"].get("realistic_per_week"), sum(p["allocation"] for p in ps if type(p["allocation"]) is int)
    if supply and total > supply:
        print(f"WARN   allocations add up to {total}, more than the policy's realistic_per_week of {supply}")
    fx = commitments(a, d, gloss)
    if ledger.get("dispensations"):
        errors.append(f"{LEDGER} has dispensations; a stretch declared ahead is a fixture on the calendar "
                      "now (a commitment with all_day: true and keep:)")
    fr = frontier(d)
    clock((a["meta"].get("lights_out") or {}).get("target"), "meta lights_out target")
    w = a["meta"]["winter"]
    ds = day_starts(a)
    bs = blocks(a, gloss)
    return {
        "BLOCKS": bs, "COMMITMENTS": fx, "PROJECTS": ps, "SHELVED": projects(d, active=False),
        "FRONTIER": fr, "BACKLOG": backlog(b),
        "WHOLE_DAYS": whole_days(a, bs), "WINTER": {"start": w["start"], "end": w["end"]},
        "DAY_START": ds, "EXAMEN": examen(a, gloss), "EXIT_RITE": exit_rite(a, gloss),
        "RATION": ration(ledger), "TIMEBOX": timebox(u), "TODO_CADENCE": due_after(u),
        "BELL_LEAD": bell_lead(a),
    }


def stored(v):
    """A compiled value as the store holds it: a field the Rule leaves unset is left
    out: the page reads a missing field and a null one differently."""
    if isinstance(v, dict):
        return {k: stored(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [stored(x) for x in v]
    return v


def main():
    compile()
    for e in errors:
        print("ERROR ", e)
    if errors:
        sys.exit(1)
    print("ok  the Rule compiles")


if __name__ == "__main__":
    main()
