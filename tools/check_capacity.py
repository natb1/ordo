#!/usr/bin/env python3
"""Fail if a block asks for more minutes than it has, or if a fixture's derived
times do not follow from its travel, prep and settle.

Sunday 20 Sep is why this exists. Its midday block ran 11:00 to a 12:39 leave-by —
99 minutes — while its Office asked for about 127. Everything after the dog was
structurally impossible, and without this check the log would have recorded five
lapses where there was really one bad schedule.

The day checked is the day the page renders: the bells the Rule gives, moved
where a fixture moves them and taken in the order they ring, the last block ending
at lights-out; a departure taking its prep as well as the ride; and a block that a
departure item splits checked on each side of it, in the order the day runs. Every
distinct day the page can render from today on is checked (rule.variants): each
weekday with each set of events that is on together on some date, and in and out of
the winter — so a second event that moves the same bell on a later date is checked
on that date, and an item off in winter is not counted in it. An event past its
last day is not on any of them. An event that ends before it starts runs past
midnight (rule.busy). A fixture that takes whole days has no hours and is not
counted: what it does not keep is simply not expected. Which events are meetings and which
fixtures is printed last (tools/rule.py); the arithmetic is the same for both.

The day's arithmetic is rule.py's — one reading of what an event occupies, of where
a bell rings and of which items a day has — so the kind an event is given and the
capacity it is checked against can never come from two definitions.

    ORDO_RULE=<dir> python3 tools/check_capacity.py [--strict] [--today YYYY-MM-DD]

--today pins the Rule's today, for a test; the Rule's clock otherwise.
"""
import sys

import rule
import ruledir

A = ruledir.current().anchors
DAYS = rule.DAYS
# A declared variation is named for the weekday it orders.
DOW = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
       "friday": "fri", "saturday": "sat", "sunday": "sun"}

STRICT = "--strict" in sys.argv

errors, warnings, rows = [], [], []

hm, clock, travel, busy, minutes = rule.hm, rule.clock, rule.travel, rule.busy, rule.minutes

# A fixture's `until` retires it, and what it causes goes with it (the page's
# commitmentsFor). Each day checked is a date (rule.variants) with the events on it,
# so what is on together is what the page renders together.
TODAY = (sys.argv[sys.argv.index("--today") + 1] if "--today" in sys.argv else rule.today(A))
PASS = {"date": None, "cs": []}


last_day = rule.last_day


def ended(c):
    return rule.ended(c, TODAY)


def commitments(day):
    """Every event with hours on the date checked, meeting and fixture alike. Sunday
    has three — the sitting, the game and leisure — and the earlier version of this
    returned only the first one it found, which would have silently ignored the
    rest."""
    assert rule.weekday_of(PASS["date"]) == day
    return PASS["cs"]


def day_blocks(day):
    """The day's blocks as the page builds them (rule.blocks: a block skipped that
    weekday is gone, the rest ordered by when their moved bells ring, each running to
    the next bell and the last to lights-out), plus the one check the page cannot
    make: a moved bell that has passed its neighbour."""
    out = rule.blocks(A, day, commitments(day))
    for key, at, end in out:
        if end <= at:
            errors.append(f"{day} {key}: its bell at {clock(at)} rings at or after the next "
                          f"({clock(end)}) — a moved bell has passed its neighbour")
    return out


def applies(item, day):
    """An item a fixture causes is on the days the fixture is (when: {commitment: X}),
    or off them (unless: {commitment: X}); one off in winter is off on a winter date
    (rule.item_on, the one reading of an item on a date)."""
    return rule.item_on(A, item, PASS["date"], commitments(day))


def in_order(items, day):
    """A declared variation may order a weekday's items differently, and the page
    applies it the same way: an item the order does not name keeps its place, just
    before the next one it does (the page's inOrder). A variation a fixture causes
    names it (commitment:) and holds only on the days that fixture is on — the page's
    orderDuring — so the pass without the fixture is checked in the plain order, as
    the page renders it."""
    order, on = [], {c["id"] for c in commitments(day)}
    for name, v in (A.get("variations") or {}).items():
        if DOW.get(name) != day:
            continue
        if v.get("commitment") and v["commitment"] not in on:
            continue
        order = [i for i in v.get("item_order") or [] if not i.startswith("exit_")]
    ids = [it["id"] for it in items]
    if not any(i in ids for i in order):
        return items
    rank, nxt = {}, len(order)
    for it in reversed(items):
        k = order.index(it["id"]) if it["id"] in order else -1
        if k >= 0:
            nxt = k
        rank[it["id"]] = k if k >= 0 else nxt - 0.5
    return sorted(items, key=lambda it: rank[it["id"]])


def required(items, conditional):
    total = 0
    for it in items:
        if rule.conditional(it) and not conditional:
            continue
        total += minutes(it)
    return total


def free(lo, hi, cs):
    """Minutes in [lo, hi) that no fixture occupies."""
    if hi <= lo:
        return 0
    taken = 0
    for c in cs:
        b0, b1 = busy(c)
        b1 = hi if b1 is None else b1
        taken += max(0, min(hi, b1) - max(lo, b0))
    return max(0, hi - lo - taken)


def segments(key, start, end, items, cs):
    """A block a departure item splits (Tuesday's `depart`) is two stretches, and
    what the order puts before the item must fit before prep starts, what it puts
    after must fit after the return. A departure no item marks (Wednesday's
    appointment) leaves one pool: which side an item falls on is not written down."""
    by_id = {c["id"]: c for c in cs}
    out, lo, label, part = [], start, key, []
    for it in items:
        c = by_id.get(it.get("commitment"))
        if not c:
            part.append(it)
            continue
        b0, b1 = busy(c)
        out.append((f"{label}<{it['id']}", lo, max(lo, min(end, b0)), part))
        lo, label, part = min(end, end if b1 is None else max(start, b1)), f"{key}>{it['id']}", []
    out.append((label, lo, end, part))
    return out


def main():
    for c in A.get("commitments") or []:
        if c.get("sets_anchor_bell") and c["sets_anchor_bell"] not in A["anchors"]:
            raise rule.RuleError(f"commitment {c['id']} moves bell {c['sets_anchor_bell']!r}, which is not a "
                                 "block; one of " + ", ".join(A["anchors"]))
        # An event on a date, or over a range, is checked on the weekdays it falls on.
        rule.when(c)

    # ---- a group's parts add up; a fixture item carries no minutes -----------------
    for key, anchor in A["anchors"].items():
        for it in anchor["items"]:
            kids = [k.get("minutes") for k in it.get("children") or []]
            if kids and None not in kids and it.get("minutes") is not None and it["minutes"] != sum(kids):
                errors.append(f"{key} {it['id']}: {it['minutes']} min, but its parts add to {sum(kids)}")
            if it.get("kind") == "fixture" and it.get("minutes"):
                errors.append(f"{key} {it['id']}: a fixture item carries no minutes — its "
                              "commitment's prep and ride are what it takes, and would count twice")

    # ---- the derived times follow from travel, prep and settle -------------------
    for c in A.get("commitments") or []:
        if rule.whole_day(c):
            continue
        cid, t = c["id"], travel(c)
        if c.get("locations") and c.get("travel_minutes") != t:
            errors.append(f"commitment {cid}: travel_minutes {c.get('travel_minutes')}, but the worst "
                          f"location is {t}")
        start = hm(c.get("start"), f"commitment {cid} start")
        lo, back = busy(c)
        if t or c.get("derived_leave_by"):
            lb = start - t
            if not c.get("derived_leave_by"):
                errors.append(f"commitment {cid}: has travel but no derived_leave_by — it is {clock(lb)}")
            elif hm(c["derived_leave_by"], f"commitment {cid} derived_leave_by") != lb:
                errors.append(f"commitment {cid}: derived_leave_by {c['derived_leave_by']}, but start "
                              f"less travel is {clock(lb)}")
            if not c.get("derived_bell"):
                errors.append(f"commitment {cid}: has travel but no derived_bell — at the latest "
                              f"{clock(lo)}, leave-by less prep")
            elif hm(c["derived_bell"], f"commitment {cid} derived_bell") > lo:
                errors.append(f"commitment {cid}: derived_bell {c['derived_bell']} rings after prep "
                              f"must start ({clock(lo)})")
        if c.get("sets_anchor_bell"):
            if not c.get("derived_anchor_bell"):
                errors.append(f"commitment {cid}: moves {c['sets_anchor_bell']} but not to when")
            else:
                at = hm(c["derived_anchor_bell"], f"commitment {cid} derived_anchor_bell")
                # A departure moves the bell before it; a return, the one after it.
                if at <= start and at > lo:
                    errors.append(f"commitment {cid}: moves {c['sets_anchor_bell']} to {clock(at)}, after "
                                  f"prep must start ({clock(lo)}) — at the latest {clock(lo)}")
                elif at > start and (back is None or at < back):
                    errors.append(f"commitment {cid}: moves {c['sets_anchor_bell']} to {clock(at)}, before "
                                  "you are back and settled"
                                  + (f" ({clock(back)}) — at the earliest {clock(back)}" if back else ""))

    # ---- every block of every distinct day from today on ----------------------------
    # A passed until is a note, not a warning: the entry stays in the Rule (README),
    # and --strict would make it block every publish from then on.
    notes = [f"commitment {c['id']}: its last day ({last_day(c)}) has passed, so {', '.join(rule.weekdays(c))} is "
             "checked without it" for c in A.get("commitments") or [] if ended(c)]
    passes = rule.variants(A, TODAY)
    per_day = {}
    for d, cs in passes:
        per_day.setdefault(rule.weekday_of(d), []).append((d, cs))
    for day in DAYS:
        every = {c["id"] for _, cs in per_day.get(day, []) for c in cs}
        seasons = {rule.winter(A, d) for d, _ in per_day.get(day, [])}
        for d, cs in per_day.get(day, []):
            PASS["date"], PASS["cs"] = d, cs
            # which of this weekday's days it is, where it has more than one
            off = sorted(every - {c["id"] for c in cs})
            tag = ", ".join(([f"no {'+'.join(off)}"] if off else [])
                            + (["winter"] if len(seasons) > 1 and rule.winter(A, d) else []))
            tag = f" ({d}{': ' + tag if tag else ''})" if len(per_day[day]) > 1 else ""
            blocks = day_blocks(day)
            # An event has you away from its prep to its settle: no bell rings then.
            for c in cs:
                lo, back = busy(c)
                for key, at, _ in blocks:
                    if back is not None and lo < at < back:
                        errors.append(f"{day} {key}: its bell at {clock(at)} rings while {c['id']} has you "
                                      f"({clock(lo)}-{clock(back)})")
            for key, start, end in blocks:
                items = in_order([it for it in A["anchors"][key]["items"] if applies(it, day)], day)
                for label, lo, hi, part in segments(key, start, end, items, cs):
                    label += tag
                    avail = free(lo, hi, cs)
                    base = required(part, conditional=False)
                    full = required(part, conditional=True)
                    slack = avail - base
                    rows.append((day, label, avail, base, full, slack))
                    if base > avail:
                        errors.append(
                            f"{day} {label}: Office needs {base} min, block has {avail} — impossible")
                    elif full > avail:
                        warnings.append(
                            f"{day} {label}: fits at {base} min, but {full} with every conditional "
                            f"and the block has {avail} — something must slide on a full day")

    w = f"{'day':<5}{'block':<44}{'avail':>6}{'office':>8}{'+cond':>7}{'slack':>7}"
    print(w)
    print("-" * len(w))
    for day, label, avail, base, full, slack in rows:
        mark = "  <-- OVER" if base > avail else ("  (tight)" if slack < 30 else "")
        print(f"{day:<5}{label:<44}{avail:>6}{base:>8}{full:>7}{slack:>7}{mark}")

    print()
    print("meetings and fixtures, by where each event falls:")
    for c in A.get("commitments") or []:
        if not ended(c):
            k, why = rule.kind(A, c, TODAY)
            print(f"  {c['id']:<18}{k:<9}{why}")
    print()
    for n_ in notes:
        print("note  ", n_)
    for w_ in warnings:
        print("warn  ", w_)
    for e in dict.fromkeys(errors):
        print("ERROR ", e)
    failed = bool(errors) or (STRICT and bool(warnings))
    print("FAIL" if failed else "OK")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    try:
        main()
    except rule.RuleError as e:
        print(f"ERROR  {e}\nFAIL")
        sys.exit(1)
