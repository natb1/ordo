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
departure item splits checked on each side of it, in the order the day runs. A
weekday whose fixture has a last day still to come (an `until`, a `date`, the end of
a range) is checked twice, with it and without it, since the page renders both; past
it, only without. A fixture that takes whole days has no hours and is not counted:
what it does not keep is simply not expected. Which events are meetings and which
fixtures is printed last (tools/rule.py); the arithmetic is the same for both.

The day's arithmetic is rule.py's — one reading of what an event occupies, of where
a bell rings and of which items a day has — so the kind an event is given and the
capacity it is checked against can never come from two definitions.

    ORDO_RULE=<dir> python3 tools/check_capacity.py [--strict]
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
# commitmentOn). One whose until has passed is not on its weekday at all; one whose
# until is still to come is checked both ways, since both weekdays will be rendered.
# A fixture on one date is the same case: its weekday is rendered with it that once
# and without it every other week, and it is over the day after. Two of them on the
# same weekday are checked together even when their dates differ, which errs safe.
TODAY = rule.today(A)
OFF = set()


last_day = rule.last_day


def ended(c):
    return rule.ended(c, TODAY)


def commitments(day):
    """Every event with hours on this weekday, meeting and fixture alike. Sunday has
    three — the sitting, the game and leisure — and the earlier version of this
    returned only the first one it found, which would have silently ignored the
    rest."""
    return rule.on_weekday(A, day, TODAY, OFF)


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
    or off them (unless: {commitment: X})."""
    return rule.applies(item, day, commitments(day))


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
        # Past its until it has you nowhere, and the bell it moved is back at its hour.
        for day in ([] if ended(c) else rule.weekdays(c)):
            for key, at, _ in day_blocks(day):
                if back is not None and lo < at < back:
                    errors.append(f"{day} {key}: its bell at {clock(at)} rings while {cid} has you "
                                  f"({clock(lo)}-{clock(back) if back else '?'})")

    # ---- every block, every day, and each weekday again once its fixtures end -------
    # A passed until is a note, not a warning: the entry stays in the Rule (README),
    # and --strict would make it block every publish from then on.
    notes = [f"commitment {c['id']}: its last day ({last_day(c)}) has passed, so {', '.join(rule.weekdays(c))} is "
             "checked without it" for c in A.get("commitments") or [] if ended(c)]
    passes = []
    for day in DAYS:
        passes.append((day, ()))
        ending = tuple(c["id"] for c in commitments(day) if last_day(c))
        if ending:
            passes.append((day, ending))
    for day, off in passes:
        OFF.clear(); OFF.update(off)
        cs = commitments(day)
        for key, start, end in day_blocks(day):
            items = in_order([it for it in A["anchors"][key]["items"] if applies(it, day)], day)
            for label, lo, hi, part in segments(key, start, end, items, cs):
                if off:
                    label = f"{label} (no {'+'.join(off)})"
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

    w = f"{'day':<5}{'block':<20}{'avail':>6}{'office':>8}{'+cond':>7}{'slack':>7}"
    print(w)
    print("-" * len(w))
    for day, label, avail, base, full, slack in rows:
        mark = "  <-- OVER" if base > avail else ("  (tight)" if slack < 30 else "")
        print(f"{day:<5}{label:<20}{avail:>6}{base:>8}{full:>7}{slack:>7}{mark}")

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
