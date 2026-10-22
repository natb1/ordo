#!/usr/bin/env python3
"""The frozen record the counts tests read: four weeks of days as the Cadence page
writes them, with the gaps, the unanswered bells, the moved bells and the shared
slots the tests count, and three weekly snapshots that hold one Rule. Run it to
lay the files out again. The days are invented, and nothing here is anyone's record.

    python3 tools/fixture/record/make.py
"""
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
OFFICE = ["meds", "weight", "breakfast", "sync", "dog", "teeth", "shower", "lunch", "dinner", "dog_2",
          "dishes", "garden", "examen", "great_silence", "sleep"]
BY_WEEKDAY = {"tue": ["trash"], "thu": ["recycling"]}
AT = {"morning": "7:03 AM", "midday": "11:01 AM", "vespers": "4:02 PM", "evening": "8:00 PM"}


def bell(key, projects=(), line=False, kept=(), at=None, backfilled=False):
    b = {"answeredAt": at or AT[key], "delay": 0, "early": 0, "ticked": True,
         "projects": list(projects), "undertakings": [], "threads": {}}
    if line:
        b["threads"] = {p: "where to pick up" for p in projects}
    if kept:
        b["kept"] = list(kept)
    if backfilled:
        b["backfilled"] = True
    return b


def day(s, bells, focus=None, gym=False, off=(), pours=0, sleep="10:00 PM", na=("groceries",), backfilled=False,
        ticked=()):
    """`ticked` names the slots the page ticks without a project: one a meeting took,
    or one whose bell was answered with nothing picked."""
    wd = DAYS[date.fromisoformat(s).weekday()]
    rec = {"date": s, "items": {}, "times": {}, "bells": {}, "focus": {}, "examen": {}, "na": {}, "pours": {},
           "cancelled": {}, "drinks": None, "meds": None}
    for i in OFFICE + BY_WEEKDAY.get(wd, []):
        if i not in off:
            rec["items"][i] = True
    if gym:
        rec["items"]["gym"] = True
    for i in na:
        rec["na"][i] = True
    for key, b in bells.items():
        if b is not None:
            rec["bells"][key] = b
    for slot, f in (focus or {}).items():
        rec["focus"][slot] = f
        if f.get("projects") or f.get("undertakings"):
            rec["items"][slot] = True
    for slot in ticked:
        rec["items"][slot] = True
    for n in range(pours):
        rec["pours"][f"p{n}"] = 1
    if sleep:
        rec["times"]["sleep"] = sleep
    if backfilled:
        rec["backfilled"] = True
    return rec


def sunday(s, pours):
    """The sitting takes the first slot and leisure the third: the bells that close
    them record no project and tick the slot, as the page records a meeting's."""
    return day(s, {"morning": bell("morning"), "midday": bell("midday"), "vespers": bell("vespers", at="6:31 PM"),
                   "evening": bell("evening")}, pours=pours, sleep="10:40 PM", na=(), ticked=("focus_1", "focus_3"))


def tuesday(s):
    """The improv Tuesday, the same both weeks: the evening bell moved to 5:31, the
    second slot planned and its bell answered with nothing picked (the page ticks
    the slot all the same), dishes lapsed, no pour, a late night."""
    return day(s, {"morning": bell("morning"), "midday": bell("midday", ["canondb"], line=True),
                   "vespers": bell("vespers"), "evening": bell("evening", ["nix_config"], line=True, at="5:31 PM")},
               {"focus_1": {"planned": "canondb", "projects": ["canondb"]},
                "focus_2": {"planned": "ordo", "projects": []},
                "focus_3": {"planned": "nix_config", "projects": ["nix_config"]}},
               gym=True, off=("dishes",), pours=0, sleep="11:05 PM", ticked=("focus_2",))


def plain(s, gym):
    """A full day, each slot planned and worked as planned, a line at every bell."""
    f = {"focus_1": {"planned": "canondb", "projects": ["canondb"]},
         "focus_2": {"planned": "ordo", "projects": ["ordo"]},
         "focus_3": {"planned": "nix_config", "projects": ["nix_config"]}}
    return day(s, {"morning": bell("morning"), "midday": bell("midday", ["canondb"], line=True),
                   "vespers": bell("vespers", ["ordo"], line=True),
                   "evening": bell("evening", ["nix_config"], line=True)}, f, gym=gym, pours=1)


def main():
    days = []
    # Two earlier weeks, read by the month's four-week criterion alone.
    d = date(2026, 9, 20)
    while d <= date(2026, 10, 3):
        s, wd = d.isoformat(), DAYS[d.weekday()]
        if s == "2026-09-23":
            pass   # a day the store lacks
        elif wd == "sun":
            days.append(sunday(s, 2))
        else:
            rec = plain(s, gym=wd in ("mon", "tue", "thu", "sat"))
            if s == "2026-09-30":
                del rec["bells"]["evening"]   # one bell unanswered
            days.append(rec)
        d += timedelta(days=1)
    # The week before the one under review.
    days.append(sunday("2026-10-04", 2))
    days.append(plain("2026-10-05", gym=True))
    days.append(tuesday("2026-10-06"))
    days.append(day("2026-10-08", {"morning": bell("morning"), "midday": bell("midday", ["ordo"], line=True),
                                   "vespers": bell("vespers", ["canondb"], line=True), "evening": bell("evening", ["canondb"])},
                    {"focus_1": {"planned": "ordo", "projects": ["ordo"]},
                     "focus_2": {"planned": "canondb", "projects": ["canondb"]},
                     "focus_3": {"planned": "canondb", "projects": ["canondb"]}}, gym=True, pours=2, sleep="10:10 PM"))
    # Backfilled from memory: every bell recorded later, one not at all.
    days.append(day("2026-10-09", {"morning": bell("morning", backfilled=True),
                                   "midday": bell("midday", ["canondb"], backfilled=True),
                                   "evening": bell("evening", ["ordo"], backfilled=True)},
                    {"focus_1": {"planned": "canondb", "projects": ["canondb"]},
                     "focus_3": {"planned": "ordo", "projects": ["ordo"]}},
                    pours=1, sleep=None, backfilled=True))
    days.append(day("2026-10-10", {"morning": bell("morning"), "midday": bell("midday"),
                                   "vespers": bell("vespers", ["ordo"], kept=["ordo"]),
                                   "evening": bell("evening", ["ordo"])},
                    {"focus_2": {"planned": "ordo", "projects": ["ordo"]},
                     "focus_3": {"planned": "ordo", "projects": ["ordo"]}}, gym=True, pours=0, sleep="11:20 PM",
                    ticked=("focus_1",)))
    # The week under review: Wednesday missing, Tuesday's evening bell moved by improv,
    # Thursday's vespers bell unanswered, a slot shared, a plan overridden, one not worked.
    days.append(sunday("2026-10-11", 3))
    days.append(day("2026-10-12", {"morning": bell("morning"), "midday": bell("midday", ["canondb"], line=True),
                                   "vespers": bell("vespers", ["ordo", "nix_config"], kept=["ordo"]),
                                   "evening": bell("evening", ["canondb"])},
                    {"focus_1": {"planned": "canondb", "projects": ["canondb"]},
                     "focus_2": {"planned": "ordo", "projects": ["ordo", "nix_config"]},
                     "focus_3": {"planned": "nix_config", "projects": ["canondb"]}}, gym=True, pours=1, sleep="9:55 PM"))
    days.append(tuesday("2026-10-13"))
    days.append(day("2026-10-15", {"morning": bell("morning"), "midday": bell("midday", ["ordo"], line=True),
                                   "vespers": None, "evening": bell("evening", ["canondb"])},
                    {"focus_1": {"planned": "ordo", "projects": ["ordo"]},
                     "focus_2": {"projects": ["canondb"]},
                     "focus_3": {"planned": "canondb", "projects": ["canondb"]}},
                    gym=True, off=("dinner",), pours=2, sleep="10:10 PM"))
    fri = day("2026-10-16", {"morning": bell("morning"), "midday": bell("midday", ["canondb"], line=True),
                             "vespers": bell("vespers", ["nix_config"], line=True),
                             "evening": bell("evening", ["ordo"], line=True)},
              {"focus_1": {"planned": "canondb", "projects": ["canondb"]},
               "focus_2": {"planned": "nix_config", "projects": ["nix_config"]},
               "focus_3": {"planned": "ordo", "projects": ["ordo"], "undertakings": ["i123"]}},
              pours=1, na=("groceries", "garden"))
    fri["bells"]["evening"]["undertakings"] = ["i123"]
    days.append(fri)
    days.append(day("2026-10-17", {"morning": bell("morning"), "midday": bell("midday"),
                                   "vespers": bell("vespers", ["ordo"], kept=["ordo"]),
                                   "evening": bell("evening", ["canondb"])},
                    {"focus_2": {"planned": "ordo", "projects": ["ordo"]},
                     "focus_3": {"planned": "canondb", "projects": ["canondb"]}}, gym=True, pours=0, sleep="11:20 PM",
                    ticked=("focus_1",)))
    for sub in ("days", "snapshots", "todo"):
        shutil.rmtree(HERE / sub, ignore_errors=True)
        (HERE / sub).mkdir()
    for rec in days:
        (HERE / "days" / (rec["date"] + ".json")).write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    # One Rule in every snapshot; the allocation set at the last sitting rides beside
    # it, which a review does not propose and the stability criterion reads apart.
    held = [{"collection": "rule", "doc_id": "policy", "data": {"docket": {"realistic_per_week": 20}}}]
    for n, s in enumerate(("2026-10-04", "2026-10-11", "2026-10-18")):
        snap = {"at": f"{s}T13:00:00Z", "docs": held + [{"collection": "projects", "doc_id": "canondb",
                                                          "data": {"id": "canondb", "rule": {"allocation": 7 - (n == 2)}}}]}
        if n:
            snap["counts"] = {"week": {"slots_worked": 12 + n}}
        (HERE / "snapshots" / (s + ".json")).write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n")
    (HERE / "todo" / "i123.json").write_text(json.dumps(
        {"id": "i123", "project": "ordo", "what": "Replace the kitchen tap", "captured": "2026-10-10"},
        indent=2, sort_keys=True) + "\n")
    print(f"{len(days)} days, 3 snapshots, 1 todo item under {HERE}")


if __name__ == "__main__":
    main()
