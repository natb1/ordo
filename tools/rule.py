#!/usr/bin/env python3
"""What a calendar event is to the day: a meeting or a fixture.

Both are calendar events, and nothing else tells them apart at the source
(hypomnemata › kinds). A MEETING falls within a work session: it spends that
session and leaves the base daily schedule as it is. A FIXTURE does not, and the
schedule warps around it. So the kind is never written down. It is computed, here,
from where the event falls, and every tool that reads the Rule asks this file.

A block runs from its bell to the next, and opens with its Office. Its work session
is what is left: from the end of the Office to the next bell. An event is a meeting
when everything it takes of the day — prep, the ride there, the event, the ride back
and the settle — lies inside one such session on every day it is on, and it moves no
bell. Anything else is a fixture. It is read on every distinct day it is on from
today (variants()), and a meeting carries, by weekday, the work item of the session
it spends (classify(), the compiler's `takes`). An end before its start runs past
midnight (busy()).

Whether an item is on a date — weekday, block, the fixtures it follows or gives
way to, the season and a whole day's keep — is why_not() / item_on(), and every
caller with a date asks it.

An event is on a weekday (`weekday:`), on one date (`date:`), or over a range of
dates (`first:`, `last:`; `from:` and `to:` are a route's two ends). One that takes whole days (`all_day: true`) has no hours: it
names what it keeps of the Office (`keep:`), and what it does not keep is not
expected on those days.

    ORDO_RULE=<dir> python3 tools/rule.py    # each event, its kind, and why

Today has one definition, the Rule's clock (hypomnemata › record): the date in
`meta.timezone`, turning at `meta.day_starts` and not at midnight, as the page's
logicalToday() has it. Every tool reads it from here; none reads the machine's date.
"""
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CLOCK = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
# A time as the page writes one ("9:40 AM", fmt()): no padding, upper-case AM/PM.
CLOCK12 = re.compile(r"(1[0-2]|[1-9]):([0-5]\d) ([AP]M)")


class RuleError(Exception):
    """the Rule says something no day can be built from."""


def hm(s, where="a time"):
    # A number where a time should be (660 for 11:00): say so rather than a traceback.
    if not (isinstance(s, str) and CLOCK.fullmatch(s)):
        raise RuleError(f"{where}: {s!r} is not a quoted \"HH:MM\"")
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def clock(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def day_of(d, where="a date"):
    try:
        return date.fromisoformat(str(d))
    except ValueError:
        raise RuleError(f"{where}: {d!r} is not a date")


def weekday_of(d):
    """The Rule's name for a date's weekday."""
    return DAYS[day_of(d).weekday()]


def day_starts(a):
    """When the day turns, in minutes past midnight (meta.day_starts; midnight where unset)."""
    return hm((a.get("meta") or {}).get("day_starts") or "00:00", "meta day_starts")


def winter(a, d):
    """Whether a date is inside the Rule's winter (meta.winter, "MM-DD" to "MM-DD",
    which may wrap the year end), as the page's isWinter has it."""
    w = (a.get("meta") or {}).get("winter") or {}
    if not (w.get("start") and w.get("end")):
        return False
    md = str(d)[5:10]
    if w["start"] <= w["end"]:
        return w["start"] <= md <= w["end"]
    return md >= w["start"] or md <= w["end"]


def clock_now(a, now=None):
    """The time now on the Rule's clock: an aware datetime in meta.timezone. `now`
    pins it (an ISO string or a datetime), for a test or a record told after the fact."""
    tz = ZoneInfo((a.get("meta") or {}).get("timezone") or "UTC")
    if now is None:
        return datetime.now(tz)
    if isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)


def today(a, now=None):
    """Today on the Rule's clock, YYYY-MM-DD: the day turns at meta.day_starts, so
    at 00:30 it is still the evening's date."""
    n = clock_now(a, now)
    starts = day_starts(a)
    d = n.date()
    if n.hour * 60 + n.minute < starts:
        d -= timedelta(days=1)
    return d.isoformat()


def now_text(a, now=None):
    """The time now as the page records one: "9:40 AM"."""
    n = clock_now(a, now)
    return f"{n.hour % 12 or 12}:{n.minute:02d} {'AM' if n.hour < 12 else 'PM'}"


def minutes_of(t, starts=0):
    """A time as the page writes one ("10:05 PM"), in minutes into the Rule's day:
    one before the day turns (`starts`, day_starts()) belongs to the evening before
    it. None where it is not such a time."""
    m = CLOCK12.fullmatch(str(t))
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    at = h * 60 + mi
    return at + 1440 if at < starts else at


def when(c):
    """How an event says when it is: 'weekday', 'date' or 'range'. Exactly one."""
    said = [k for k in ("weekday", "date", "first") if k in c]
    if len(said) != 1:
        raise RuleError(f"commitment {c['id']} needs one of weekday:, date: or first:/last:, and has "
                        + (" and ".join(said) if said else "none"))
    if said[0] == "first":
        lo = day_of(c["first"], f"commitment {c['id']} first")
        hi = day_of(c.get("last", c["first"]), f"commitment {c['id']} last")
        if hi < lo:
            raise RuleError(f"commitment {c['id']}: {lo} to {hi} is not a stretch of days")
        if c.get("until"):
            raise RuleError(f"commitment {c['id']} gives its last day and needs no until:")
        return "range"
    if "last" in c:
        raise RuleError(f"commitment {c['id']} has last: without first:")
    if said[0] == "date":
        day_of(c["date"], f"commitment {c['id']} date")
        if c.get("until"):
            raise RuleError(f"commitment {c['id']} is on one date and needs no until:")
    elif c["weekday"] not in DAYS:
        raise RuleError(f"commitment {c['id']}: weekday {c['weekday']!r} is not one of " + ", ".join(DAYS))
    return said[0]


def first_day(c):
    """The first date an event is on, or None for a weekday series."""
    return str(c["date"]) if "date" in c else str(c["first"]) if "first" in c else None


def last_day(c):
    """The last date an event is on, or None where a series has no end."""
    if "date" in c:
        return str(c["date"])
    if "first" in c:
        return str(c.get("last", c["first"]))
    return str(c["until"]) if c.get("until") else None


def ended(c, today):
    """Whether an event's last day is behind `today`, which the caller reads off
    the Rule's clock: nothing here falls back to the machine's date."""
    return last_day(c) is not None and last_day(c) < today


def weekdays(c):
    """Every weekday an event can fall on."""
    kind = when(c)
    if kind == "weekday":
        return [c["weekday"]]
    if kind == "date":
        return [weekday_of(c["date"])]
    lo, hi = day_of(c["first"]), day_of(c.get("last", c["first"]))
    out = []
    for n in range(min((hi - lo).days, 6) + 1):
        out.append(weekday_of(lo + timedelta(days=n)))
    return out


def whole_day(c):
    return bool(c.get("all_day"))


def on_date(c, d):
    """Whether an event is on a date: on its weekday, within its dates, and not
    ended (a series is on its `until` day itself). Raises on an event the Rule's
    checks reject, as on_weekday does."""
    d = str(d)
    return weekday_of(d) in weekdays(c) and (first_day(c) is None or first_day(c) <= d) and not ended(c, d)


def on_weekday(a, day, today=None, without=()):
    """The events with hours on a weekday that have not ended as of `today` (the
    Rule's clock unless given). A whole-day fixture has no hours and takes no part
    in the day's arithmetic."""
    today = today or globals()["today"](a)
    return [c for c in a.get("commitments") or []
            if not whole_day(c) and day in weekdays(c) and c["id"] not in without
            and not ended(c, today)]


def travel(c):
    """The ride there. Where the place varies, the worst known case: being early
    costs nothing, being late costs the appointment."""
    locs = c.get("locations") or []
    return max(x["travel_minutes"] for x in locs) if locs else c.get("travel_minutes", 0)


def busy(c):
    """What an event occupies: [prep starts, back again). Prep is not free time —
    you are changing, not working — and neither is the settle after a return. No end
    recorded gives None: it eats the rest of its block, the safe way to be wrong.

    An end before its start runs past midnight: the Rule's day does not turn at
    midnight but at meta.day_starts, and its minutes run on past 1440 (the page's
    nowMins), so 19:00-00:30 occupies 1140 to 1470, never 1140 to 30. An end equal
    to its start says nothing anyone could mean, and is refused."""
    where = f"commitment {c['id']}"
    start = hm(c.get("start"), f"{where} start")
    lo = hm(c.get("derived_leave_by") or c.get("start"), f"{where} start") - c.get("prep_minutes", 0)
    if not c.get("end"):
        return lo, None
    end = hm(c["end"], f"{where} end")
    if end == start:
        raise RuleError(f"{where} ends when it starts ({c['end']}); give the hour it ends")
    if end < start:
        end += 1440
    back = end + c.get("return_minutes", c.get("travel_minutes", 0)) + c.get("settle_minutes", 0)
    return lo, back


def bell(a, key, cs):
    """A bell rings at its usual hour unless an event moves it. Where two events of
    one date move the same bell, the one that starts first moves it, as the page's
    bellOf reads its commitmentsFor (sorted by start; the Rule's order among equal
    starts)."""
    movers = [c for c in cs if c.get("sets_anchor_bell") == key and c.get("derived_anchor_bell")]
    movers.sort(key=lambda c: hm(c.get("start"), f"commitment {c['id']} start"))
    for c in movers:
        return hm(c["derived_anchor_bell"], f"commitment {c['id']} derived_anchor_bell")
    return hm(a["anchors"][key].get("bell"), f"anchors {key} bell")


def blocks(a, day, cs):
    """The day's blocks as the page builds them: (key, bell, next bell), the last
    running to lights-out."""
    lights_out = hm(a["meta"]["lights_out"]["target"], "meta lights_out target")
    bs = sorted((bell(a, k, cs), k) for k, an in a["anchors"].items()
                if day not in (an.get("skip_weekday") or []))
    return [(key, at, bs[n + 1][0] if n + 1 < len(bs) else lights_out) for n, (at, key) in enumerate(bs)]


def office(it):
    """Whether an item is the Office's: a work item is the docket's and a fixture
    item the calendar's, so only the others name a guard and are counted by it."""
    return it.get("kind") not in ("work", "fixture")


def applies(item, day, cs):
    """Whether an item is on a WEEKDAY with these events on: its skip_weekday, its
    when.weekday, the fixture it follows (when.commitment) or gives way to
    (unless.commitment). It knows no date, so it cannot say the season and knows no
    whole day: a caller that has a date asks item_on(), which is this and the rest."""
    if day in (item.get("skip_weekday") or []):
        return False
    w = item.get("when") or {}
    if "weekday" in w and day not in w["weekday"]:
        return False
    on = {c["id"] for c in cs}
    if "commitment" in w and w["commitment"] not in on:
        return False
    if (item.get("unless") or {}).get("commitment") in on:
        return False
    return True


def events_on(a, d):
    """Every event on a date, whole days among them, in the Rule's order."""
    return [c for c in a.get("commitments") or [] if on_date(c, d)]


def why_not(a, item, d, cs=None, key=None, part=None):
    """Why an item is not expected on a date, or None where it is. The one reading
    of "is this item on this date" (hypomnemata › record), as the page's itemOn and
    notExpectedOn have it:

      a      the Rule (anchors as ruledir assembles them)
      item   the item as the Office gives it; for a part, its group (and `part`)
      d      the date, YYYY-MM-DD
      cs     the events on the date; events_on(a, d) where None. Pass only the
             ones with hours to read the day's arithmetic without its whole days.
      key    the block the item stands in: its skip_weekday is checked too
      part   the id of a group's part asked about, where a whole day keeps a part

    In order: the block's skip_weekday; the item's skip_weekday, when.weekday,
    when.commitment and unless.commitment (applies()); when.not_winter inside the
    Rule's winter (winter()); and every whole-day event of the date must keep the
    item, by its own id or by the part's (a fixture's keep may name a part)."""
    d = str(d)
    day = weekday_of(d)
    cs = events_on(a, d) if cs is None else cs
    if key is not None and day in (a["anchors"][key].get("skip_weekday") or []):
        return f"the {key} block has no {day}"
    if not applies(item, day, [c for c in cs if not whole_day(c)]):
        return f"{item['id']} is off on {day}, or follows a fixture that is not on that day"
    if (item.get("when") or {}).get("not_winter") and winter(a, d):
        return f"{item['id']} is off in winter"
    for c in cs:
        keep = c.get("keep") or []
        if whole_day(c) and item["id"] not in keep and (part is None or part not in keep):
            return (f"{c['id']} takes the whole day and keeps "
                    + (", ".join(keep) or "nothing of the Office"))
    return None


def item_on(a, item, d, cs=None, key=None, part=None):
    """Whether an item is expected on a date: why_not() finds no reason it is not."""
    return why_not(a, item, d, cs, key, part) is None


def minutes(it):
    """A group's minutes are its parts' where every part gives some."""
    kids = [k.get("minutes") for k in it.get("children") or []]
    if kids and None not in kids:
        return sum(kids)
    return it.get("minutes", 0)


def conditional(it):
    w = it.get("when") or {}
    return "ledger" in w or "floor_per_week" in w


def sessions(a, day, cs, d=None):
    """Each block's work session on a weekday: {block: (start, end)}. The session
    opens when the block's Office is done, at the minutes its unconditional items
    ask for, and closes at the next bell. A block with no work item that day has
    none.

    Given the date `d` (of that weekday), its items are the date's (item_on: the
    season too). Without one it is the weekday read outside winter: an item off in
    winter is counted, the longer Office and the shorter session — the safe way to
    be wrong about a meeting."""
    out = {}
    for key, at, end in blocks(a, day, cs):
        items = [it for it in a["anchors"][key]["items"]
                 if (item_on(a, it, d, cs) if d is not None else applies(it, day, cs))]
        if not any(it.get("kind") == "work" for it in items):
            continue
        office = sum(minutes(it) for it in items if it.get("kind") != "work" and not conditional(it))
        out[key] = (at + office, end)
    return out


def _breaks(a, today, span):
    """The dates from `today` on where what the day holds can change: each event's
    first day and the day after its last, the winter's ends, and a year on."""
    lo = day_of(today)
    hi = lo + timedelta(days=span)
    out = {lo}
    for c in a.get("commitments") or []:
        if first_day(c):
            out.add(day_of(first_day(c)))
        if last_day(c):
            out.add(day_of(last_day(c)) + timedelta(days=1))
    w = (a.get("meta") or {}).get("winter") or {}
    if w.get("start") and w.get("end"):
        for y in range(lo.year, max(hi.year, max(out).year) + 2):
            for md, after in ((w["start"], 0), (w["end"], 1)):
                try:
                    out.add(date.fromisoformat(f"{y}-{md}") + timedelta(days=after))
                except ValueError:
                    pass    # 02-29 in a year without it
    hi = max([hi] + list(out))
    return sorted(x for x in out if lo <= x <= hi) + [hi + timedelta(days=7)]


def variants(a, today, span=371):
    """Every distinct day the Rule can render from `today` on: [(date, events)], one
    date for each weekday, set of events with hours and season that occurs — the
    first date it does. Between two dates where something changes (_breaks) a week
    shows every weekday, so nothing is missed: a second event moving a bell on a
    later date is read on that date, with what is on with it. A year at the least,
    so both seasons are read."""
    out, seen = [], set()
    bs = _breaks(a, today, span)
    for p, q in zip(bs, bs[1:]):
        for n in range(min((q - p).days, 7)):
            d = (p + timedelta(days=n)).isoformat()
            cs = [c for c in events_on(a, d) if not whole_day(c)]
            k = (weekday_of(d), tuple(sorted(c["id"] for c in cs)), winter(a, d))
            if k not in seen:
                seen.add(k)
                out.append((d, cs))
    return out


def _own_days(a, c):
    """An event's own dates, for one that has ended: its date, its range (a year of
    it at most), or a series' last week."""
    last = day_of(last_day(c))
    lo = day_of(first_day(c)) if first_day(c) else last - timedelta(days=6)
    lo = max(lo, last - timedelta(days=370))
    out = []
    for n in range((last - lo).days + 1):
        d = (lo + timedelta(days=n)).isoformat()
        if on_date(c, d):
            out.append((d, [x for x in events_on(a, d) if not whole_day(x)]))
    return out


def classify(a, c, today=None):
    """('meeting' | 'fixture', why, takes). See the top of the file. `takes` is, for
    a meeting, the session it spends on each weekday it falls on: {weekday: the work
    item id of the block that holds it}, e.g. {"sun": "focus_1"}; None for a fixture.

    The event is read on every distinct day it is on from `today` (variants(): the
    other events of that date, the bells they move and the season), or, where it has
    ended, on its own last dates. It is a meeting only where it lies in one session
    on every one of them. Where two dates of one weekday put it in different
    sessions, `takes` names the first of them, as of today."""
    if whole_day(c):
        return "fixture", "it takes the whole day", None
    if c.get("sets_anchor_bell"):
        return "fixture", f"it moves the {c['sets_anchor_bell']} bell", None
    lo, back = busy(c)
    if back is None:
        return "fixture", "it gives no end", None
    today = today or globals()["today"](a)
    weekdays(c)     # an event the Rule's checks reject raises here, before any date
    days = [(d, cs) for d, cs in variants(a, today) if c in cs] if not ended(c, today) else []
    if not days:
        days = _own_days(a, c)
    why, takes = [], {}
    for d, cs in days:
        day = weekday_of(d)
        ss = sessions(a, day, cs, d)
        held = [k for k, (s, e) in ss.items() if s <= lo and back <= e]
        if not held:
            near = "; ".join(f"{k} {clock(s)}-{clock(e)}" for k, (s, e) in ss.items())
            return "fixture", (f"on {day} {d} it takes {clock(lo)}-{clock(back)}, inside no work session"
                               + (f" ({near})" if near else "")), None
        if day not in takes:
            takes[day] = next(it["id"] for it in a["anchors"][held[0]]["items"]
                              if it.get("kind") == "work" and item_on(a, it, d, cs))
            why.append(f"{day} {held[0]}")
    return "meeting", "within the work session of " + ", ".join(why), takes


def kind(a, c, today=None):
    """('meeting' | 'fixture', why). See the top of the file and classify()."""
    return classify(a, c, today)[:2]


def takes(a, c, today=None):
    """The session a meeting spends on each weekday, {weekday: work item id}; None
    for a fixture (classify())."""
    return classify(a, c, today)[2]


def project(c, d):
    """The project a meeting spends a session of: the one it names, else the one
    whose calendar holds every unassigned event, the default."""
    if c.get("project"):
        return c["project"]
    return next((p["id"] for p in d["projects"] if p.get("default")), None)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ruledir
    a = ruledir.current().anchors
    try:
        for c in a.get("commitments") or []:
            k, why = kind(a, c)
            print(f"{c['id']:<18}{k:<9}{why}")
    except RuleError as e:
        print("ERROR ", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
