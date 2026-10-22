#!/usr/bin/env python3
"""The rule that tells a meeting from a fixture, when an event is on, whether an
item is on a date, and the capacity check that reads the same arithmetic.

    python3 -m unittest tools/test_rule.py
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rule  # noqa: E402

# A day small enough to read: two blocks, each an Office and a work session.
DAY = {
    "meta": {"lights_out": {"target": "22:00"}},
    "anchors": {
        "morning": {"bell": "07:00", "items": [
            {"id": "meds", "kind": "office", "minutes": 10},
            {"id": "gym", "kind": "office", "minutes": 45, "when": {"floor_per_week": 3}},
            {"id": "focus_1", "kind": "work"}]},
        "midday": {"bell": "11:00", "items": [
            {"id": "lunch", "kind": "office", "minutes": 30,
             "children": [{"id": "made", "minutes": 20}, {"id": "ate", "minutes": 10}]},
            {"id": "focus_2", "kind": "work", "skip_weekday": ["sun"]}]},
    },
    "commitments": [],
}


def day(*commitments):
    a = copy.deepcopy(DAY)
    a["commitments"] = [dict(c) for c in commitments]
    return a


def kind(a, cid):
    return rule.kind(a, next(c for c in a["commitments"] if c["id"] == cid), "2026-01-01")[0]


class Sessions(unittest.TestCase):
    def test_a_session_opens_when_the_unconditional_office_is_done(self):
        # the gym is conditional and does not delay the session
        self.assertEqual(rule.sessions(day(), "mon", []),
                         {"morning": (7 * 60 + 10, 11 * 60), "midday": (11 * 60 + 30, 22 * 60)})

    def test_a_block_with_no_work_item_that_day_has_no_session(self):
        self.assertNotIn("midday", rule.sessions(day(), "sun", []))


class Kind(unittest.TestCase):
    def test_an_event_inside_a_work_session_is_a_meeting(self):
        a = day({"id": "call", "weekday": "mon", "start": "09:00", "end": "09:45"})
        self.assertEqual(kind(a, "call"), "meeting")

    def test_one_that_reaches_into_the_office_is_a_fixture(self):
        a = day({"id": "call", "weekday": "mon", "start": "07:05", "end": "08:00"})
        self.assertEqual(kind(a, "call"), "fixture")

    def test_prep_and_the_ride_back_count(self):
        inside = {"id": "class", "weekday": "mon", "start": "09:00", "end": "09:30",
                  "travel_minutes": 10, "prep_minutes": 10, "derived_leave_by": "08:50"}
        self.assertEqual(kind(day(inside), "class"), "meeting")
        late = dict(inside, start="10:20", end="10:55", derived_leave_by="10:10")   # back at 11:05
        self.assertEqual(kind(day(late), "class"), "fixture")

    def test_one_that_crosses_a_bell_is_a_fixture(self):
        a = day({"id": "lunch_out", "weekday": "mon", "start": "10:30", "end": "11:30"})
        self.assertEqual(kind(a, "lunch_out"), "fixture")

    def test_one_that_moves_a_bell_is_a_fixture(self):
        a = day({"id": "game", "weekday": "mon", "start": "13:00", "end": "14:00",
                 "sets_anchor_bell": "midday", "derived_anchor_bell": "12:00"})
        self.assertEqual(kind(a, "game"), "fixture")

    def test_one_with_no_end_is_a_fixture(self):
        a = day({"id": "open", "weekday": "mon", "start": "09:00"})
        self.assertEqual(kind(a, "open"), "fixture")

    def test_one_in_a_block_with_no_session_that_day_is_a_fixture(self):
        a = day({"id": "call", "weekday": "sun", "start": "13:00", "end": "14:00"})
        self.assertEqual(kind(a, "call"), "fixture")

    def test_a_range_must_fit_on_every_day_it_covers(self):
        fits = {"id": "course", "first": "2026-01-05", "last": "2026-01-06", "start": "13:00", "end": "14:00"}
        self.assertEqual(kind(day(fits), "course"), "meeting")           # Monday and Tuesday
        spills = dict(fits, first="2026-01-03", last="2026-01-04")       # Saturday and Sunday
        self.assertEqual(kind(day(spills), "course"), "fixture")

    def test_a_whole_day_is_a_fixture(self):
        a = day({"id": "away", "first": "2026-01-05", "last": "2026-01-09", "all_day": True, "keep": ["meds"]})
        self.assertEqual(kind(a, "away"), "fixture")

    def test_the_office_another_fixture_adds_delays_the_session(self):
        a = day({"id": "class", "weekday": "mon", "start": "19:00", "end": "20:00",
                 "sets_anchor_bell": "midday", "derived_anchor_bell": "11:00"},
                {"id": "call", "weekday": "mon", "start": "07:15", "end": "07:45"})
        a["anchors"]["morning"]["items"].insert(1, {"id": "pack", "kind": "office", "minutes": 20,
                                                    "when": {"commitment": "class"}})
        self.assertEqual(kind(a, "call"), "fixture")       # the session opens at 07:30 on a class day


class When(unittest.TestCase):
    def test_exactly_one_way_of_saying_when(self):
        for c in ({"id": "x"}, {"id": "x", "weekday": "mon", "date": "2026-01-05"},
                  {"id": "x", "date": "2026-01-05", "first": "2026-01-05"}):
            with self.assertRaises(rule.RuleError):
                rule.when(c)

    def test_from_and_to_are_a_route_not_a_range(self):
        c = {"id": "x", "weekday": "mon", "from": "home", "to": "there"}
        self.assertEqual(rule.when(c), "weekday")

    def test_a_range_runs_forwards_and_needs_no_until(self):
        with self.assertRaises(rule.RuleError):
            rule.when({"id": "x", "first": "2026-01-06", "last": "2026-01-05"})
        with self.assertRaises(rule.RuleError):
            rule.when({"id": "x", "first": "2026-01-05", "until": "2026-02-01"})
        with self.assertRaises(rule.RuleError):
            rule.when({"id": "x", "weekday": "mon", "last": "2026-01-05"})

    def test_the_weekdays_an_event_can_fall_on(self):
        self.assertEqual(rule.weekdays({"id": "x", "weekday": "tue"}), ["tue"])
        self.assertEqual(rule.weekdays({"id": "x", "date": "2026-01-05"}), ["mon"])
        self.assertEqual(rule.weekdays({"id": "x", "first": "2026-01-09", "last": "2026-01-11"}),
                         ["fri", "sat", "sun"])
        self.assertEqual(len(rule.weekdays({"id": "x", "first": "2026-01-01", "last": "2026-03-01"})), 7)

    def test_an_event_ends_after_its_last_day(self):
        once = {"id": "x", "date": "2026-01-05"}
        self.assertFalse(rule.ended(once, "2026-01-05"))
        self.assertTrue(rule.ended(once, "2026-01-06"))
        self.assertTrue(rule.ended({"id": "x", "first": "2026-01-01", "last": "2026-01-03"}, "2026-01-04"))
        self.assertTrue(rule.ended({"id": "x", "weekday": "mon", "until": "2026-01-03"}, "2026-01-04"))
        self.assertFalse(rule.ended({"id": "x", "weekday": "mon"}, "2099-01-01"))

    def test_a_whole_day_fixture_takes_no_part_in_a_days_arithmetic(self):
        a = day({"id": "away", "first": "2026-01-05", "last": "2026-01-09", "all_day": True, "keep": []},
                {"id": "call", "weekday": "mon", "start": "09:00", "end": "09:45"})
        self.assertEqual([c["id"] for c in rule.on_weekday(a, "mon", "2026-01-01")], ["call"])


class Today(unittest.TestCase):
    """Today has one definition, the Rule's clock: meta.timezone, turning at
    meta.day_starts and not at midnight."""
    A = {"meta": {"timezone": "America/New_York", "day_starts": "04:00"}}

    def test_the_date_is_the_rules_zone_not_utc(self):
        # 03:30 UTC on the 16th is 23:30 on the 15th in New York
        self.assertEqual(rule.today(self.A, "2026-10-16T03:30:00Z"), "2026-10-15")

    def test_the_day_turns_at_day_starts(self):
        self.assertEqual(rule.today(self.A, "2026-10-16T03:59:00-04:00"), "2026-10-15")
        self.assertEqual(rule.today(self.A, "2026-10-16T04:00:00-04:00"), "2026-10-16")

    def test_the_time_now_is_written_as_the_page_writes_one(self):
        self.assertEqual(rule.now_text(self.A, "2026-10-16T13:05:00-04:00"), "1:05 PM")
        self.assertEqual(rule.now_text(self.A, "2026-10-16T00:30:00-04:00"), "12:30 AM")

    def test_a_series_ended_is_read_against_the_rules_today(self):
        a = dict(self.A, commitments=[{"id": "c", "weekday": "thu", "until": "2026-10-15",
                                       "start": "10:00", "end": "11:00"}])
        # at 23:30 New York on the 15th the series is still on; the machine's UTC date is the 16th
        self.assertEqual([c["id"] for c in rule.on_weekday(a, "thu", today=rule.today(a, "2026-10-16T03:30:00Z"))], ["c"])
        self.assertEqual(rule.on_weekday(a, "thu", today="2026-10-16"), [])


def wintry(*commitments):
    """DAY with a winter, and a morning walk the winter takes away."""
    a = day(*commitments)
    a["meta"]["winter"] = {"start": "12-01", "end": "02-28"}
    a["anchors"]["morning"]["items"].insert(1, {"id": "walk", "kind": "office", "minutes": 30,
                                                "when": {"not_winter": True}})
    return a


class ItemOn(unittest.TestCase):
    """One reading of whether an item is on a date, for every caller that has one."""

    def test_an_item_off_in_winter_is_off_on_a_winter_date(self):
        a = wintry()
        walk = a["anchors"]["morning"]["items"][1]
        self.assertTrue(rule.item_on(a, walk, "2026-10-05"))
        self.assertFalse(rule.item_on(a, walk, "2026-01-05"))
        self.assertIn("winter", rule.why_not(a, walk, "2026-01-05"))

    def test_its_weekdays_and_its_blocks(self):
        a = day()
        focus_2 = a["anchors"]["midday"]["items"][1]
        self.assertFalse(rule.item_on(a, focus_2, "2026-01-04"))          # a Sunday
        a["anchors"]["midday"]["skip_weekday"] = ["mon"]
        lunch = a["anchors"]["midday"]["items"][0]
        self.assertTrue(rule.item_on(a, lunch, "2026-01-05"))
        self.assertFalse(rule.item_on(a, lunch, "2026-01-05", key="midday"))

    def test_an_item_a_fixture_causes_follows_the_fixtures_dates(self):
        a = day({"id": "class", "date": "2026-01-05", "start": "19:00", "end": "20:00"})
        pack = {"id": "pack", "kind": "office", "minutes": 10, "when": {"commitment": "class"}}
        self.assertTrue(rule.item_on(a, pack, "2026-01-05"))
        self.assertFalse(rule.item_on(a, pack, "2026-01-12"))
        self.assertFalse(rule.item_on(a, dict(pack, when={}, unless={"commitment": "class"}), "2026-01-05"))

    def test_a_whole_day_keeps_an_item_or_a_part_of_one(self):
        a = day({"id": "away", "first": "2026-01-05", "last": "2026-01-09", "all_day": True, "keep": ["made"]})
        lunch, meds = a["anchors"]["midday"]["items"][0], a["anchors"]["morning"]["items"][0]
        self.assertFalse(rule.item_on(a, meds, "2026-01-05"))
        self.assertTrue(rule.item_on(a, meds, "2026-01-10"))
        self.assertTrue(rule.item_on(a, lunch, "2026-01-05", part="made"))
        self.assertFalse(rule.item_on(a, lunch, "2026-01-05", part="ate"))
        # read without its whole days, for the day's arithmetic
        self.assertTrue(rule.item_on(a, meds, "2026-01-05", cs=[]))

    def test_the_session_of_a_winter_date_opens_without_the_winter_items(self):
        a = wintry()
        self.assertEqual(rule.sessions(a, "mon", [], "2026-10-05")["morning"][0], 7 * 60 + 40)
        self.assertEqual(rule.sessions(a, "mon", [], "2026-01-05")["morning"][0], 7 * 60 + 10)
        # read by weekday alone, outside winter: the longer Office
        self.assertEqual(rule.sessions(a, "mon", [])["morning"][0], 7 * 60 + 40)

    def test_a_meeting_is_read_in_the_season_of_its_dates(self):
        call = {"id": "call", "date": "2026-01-05", "start": "07:15", "end": "07:30"}
        self.assertEqual(kind(wintry(call), "call"), "meeting")           # the walk is off in winter
        weekly = dict(call, weekday="mon")
        del weekly["date"]
        self.assertEqual(kind(wintry(weekly), "call"), "fixture")         # but not in October


class PastMidnight(unittest.TestCase):
    """An end before its start runs past midnight; the day's minutes run on past 1440."""

    def test_an_end_before_its_start_is_the_next_morning(self):
        self.assertEqual(rule.busy({"id": "x", "start": "19:00", "end": "00:30"}), (19 * 60, 24 * 60 + 30))

    def test_an_end_at_its_start_is_refused(self):
        with self.assertRaises(rule.RuleError):
            rule.busy({"id": "x", "start": "19:00", "end": "19:00"})

    def test_one_that_runs_past_midnight_is_no_meeting_of_the_afternoon(self):
        a = day({"id": "late", "weekday": "mon", "start": "19:00", "end": "00:30"})
        self.assertEqual(kind(a, "late"), "fixture")


class Bells(unittest.TestCase):
    def test_of_two_events_moving_one_bell_the_first_to_start_moves_it(self):
        # the page's bellOf reads its events sorted by start
        late = {"id": "late", "start": "21:00", "sets_anchor_bell": "midday", "derived_anchor_bell": "20:30"}
        early = {"id": "early", "start": "13:00", "sets_anchor_bell": "midday", "derived_anchor_bell": "12:00"}
        self.assertEqual(rule.bell(DAY, "midday", [late, early]), 12 * 60)

    def test_every_distinct_day_is_read_on_a_date_of_its_own(self):
        a = day({"id": "series", "weekday": "tue", "until": "2026-01-13", "start": "09:00", "end": "09:30"},
                {"id": "once", "date": "2026-01-20", "start": "13:00", "end": "13:30"})
        tue = [(d, sorted(c["id"] for c in cs)) for d, cs in rule.variants(a, "2026-01-01")
               if rule.weekday_of(d) == "tue"]
        self.assertEqual(tue, [("2026-01-06", ["series"]), ("2026-01-20", ["once"]), ("2026-01-27", [])])


class Takes(unittest.TestCase):
    """A meeting carries the session it spends, by weekday, as the work item's id."""

    def test_a_meeting_takes_its_blocks_work_item(self):
        a = day({"id": "call", "weekday": "mon", "start": "09:00", "end": "09:45"},
                {"id": "course", "first": "2026-01-05", "last": "2026-01-06", "start": "13:00", "end": "14:00"})
        self.assertEqual(rule.takes(a, a["commitments"][0], "2026-01-01"), {"mon": "focus_1"})
        self.assertEqual(rule.takes(a, a["commitments"][1], "2026-01-01"), {"mon": "focus_2", "tue": "focus_2"})

    def test_a_fixture_takes_nothing(self):
        a = day({"id": "open", "weekday": "mon", "start": "09:00"})
        self.assertIsNone(rule.takes(a, a["commitments"][0], "2026-01-01"))

    def test_the_compiler_carries_it_on_each_meeting(self):
        import compiler
        import ruledir
        compiler.errors.clear()
        out = compiler.compile(ruledir.load(ruledir.FIXTURE))
        self.assertEqual(compiler.errors, [])
        by = {c["id"]: c for c in out["COMMITMENTS"]}
        self.assertEqual(by["sunday_sitting"]["takes"], {"sun": "focus_1"})
        self.assertEqual(by["sunday_leisure"]["takes"], {"sun": "focus_3"})
        self.assertNotIn("takes", by["improv"])


class Capacity(unittest.TestCase):
    """tools/check_capacity.py over the frozen Rule with one event added, as the
    gate runs it."""
    TOOLS = Path(__file__).resolve().parent

    def run_with(self, c):
        with tempfile.TemporaryDirectory() as t:
            shutil.copytree(self.TOOLS / "fixture" / "rule", t, dirs_exist_ok=True)
            Path(t, "commitments", c["id"] + ".json").write_text(json.dumps(dict(c, seq=99)))
            return subprocess.run([sys.executable, "-B", str(self.TOOLS / "check_capacity.py"),
                                   "--today", "2026-10-22"],
                                  env=dict(os.environ, ORDO_RULE=t), capture_output=True, text=True)

    def test_the_frozen_rule_fits(self):
        with tempfile.TemporaryDirectory() as t:
            p = subprocess.run([sys.executable, "-B", str(self.TOOLS / "check_capacity.py"), "--today", "2026-10-22"],
                               env=dict(os.environ, ORDO_RULE=str(self.TOOLS / "fixture" / "rule")),
                               capture_output=True, text=True, cwd=t)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("(2026-12-22: no improv, winter)", p.stdout)       # the evening without improv, in winter

    def test_an_event_past_midnight_takes_the_rest_of_its_block(self):
        p = self.run_with({"id": "late", "weekday": "mon", "start": "21:00", "end": "00:30",
                           "calendar_event": "e", "what": "x"})
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("mon evening (2026-10-26): Office needs 70 min, block has 60", p.stdout)
        self.assertIn("late              fixture", p.stdout)

    def test_a_second_event_moving_a_bell_is_checked_on_its_own_date(self):
        # improv moves the evening bell on Tuesdays until 2026-12-15; this moves it on
        # a later Tuesday, to leave a 30-minute evening
        p = self.run_with({"id": "late_show", "date": "2026-12-22", "start": "22:00", "end": "23:00",
                           "sets_anchor_bell": "evening", "derived_anchor_bell": "21:30",
                           "calendar_event": "e", "what": "x"})
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("tue evening (2026-12-22: no improv, winter): Office needs 65 min, block has 30", p.stdout)


class Project(unittest.TestCase):
    DOCKET = {"projects": [{"id": "work"}, {"id": "home", "default": True}]}

    def test_a_meeting_is_its_projects_or_the_defaults(self):
        self.assertEqual(rule.project({"id": "x", "project": "work"}, self.DOCKET), "work")
        self.assertEqual(rule.project({"id": "x"}, self.DOCKET), "home")


if __name__ == "__main__":
    unittest.main()
