#!/usr/bin/env python3
"""The next actions: the open TODO items and asks of every project, in one order.

    python3 -m unittest tools/test_next.py
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import next as nxt  # noqa: E402
import ruledir  # noqa: E402

TODAY = "2026-10-15"
SRC = {"owner": "garden", "url": "https://github.com/natb1/garden/blob/main/plan/beds.toml"}


def project(pid, seq, **rule):
    return {"id": pid, "rule": dict({"id": pid, "what": pid.title(), "seq": seq, "active": True}, **rule)}


def docs(*todos, projects=None):
    d = {("projects", p["id"]): p for p in (projects or [project("ordo", 1, default=True), project("garden", 2)])}
    d[("rule", "policy")] = {"todo": {"due_after_days": 14}}
    for t in todos:
        d[("todo", t["id"])] = t
    return d


def order(d):
    rows, held = nxt.ordered(d, TODAY)
    return [r["id"] for r in rows], held


class Order(unittest.TestCase):
    def test_one_measure_across_projects(self):
        d = docs({"id": "a", "what": "a", "project": "ordo", "captured": "2026-10-01", "by": "2026-10-20"},
                 {"id": "b", "what": "b", "project": "garden", "captured": "2026-10-01", "by": "2026-10-10"},
                 {"id": "c", "what": "c", "captured": "2026-09-20"})
        # b is 5 days over a 9-day span; c, undated, 11 over its 14; a is not yet due.
        self.assertEqual(order(d), (["c", "b", "a"], 0))

    def test_a_dated_ask_ranks_by_its_date_and_an_undated_one_follows_oldest_first(self):
        d = docs({"id": "garden-q1", "what": "q1", "kind": "ask", "project": "garden", "source": SRC,
                  "asked": "2026-10-01", "captured": "2026-10-01", "by": "2026-10-12"},
                 {"id": "garden-q2", "what": "q2", "kind": "ask", "project": "garden", "source": SRC,
                  "asked": "2026-10-03", "captured": "2026-10-03"},
                 {"id": "garden-q3", "what": "q3", "kind": "ask", "project": "garden", "source": SRC,
                  "asked": "2026-09-30", "captured": "2026-09-30"},
                 {"id": "t", "what": "t", "captured": "2026-10-14"})
        self.assertEqual(order(d), (["garden-q1", "t", "garden-q3", "garden-q2"], 0))

    def test_an_owned_undated_item_is_counted_not_listed_and_dictations_are_left_out(self):
        d = docs({"id": "garden-x", "what": "x", "project": "garden", "source": SRC, "captured": "2026-09-01"},
                 {"id": "d", "what": "d", "kind": "dictation", "captured": "2026-09-01"},
                 {"id": "done", "what": "done", "done": True, "captured": "2026-09-01"})
        self.assertEqual(order(d), ([], 1))

    def test_a_blocker_stands_just_before_what_it_stops(self):
        d = docs({"id": "late", "what": "late", "captured": "2026-09-01", "by": "2026-10-01"},
                 {"id": "fix", "what": "fix", "captured": "2026-10-14", "blocks": ["late"]})
        self.assertEqual(order(d), (["fix", "late"], 0))

    def test_a_basic_need_that_does_not_hold_comes_first(self):
        d = docs({"id": "a", "what": "a", "project": "ordo", "captured": "2026-09-01"},
                 {"id": "b", "what": "b", "project": "garden", "captured": "2026-10-14"},
                 projects=[project("ordo", 1, default=True), project("garden", 2, need="basic", holds=False)])
        self.assertEqual(order(d), (["b", "a"], 0))

    def test_an_inactive_project_is_left_out(self):
        d = docs({"id": "a", "what": "a", "project": "garden", "captured": "2026-09-01"},
                 projects=[project("ordo", 1, default=True), project("garden", 2, active=False)])
        self.assertEqual(order(d), ([], 0))


class Output(unittest.TestCase):
    def run_on(self, d, *args):
        with tempfile.TemporaryDirectory() as tmp:
            ruledir.write(tmp, d)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                nxt.main([tmp, "--today", TODAY, *args])
        return out.getvalue()

    def test_the_default_shows_once_the_date_is_near_or_past_and_the_notes_first_line(self):
        out = self.run_on(docs(
            {"id": "garden-q1", "what": "Which bed first?", "kind": "ask", "project": "garden", "source": SRC,
             "captured": "2026-10-01", "by": "2026-10-12", "default": "the east bed",
             "notes": "\nThe east bed gets the morning sun.\nMore."}))
        self.assertIn("1. Which bed first?", out)
        self.assertIn("ask from garden · overdue by 3 days against its date, 2026-10-12; "
                      "past its date, the default holds: the east bed", out)
        self.assertIn("   The east bed gets the morning sun.\n", out)
        self.assertNotIn("More.", out)

    def test_within_keeps_what_is_due_soon_or_overdue(self):
        out = self.run_on(docs({"id": "a", "what": "soon", "captured": "2026-10-01", "by": "2026-10-20"},
                               {"id": "b", "what": "far", "captured": "2026-10-01", "by": "2027-01-01"}),
                          "--within", "7")
        self.assertIn("soon", out)
        self.assertNotIn("far", out)


class Page(unittest.TestCase):
    """The page orders a dated ask as tools/next.py does, and says its default."""

    def test_rankwork_puts_a_dated_ask_in_the_second_tier_and_an_undated_one_in_canon(self):
        import re
        src = (Path(__file__).resolve().parent.parent / "web" / "cadence.html").read_text(encoding="utf-8")
        import test_gate
        body = test_gate.js_block("rankWork", src)
        self.assertRegex(body, r"if\(x\.by && !x\.answer\)\{ var st=todoStatus\(x\); due\.push")
        self.assertIn("defaultWhy(x,st)", test_gate.js_block("rankWork", src))

    def test_the_default_is_said_near_or_past_the_date(self):
        import shutil
        import test_gate
        if not shutil.which("node"):
            self.skipTest("node is absent")
        pre = ('var TODO_CADENCE=14, viewDate="2026-10-15";'
               'function addDays(d,n){var x=new Date(d+"T12:00:00Z");x.setUTCDate(x.getUTCDate()+n);return x.toISOString().slice(0,10);}'
               'function daysBetween(a,b){return Math.round((new Date(b)-new Date(a))/864e5);}'
               'function plural(n,w){return n+" "+w+(n===1?"":"s");} function words(n){return String(n);}')
        got = test_gate.run_js(["todoStatus", "todoWhy", "defaultWhy", "ownerOf"],
                               'function say(x){var st=todoStatus(x); return todoWhy(st)+defaultWhy(x,st);}'
                               'out([say({by:"2026-10-12",captured:"2026-10-01",default:"the east bed"}),'
                               'say({by:"2027-01-01",captured:"2026-10-01",default:"the east bed"})]);', pre)
        self.assertEqual(got[0], "Overdue by 3 days against its date, 2026-10-12; past its date, the default holds: the east bed")
        self.assertEqual(got[1], "Due its date, 2027-01-01")


if __name__ == "__main__":
    unittest.main()
