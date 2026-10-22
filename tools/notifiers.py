#!/usr/bin/env python3
"""What the notifiers should hold, derived from the Rule.

The Clock alarms and the Cadence calendar's events are copies of the Rule that no
checker can see (README › what no checker can see). This prints the copy they
should be, so the notifier step compares against a list rather than a reading of
the Rule. It checks nothing: the phone and the calendar are out of reach.

A fixture warps the day only on the dates it happens, and the day goes back to
normal by itself when it stops. So nothing here is excluded by weekday. Every
block's bell is a series that rings every day; a fixture that moves a bell cancels
that series' instance on each of its own dates, and adds its moved bell on the same
dates. When the fixture ends, or a week of it is cancelled, there is no date left to
cancel, and the usual bell rings.

The phone cannot follow that yet: an iOS alarm repeats by weekday, with no end date
and no single date skipped. Until there is an app that schedules the alarms from the
calendar (postponed), the alarms are set by hand by weekday, and put back by hand when
a fixture ends or a week of it is cancelled (README, I.4). The first table says how.

On an export of the store, $ORDO_RULE:

    python3 tools/notifiers.py                      # from today, 14 days
    python3 tools/notifiers.py 2026-11-10           # from that day
    python3 tools/notifiers.py --cancelled improv:2026-10-20   # a week of a series
                                                    # that is off the calendar
"""
import argparse
import sys
from datetime import timedelta

import rule
import ruledir

WINDOW = 14     # days, the sync's window
DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


def mins(t, where="a time"):
    return rule.hm(t, where)


def days(ds):
    ds = [d for d in DAYS if d in ds]
    if len(ds) == 7:
        return "every day"
    if len(ds) >= 5:
        return "every day except " + ", ".join(d.capitalize() for d in DAYS if d not in ds)
    return ", ".join(d.capitalize() for d in ds)


def table(head, rows):
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for r in rows:
        print("| " + " | ".join(r) + " |")
    print()


def label(a, key, c=None):
    """The alarm's label. Its Cadence event is the label and " bell", so the two are
    reworded together or not at all."""
    name = a["anchors"][key]["name"]
    return f"{name} ({c['what']})" if c else name


def leave_alerts(c):
    """At the leave-by, and at derived_bell, when prep starts. A commitment whose
    prep starts at the bell it moves (improv) already has a bell there."""
    alerts = "at the time"
    if c.get("derived_bell") and c.get("derived_bell") != c.get("derived_anchor_bell"):
        lead = (mins(c["derived_leave_by"], f"commitment {c['id']} derived_leave_by")
                - mins(c["derived_bell"], f"commitment {c['id']} derived_bell"))
        alerts += f", and {lead} min before"
    return alerts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("start", nargs="?", help="the first date, YYYY-MM-DD (default: today)")
    ap.add_argument("--cancelled", action="append", default=[], metavar="ID:DATE",
                    help="a date a series is off the calendar; may be given again")
    args = ap.parse_args(argv)
    a = ruledir.current().anchors
    # The window opens today on the Rule's clock, never the machine's.
    today = rule.day_of(args.start if args.start else rule.today(a), "the start date")
    window = [today + timedelta(days=n) for n in range(WINDOW)]
    warn = a["meta"]["warning_bell_minutes"]

    # A fixture that takes whole days has no hours, so no bell and no leave-by.
    cs = [c for c in a.get("commitments") or [] if not rule.whole_day(c)]
    ids = {c["id"] for c in cs}
    off = set()
    for x in args.cancelled:
        cid, _, d = x.partition(":")
        if cid not in ids:
            raise rule.RuleError(f"--cancelled {x}: no commitment {cid!r} with hours")
        off.add((cid, rule.day_of(d, f"--cancelled {x}")))
    live = [c for c in cs if not rule.ended(c, today.isoformat())]
    movers = [c for c in live if c.get("sets_anchor_bell")]
    leavers = [c for c in live if c.get("derived_leave_by")]
    series = lambda c: rule.when(c) == "weekday"

    # The series: set up once, and changed only when a time changes. A block skipped
    # on a weekday (skip_weekday) never rings that day, so that one exclusion stays.
    srows, alarms = [], []
    for key, b in a["anchors"].items():
        skip = set(b.get("skip_weekday") or [])
        srows.append((b["bell"], days([d for d in DAYS if d not in skip]),
                      f"{label(a, key)} bell", f"{warn} min before", ""))
        gone = {c["weekday"] for c in movers if c["sets_anchor_bell"] == key and series(c)}
        dated = [c for c in movers if c["sets_anchor_bell"] == key and not series(c)]
        alarms.append((b["bell"], days([d for d in DAYS if d not in skip | gone]), label(a, key),
                       "; ".join(f"off on {rule.first_day(c)}" + (f" to {rule.last_day(c)}" if "first" in c else "")
                                 for c in dated)))
    for c in movers:
        lab = label(a, c["sets_anchor_bell"], c)
        alarms.append((c["derived_anchor_bell"],
                       days([c["weekday"]]) if series(c) else
                       f"once, on {rule.first_day(c)}" + (f" to {rule.last_day(c)}" if "first" in c else ""),
                       lab, f"until {c['until']}" if c.get("until") else ""))
        if series(c):
            srows.append((c["derived_anchor_bell"], days([c["weekday"]]), f"{lab} bell",
                          f"{warn} min before", f"until {c['until']}" if c.get("until") else ""))
    for c in leavers:
        if series(c):
            srows.append((c["derived_leave_by"], days([c["weekday"]]), f"Leave for: {c['what']}",
                          leave_alerts(c), f"until {c['until']}" if c.get("until") else ""))
    srows.sort(key=lambda r: (mins(r[0], f"an event at {r[0]!r}"), r[2]))
    alarms.sort(key=lambda r: (mins(r[0], f"a bell at {r[0]!r}"), r[2]))

    # Each date: what its series hold, and what the date must hold. The difference is
    # the exceptions the sync makes by hand: an instance cancelled, or a one-off added.
    held, exceptions = [], []
    for d in window:
        happens = [c for c in live if rule.on_date(c, d) and (c["id"], d) not in off]
        want, natural = {}, {}
        for key, b in a["anchors"].items():
            if rule.weekday_of(d) in (b.get("skip_weekday") or []):
                continue
            ev = (b["bell"], f"{label(a, key)} bell")
            natural[ev] = None
            if not any(c.get("sets_anchor_bell") == key for c in happens):
                want[ev] = None
            else:
                mover = next(c for c in happens if c.get("sets_anchor_bell") == key)
                natural[ev] = f"{mover['what']} moves it to {mover['derived_anchor_bell']}"
        for c in movers:
            ev = (c["derived_anchor_bell"], f"{label(a, c['sets_anchor_bell'], c)} bell")
            if series(c) and rule.on_date(c, d):
                natural[ev] = f"{c['what']} is not on this date"
            if c in happens:
                want[ev] = None
        for c in leavers:
            ev = (c["derived_leave_by"], f"Leave for: {c['what']}")
            if series(c) and rule.on_date(c, d):
                natural[ev] = f"{c['what']} is not on this date"
            if c in happens:
                want[ev] = None
        for ev in sorted(set(natural) - set(want)):
            exceptions.append((d, ev[0], ev[1], "cancel the instance: " + natural[ev]))
        for ev in sorted(set(want) - set(natural)):
            exceptions.append((d, ev[0], ev[1], "add a one-off"))
        held.append((d, sorted(want, key=lambda e: mins(e[0], f"an event at {e[0]!r}"))))

    print(f"As of {today}, through {window[-1]}.\n")
    print("Clock alarms: the bells, set by hand, snooze off. A weekday is off a block's "
          "alarm while a fixture moves that bell; when the fixture ends, tick it back on "
          "and delete the moved alarm (README, I.4).\n")
    table(["Time", "Repeat", "Label", ""], [list(r) for r in alarms])

    print("Cadence series: warnings and leave-bys, nothing else. No weekday is left out "
          "for a fixture; its dates are the exceptions below.\n")
    table(["Time", "Repeat", "Event", "Alerts", ""], [list(r) for r in srows])

    print(f"Exceptions through {window[-1]}: an instance to cancel, or a one-off to add.\n")
    if exceptions:
        table(["Date", "Time", "Event", "Do"],
              [[f"{d} {d.strftime('%a')}", t, ev, do] for d, t, ev, do in exceptions])
    else:
        print("None.\n")

    print("What each date must hold on Cadence, and nothing else:\n")
    table(["Date", "Events"], [[f"{d} {d.strftime('%a')}", " · ".join(f"{t} {ev}" for t, ev in evs)]
                               for d, evs in held])

    # The phone is the one copy kept by hand, so each change to it is named with its
    # date: a series that ends (said from 14 days before until 14 days after, since
    # nothing here can see whether it was done), a cancelled week, a one-time fixture.
    changes = []
    seen = [today - timedelta(days=WINDOW)] + window
    for c in cs:
        if not c.get("sets_anchor_bell"):
            continue
        key = c["sets_anchor_bell"]
        usual, moved = label(a, key), label(a, key, c)
        if series(c) and c.get("until"):
            back = rule.day_of(c["until"]) + timedelta(days=1)
            if seen[0] <= back <= window[-1]:
                nxt = back
                while rule.weekday_of(nxt) != c["weekday"]:
                    nxt += timedelta(days=1)
                changes.append((back, f"between {back} and {nxt.strftime('%a')} {nxt}",
                                f"delete the {moved} alarm; tick {c['weekday'].capitalize()} back on "
                                f"the {usual} alarm ({c['what']} ended {c['until']})"))
        for d in window:
            if (c["id"], d) in off and rule.on_date(c, d):
                changes.append((d, f"on {d} only", f"turn the {usual} alarm on and the {moved} alarm "
                                f"off, and back the next morning ({c['what']} is cancelled)"))
            elif not series(c) and rule.on_date(c, d):
                changes.append((d, f"on {d} only", f"turn the {usual} alarm off and set a one-time "
                                f"alarm, {moved}, at {c['derived_anchor_bell']}"))
    changes.sort(key=lambda r: r[0])
    print("Clock alarms to change by hand:\n")
    if changes:
        table(["When", "Change"], [[w, x] for _, w, x in changes])
    else:
        print("None.\n")


if __name__ == "__main__":
    try:
        main()
    except rule.RuleError as e:
        print("ERROR ", e)
        sys.exit(1)
