#!/usr/bin/env python3
"""The rule that tells a meeting from a fixture, and when an event is on.

    python3 -m unittest tools/test_rule.py
"""
import copy
import sys
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


class Project(unittest.TestCase):
    DOCKET = {"projects": [{"id": "work"}, {"id": "home", "default": True}]}

    def test_a_meeting_is_its_projects_or_the_defaults(self):
        self.assertEqual(rule.project({"id": "x", "project": "work"}, self.DOCKET), "work")
        self.assertEqual(rule.project({"id": "x"}, self.DOCKET), "home")


if __name__ == "__main__":
    unittest.main()
