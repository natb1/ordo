#!/usr/bin/env python3
"""The next actions: every open TODO item and ask, across the projects, in one order.

    python3 tools/next.py DIR [--within DAYS] [--limit N] [--today YYYY-MM-DD]

DIR is an export of the store (the Rule and every `todo` document), as /ordo makes
one. The order is the page's own second tier, read across every active project at
once, because its measure needs no project to compare by (hypomnemata › allocation):
how far overdue each item is, as a fraction of the span from its capture to its date.
An item with a `by` is due on it; one without is due `todo.due_after_days` after its
capture, so it rises as it ages; an ask with a `by` is due on it like any item (past
it, its owner's `default` holds), and an ask without one follows, oldest first, as in
the page's canon. Before the deficit, the level: the items of a project whose end
keeps a basic need, then a relational one, stand first while its `holds` is false.

There is no other weight. An item's priority is never a field of its own, and nothing
here scores by leverage or importance: an owner that wants an item sooner gives it an
earlier date. What the order cannot read, the owner's reason or what an answer would
move, is the first line of the item's `notes`, printed beneath it as written.

A blocker stands just before the first thing it stops. An item another tool owns and
has not dated does not age, and is counted at the end, not listed. Dictations are the
notebook's work, not the user's next actions, and are left out.

--within DAYS lists only what is due within that many days, or overdue (an undated ask
is listed regardless); --limit N, the first N. Nothing is written.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ruledir  # noqa: E402

LEVELS = {"basic": 0, "relational": 1}


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def first_line(text, width=200):
    for line in (text or "").splitlines():
        if line.strip():
            line = line.strip()
            return line if len(line) <= width else line[:width - 1].rstrip() + "…"
    return ""


def projects_of(docs):
    out = {}
    for (c, i), d in docs.items():
        if c != "projects":
            continue
        r = d.get("rule") if isinstance(d.get("rule"), dict) else d
        if r.get("active", True):
            out[i] = {"what": r.get("what") or i, "seq": r.get("seq", 0),
                      "level": LEVELS.get(r.get("need"), 2) if r.get("holds") is False else 2,
                      "default": bool(r.get("default"))}
    return out


def ordered(docs, today, after_days=14):
    """(rows, held): rows in order, each {id, doc, project, on, over, frac, tier,
    blocked_by}; held, the count of owned undated items left out."""
    projects = projects_of(docs)
    default = next((p for p, v in projects.items() if v["default"]), None)
    todos = {i: d for (c, i), d in docs.items() if c == "todo"}
    live = {}
    for i, d in todos.items():
        if d.get("done") or d.get("removed") or not d.get("what") or d.get("kind") == "dictation" or d.get("canon"):
            continue
        pid = d.get("project") or default
        if pid in projects:
            live[i] = dict(d, id=i, project=pid)
    rows, held = {}, 0
    for i, d in live.items():
        owned = isinstance(d.get("source"), dict)
        cap = str(d.get("captured") or d.get("asked") or today)[:10]
        if d.get("by"):
            on = d["by"]
        elif d.get("kind") == "ask" or d.get("answer"):
            rows[i] = {"tier": 1, "on": None, "over": None, "frac": None, "cap": cap}
            continue
        elif owned:
            held += 1
            continue
        else:
            on = (date.fromisoformat(cap) + timedelta(days=after_days)).isoformat()
        over = days(on, today)
        rows[i] = {"tier": 0, "on": on, "over": over, "cap": cap,
                   "frac": over / max(1, days(cap, on))}
    # An answered ask waits on its owner, not the user: it goes with the undated asks.
    for i in rows:
        if live[i].get("answer"):
            rows[i]["tier"] = 1
    blocked_by = {}
    for i in rows:
        for b in live[i].get("blocks") or []:
            if b in rows:
                blocked_by.setdefault(b, []).append(i)

    def key(i):
        r, p = rows[i], projects[live[i]["project"]]
        rank = (-r["frac"],) if r["tier"] == 0 else (r["cap"],)
        return (p["level"], r["tier"]) + rank + (p["seq"], i)

    base = sorted(rows, key=key)
    out, put = [], set()

    def place(i):
        if i in put:
            return
        put.add(i)
        for b in sorted(blocked_by.get(i, []), key=key):
            place(b)
        out.append(i)

    targets = {b for bs in blocked_by.values() for b in bs}
    for i in base:
        if i not in targets or not any(t in rows for t in live[i].get("blocks") or []):
            place(i)
    for i in base:
        place(i)
    result = []
    for i in out:
        r = dict(rows[i], id=i, doc=live[i], project=live[i]["project"],
                 project_what=projects[live[i]["project"]]["what"],
                 blocked_by=[live[b]["what"] for b in blocked_by.get(i, [])])
        result.append(r)
    return result, held


def why(r, today):
    d = r["doc"]
    if r["tier"] == 1:
        if d.get("answer"):
            return f"answered; {(d.get('source') or {}).get('owner') or 'its owner'} reads it at its next run"
        return f"an ask put {r['cap']}, undated"
    over = r["over"]
    when = f"its date, {r['on']}" if d.get("by") else f"{r['on']}, from capture"
    text = (f"overdue by {over} day{'s' if over != 1 else ''} against {when}" if over > 0
            else f"due today, {when}" if over == 0
            else f"due {r['on']}, in {-over} day{'s' if over != -1 else ''}")
    dflt = (d.get("default") or "").strip()
    if dflt and over >= -14:
        text += ("; past its date, the default holds: " if over > 0 else "; if not done by then: ") + dflt
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("--within", type=int, help="only what is due within DAYS, or overdue")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--today", help="YYYY-MM-DD, in place of the Rule's clock")
    args = ap.parse_args(argv)
    docs = ruledir.read(args.dir)
    if args.today:
        today = args.today
    else:
        import rule  # noqa: E402  the Rule's clock: the day turns at day_starts
        today = rule.today(ruledir.assemble(docs).anchors)
    policy = docs.get(("rule", "policy"), {})
    after = ((policy.get("todo") or {}).get("due_after_days")) or 14
    rows, held = ordered(docs, today, after)
    if args.within is not None:
        rows = [r for r in rows if r["tier"] == 1 or r["over"] >= -args.within]
    if args.limit is not None:
        rows = rows[:args.limit]
    if not rows:
        print("nothing open")
    for n, r in enumerate(rows, 1):
        d = r["doc"]
        kind = "ask" if d.get("kind") == "ask" else "todo"
        owner = (d.get("source") or {}).get("owner")
        print(f"{n}. {d['what']}")
        print(f"   {r['project_what']} · {kind}{' from ' + owner if owner else ''} · {why(r, today)}")
        if r["blocked_by"]:
            print("   blocked by " + "; ".join(r["blocked_by"]) + ", which stand just before it")
        note = first_line(d.get("notes"))
        if note:
            print(f"   {note}")
    if held:
        print(f"\n{held} undated item{'s' if held != 1 else ''} held by an owner wait last, not listed: "
              "each rises once its owner dates it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
