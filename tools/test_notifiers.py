#!/usr/bin/env python3
"""A fixture warps the notifiers on its own dates only, and the day goes back by itself.

    python3 -m unittest tools/test_notifiers.py
"""
import io
from datetime import timedelta
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import notifiers  # noqa: E402
import rule  # noqa: E402
import os  # noqa: E402

import ruledir  # noqa: E402

# The Rule these run on is the frozen one, whatever the caller's shell exports.
os.environ[ruledir.ENV] = str(ruledir.FIXTURE)
A = ruledir.current().anchors


def run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        notifiers.main(list(argv))
    return out.getvalue()


def exceptions(text):
    part = text.split("Exceptions", 1)[1].split("What each date", 1)[0]
    return [line for line in part.splitlines() if line.startswith("| 20")]


def held(text, day):
    part = text.split("What each date", 1)[1]
    return next(line for line in part.splitlines() if line.startswith(f"| {day}"))


class Notifiers(unittest.TestCase):
    def setUp(self):
        self.mover = next((c for c in A.get("commitments") or []
                           if c.get("sets_anchor_bell") and c.get("until")), None)
        if not self.mover:
            self.skipTest("no commitment with an until: moves a bell")
        self.key = self.mover["sets_anchor_bell"]
        self.name = A["anchors"][self.key]["name"]

    def dates(self):
        """The mover's last date, and the same weekday a week after it."""
        last = rule.day_of(self.mover["until"])
        while rule.DAYS[last.weekday()] != self.mover["weekday"]:
            last -= timedelta(days=1)
        return last, last + timedelta(days=7)

    def test_no_weekday_is_left_out_for_a_fixture(self):
        series = run(str(self.dates()[0])).split("Cadence series", 1)[1].split("Exceptions", 1)[0]
        line = next(l for l in series.splitlines() if f"| {self.name} bell |" in l)
        self.assertIn("every day", line)

    def test_its_dates_cancel_the_usual_bell_and_add_the_moved_one(self):
        last, _ = self.dates()
        text = run(str(last))
        self.assertTrue(any(f"| {self.name} bell |" in l and str(last) in l for l in exceptions(text)))
        self.assertIn(f"{self.name} ({self.mover['what']}) bell", held(text, last))
        self.assertNotIn(f"{self.mover['derived_anchor_bell']} {self.name} bell", held(text, last))

    def test_after_its_until_the_day_is_back_without_a_step(self):
        _, after = self.dates()
        text = run(str(after))
        self.assertEqual([l for l in exceptions(text) if self.mover["what"] in l], [])
        self.assertIn(f"{A['anchors'][self.key]['bell']} {self.name} bell", held(text, after))
        self.assertNotIn(self.mover["what"], held(text, after))

    def test_a_cancelled_week_rings_the_usual_bell(self):
        last, _ = self.dates()
        text = run(str(last), "--cancelled", f"{self.mover['id']}:{last}")
        self.assertIn(f"{A['anchors'][self.key]['bell']} {self.name} bell", held(text, last))
        self.assertNotIn(self.mover["what"], held(text, last))

    def test_the_phone_is_told_when_its_alarms_go_back(self):
        last, after = self.dates()
        changes = lambda text: text.split("to change by hand", 1)[1]
        self.assertIn(f"tick {self.mover['weekday'].capitalize()} back",
                      changes(run(str(last - timedelta(days=7)))))
        self.assertIn("None.", changes(run(str(after + timedelta(days=21)))))


if __name__ == "__main__":
    unittest.main()
