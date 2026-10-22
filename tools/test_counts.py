#!/usr/bin/env python3
"""The horizon counts, over the frozen Rule (tools/fixture/rule) and the frozen
record beside it (tools/fixture/record, laid out by its make.py).

    python3 -m unittest tools/test_counts.py
"""
import contextlib
import copy
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import counts  # noqa: E402
import rule  # noqa: E402
import ruledir  # noqa: E402

RECORD = ruledir.FIXTURE.parent / "record"
R, REC = counts.load(ruledir.FIXTURE, RECORD)
OUT = counts.report(R, REC, as_of="2026-10-18")
WEEK = counts.span("2026-10-11", "2026-10-17")


def again(rec):
    return counts.report(R, rec, as_of="2026-10-18")


def with_rule(**parts):
    """The frozen Rule with a part replaced: anchors, backlog."""
    r = copy.copy(R)
    for k, v in parts.items():
        setattr(r, k, v)
    return r


class Weeks(unittest.TestCase):
    def test_the_week_under_review_ended_before_the_sitting(self):
        self.assertEqual(counts.week_before("2026-10-18"), ("2026-10-11", "2026-10-17"))
        self.assertEqual(counts.week_before("2026-10-17"), ("2026-10-04", "2026-10-10"))
        self.assertEqual(counts.week_before("2026-10-21"), ("2026-10-11", "2026-10-17"))

    def test_a_week_is_named_by_its_sunday(self):
        self.assertEqual(counts.week_from("2026-10-04"), ("2026-10-04", "2026-10-10"))
        self.assertEqual(counts.week_from("20261004"), ("2026-10-04", "2026-10-10"))   # said as the record says dates
        with self.assertRaises(ValueError):
            counts.week_from("2026-10-05")

    def test_the_period_before_is_the_week_before(self):
        self.assertEqual((OUT["under_review"]["from"], OUT["under_review"]["to"]), ("2026-10-11", "2026-10-17"))
        self.assertEqual((OUT["week"]["before"]["from"], OUT["week"]["before"]["to"]), ("2026-10-04", "2026-10-10"))


class ByDay(unittest.TestCase):
    def test_a_plan_taken_held_or_was_overridden_or_not_worked(self):
        self.assertEqual(OUT["day"]["now"]["totals"],
                         {"taken": 13, "held": 11, "overridden": 1, "unworked": 1, "unanswered": 0})
        self.assertEqual(OUT["day"]["now"]["days"]["2026-10-12"],
                         {"taken": 3, "held": 2, "overridden": 1, "unworked": 0, "unanswered": 0})

    def test_a_day_the_store_lacks_is_a_gap(self):
        self.assertEqual(OUT["day"]["now"]["gaps"], ["2026-10-14"])
        self.assertNotIn("2026-10-14", OUT["day"]["now"]["days"])

    def test_a_closing_bell_with_no_record_is_unanswered_not_unworked(self):
        rec = copy.deepcopy(REC)
        d = rec[("days", "2026-10-12")]
        del d["bells"]["evening"]
        d["focus"]["focus_3"]["projects"] = []
        del d["items"]["focus_3"]
        self.assertEqual(again(rec)["day"]["now"]["days"]["2026-10-12"],
                         {"taken": 3, "held": 2, "overridden": 0, "unworked": 0, "unanswered": 1})

    def test_a_slot_ticked_by_hand_with_no_bell_is_unanswered_as_the_week_reads_it_worked(self):
        rec = copy.deepcopy(REC)
        d = rec[("days", "2026-10-12")]
        del d["bells"]["evening"]
        d["focus"]["focus_3"]["projects"] = []   # the tick stands: worked, naming no project
        out = again(rec)
        self.assertEqual(out["day"]["now"]["days"]["2026-10-12"],
                         {"taken": 3, "held": 2, "overridden": 0, "unworked": 0, "unanswered": 1})
        self.assertEqual(out["week"]["now"]["unnamed"], 1)

    def test_a_plan_that_named_an_item_held_when_the_item_was_picked(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-12")]["focus"]["focus_1"] = {"planned": "laundry", "projects": [], "undertakings": ["laundry"]}
        rec[("periodic", "laundry")] = {"id": "laundry", "project": "ordo", "cadence": 7}
        out = again(rec)
        self.assertEqual(out["day"]["now"]["days"]["2026-10-12"]["held"], 2)
        self.assertEqual(out["week"]["now"]["projects"]["ordo"]["sessions"], 4.5)   # the item's project is charged


class ByWeek(unittest.TestCase):
    def test_a_shared_slot_charges_each_project_a_share(self):
        p = OUT["week"]["now"]["projects"]
        self.assertEqual(p["nix_config"]["sessions"], 2.5)   # Monday's second slot, shared with ordo
        self.assertEqual(p["canondb"]["sessions"], 7.0)

    def test_a_meeting_spends_a_slot_of_its_project_and_the_slot_is_no_session(self):
        p = OUT["week"]["now"]["projects"]["ordo"]   # the sitting, Sunday's leisure and the trainer
        self.assertEqual((p["sessions"], p["meetings"], p["used"], p["allocation"]), (3.5, 3, 6.5, 7))
        # the page ticks a slot a meeting took; the fixture's Sundays and Saturdays do too, and no session is counted
        self.assertTrue(REC[("days", "2026-10-11")]["items"]["focus_1"])
        self.assertEqual(OUT["week"]["now"]["unnamed"], 0)

    def test_the_sessions_add_up_to_the_slots_worked(self):
        w = OUT["week"]["now"]
        self.assertEqual(w["slots_worked"], 13)
        self.assertEqual(round(sum(v["sessions"] for v in w["projects"].values()), 2), 13.0)
        self.assertEqual(w["supply"], 20)

    def test_an_undertaking_counts_for_the_project_that_owns_it(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-16")]["focus"]["focus_3"]["projects"] = []   # only the item was picked
        owned = again(rec)["week"]["now"]
        self.assertEqual((owned["projects"]["ordo"]["sessions"], owned["unplaced"]), (3.5, 0))
        del rec[("todo", "i123")]   # the export does not place it: the default project's, as the page charges it, and said
        unowned = again(rec)["week"]["now"]
        self.assertEqual((unowned["projects"]["ordo"]["sessions"], unowned["unplaced"], unowned["slots_worked"]),
                         (3.5, 1, 13))

    def test_a_frontier_question_counts_for_its_project_and_a_follow_up_for_none(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-12")]["focus"]["focus_1"] = {"planned": "canondb", "projects": [],
                                                           "undertakings": ["q:canondb:ti-esti"]}
        out = again(rec)
        self.assertEqual((out["week"]["now"]["projects"]["canondb"]["sessions"], out["week"]["now"]["unplaced"]), (7.0, 0))
        self.assertEqual(out["day"]["now"]["days"]["2026-10-12"]["held"], 2)
        rec = copy.deepcopy(REC)
        d = rec[("days", "2026-10-16")]
        d["focus"]["focus_3"] = {"planned": "ordo", "projects": [], "undertakings": ["then:i123"]}
        d["bells"]["evening"].update({"projects": [], "undertakings": ["then:i123"]})
        out = again(rec)
        self.assertEqual((out["week"]["now"]["slots_worked"], out["week"]["now"]["projects"]["ordo"]["sessions"]), (12, 2.5))
        self.assertEqual(out["day"]["now"]["days"]["2026-10-16"]["unworked"], 1)

    def test_a_project_the_docket_does_not_know_is_named_as_such(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-12")]["focus"]["focus_1"]["projects"] = ["canondb", "ghost"]
        p = again(rec)["week"]["now"]["projects"]
        self.assertEqual((p["canondb"]["sessions"], p["ghost"]["sessions"], p["ghost"]["unknown"]), (6.5, 0.5, True))

    def test_a_cancelled_meeting_spends_nothing(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-11")]["cancelled"] = {"sunday_leisure": True}
        out = again(rec)["week"]["now"]
        self.assertEqual(out["projects"]["ordo"]["meetings"], 2)
        self.assertEqual(out["cancelled"], ["sunday_leisure 2026-10-11"])

    def test_a_cancelled_mark_for_no_event_of_the_day_is_no_meeting_that_did_not_happen(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-11")]["cancelled"] = {"sunday_leisure": True, "gone_event": True}
        self.assertEqual(again(rec)["record"]["now"]["cancelled"], ["sunday_leisure 2026-10-11"])


class TheRecord(unittest.TestCase):
    def test_an_anchor_ran_when_its_bell_was_answered(self):
        self.assertEqual(OUT["record"]["now"]["anchors"]["vespers"], {"answered": 5, "expected": 6})

    def test_a_bell_the_page_withdrew_is_no_bell(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-12")]["bells"]["vespers"] = None   # a null leaf: the page removed it
        out = again(rec)
        self.assertEqual(out["record"]["now"]["anchors"]["vespers"], {"answered": 4, "expected": 6})
        self.assertEqual(out["items"]["now"]["items"]["dinner"]["unreached"], {"held": 2, "days": 3})
        self.assertEqual([w["all_answered"] for w in out["month"]["criteria"]["anchors_run"]["weeks"]], [0, 6, 6, 5, 4])

    def test_a_day_backfilled_from_memory_is_a_gap_for_the_bells_it_lacks(self):
        b = OUT["record"]["before"]
        self.assertEqual(b["anchor_gaps"], ["2026-10-09 vespers"])
        self.assertEqual(b["anchors"]["vespers"], {"answered": 5, "expected": 5})
        self.assertEqual(OUT["items"]["before"]["items"]["dinner"]["unreached"], {"held": 1, "days": 1})   # not that day

    def test_drinks_sum_the_pours(self):
        d = OUT["record"]["now"]["drinks"]
        self.assertEqual((d["drunk"], d["ration"], d["days"], d["days_over"]), (7, 8, 6, 1))
        self.assertEqual(counts.drinks_of({"drinks": 2, "pours": {"a": 1, "b": -1}}), 2)
        self.assertIsNone(counts.drinks_of({}))

    def test_resume_lines_written_and_kept_over_the_bells_that_closed_a_pick(self):
        self.assertEqual(OUT["record"]["now"]["resume_lines"],
                         {"with_line": 9, "written": 7, "kept": 2, "closed_with_pick": 12})

    def test_a_resume_line_the_page_removed_is_no_line(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-12")]["bells"]["midday"]["threads"] = {"canondb": None}   # a null leaf
        self.assertEqual(again(rec)["record"]["now"]["resume_lines"],
                         {"with_line": 8, "written": 6, "kept": 2, "closed_with_pick": 12})

    def test_bedtime_is_a_range(self):
        self.assertEqual(OUT["record"]["now"]["bedtime"], {"days": 6, "earliest": "9:55 PM", "latest": "11:20 PM"})
        self.assertEqual(rule.minutes_of("12:30 AM", 240), 24 * 60 + 30)   # before the day turns: the evening's

    def test_each_floor_item_against_its_floor(self):
        self.assertEqual(OUT["record"]["now"]["floors"], {"gym": {"ticked": 4, "floor": 3}})


class ByMonth(unittest.TestCase):
    def test_anchors_run_by_week_over_thirty_five_days(self):
        c = OUT["month"]["criteria"]["anchors_run"]
        self.assertEqual((OUT["month"]["from"], OUT["month"]["to"]), ("2026-09-13", "2026-10-17"))
        self.assertEqual([w["all_answered"] for w in c["weeks"]], [0, 6, 6, 5, 5])
        self.assertEqual([w["met"] for w in c["weeks"]], [None, True, True, None, None])
        self.assertEqual(c["weeks"][0]["days"], 0)
        self.assertEqual(c["weeks"][3]["bell_gaps"], ["2026-10-09"])   # a backfilled day lacking a bell: a gap

    def test_a_gap_is_never_a_miss(self):
        # 2026-10-04 and 2026-10-11 each have five days with every bell answered and one day the store lacks
        c = OUT["month"]["criteria"]["anchors_run"]
        self.assertIsNone(c["met"])
        self.assertEqual(c["undecided"], ["2026-10-04", "2026-10-11"])
        a = copy.deepcopy(R.anchors)
        a["commitments"].append({"id": "vac", "what": "A week away", "first": "2026-10-11", "last": "2026-10-17",
                                 "all_day": True, "keep": [], "calendar_event": "x"})
        w = counts.report(with_rule(anchors=a), REC, as_of="2026-10-18")["month"]["criteria"]["anchors_run"]["weeks"][-1]
        self.assertEqual((w["all_answered"], w["days"], len(w["whole_days"]), w["met"]), (0, 0, 6, None))

    def test_the_numbers_are_the_rules_own_words(self):
        b = copy.deepcopy(R.backlog)
        b["gate"]["criteria"]["anchors_run"] = ">=5 of 7 days, three consecutive weeks, all four bells answered"
        out = counts.report(with_rule(backlog=b), REC, as_of="2026-10-18")
        c = out["month"]["criteria"]["anchors_run"]
        self.assertEqual((out["month"]["from"], len(c["weeks"]), c["met"]), ("2026-09-20", 4, True))
        b["gate"]["criteria"]["anchors_run"] = "every bell, every day"
        c = counts.report(with_rule(backlog=b), REC, as_of="2026-10-18")["month"]["criteria"]["anchors_run"]
        self.assertIsNone(c["met"])
        self.assertIn("read at the sitting", c["note"])

    def test_rule_stable_reads_the_weekly_snapshots_rule_apart_from_the_rest(self):
        c = OUT["month"]["criteria"]["rule_stable"]
        self.assertEqual(c["snapshots"], ["2026-10-04", "2026-10-11", "2026-10-18"])
        self.assertEqual((c["weeks_unchanged"], c["met"]), (2, True))
        self.assertEqual(c["changed_elsewhere"], ["projects"])   # an allocation set at the sitting is no change proposed
        rec = copy.deepcopy(REC)
        rec[("snapshots", "2026-10-18")]["docs"] = []
        self.assertEqual(again(rec)["month"]["criteria"]["rule_stable"]["weeks_unchanged"], 0)
        del rec[("snapshots", "2026-10-04")]
        self.assertIsNone(again(rec)["month"]["criteria"]["rule_stable"]["met"])

    def test_before_its_snapshot_is_written_the_export_is_the_newest_point(self):
        rec = copy.deepcopy(REC)
        del rec[("snapshots", "2026-10-18")]
        c = again(rec)["month"]["criteria"]["rule_stable"]
        self.assertEqual(c["snapshots"], ["2026-10-04", "2026-10-11", "2026-10-18 (the export)"])
        self.assertEqual(c["weeks_unchanged"], 0)   # the frozen snapshots hold one stub document, not the Rule

    def test_a_day_after_the_snapshot_the_export_is_no_week_of_its_own(self):
        c = counts.report(R, REC, as_of="2026-10-19")["month"]["criteria"]["rule_stable"]
        self.assertEqual(c["snapshots"], ["2026-10-04", "2026-10-11", "2026-10-18"])

    def test_resume_lines_meet_the_rate_or_not_on_the_exact_ratio(self):
        c = OUT["month"]["criteria"]["resume_lines"]
        self.assertEqual((c["with_line"], c["closed_with_pick"], c["rate"], c["met"]), (49, 56, 0.88, True))
        was = counts.record_counts
        counts.record_counts = lambda *a, **k: {"resume_lines": {"with_line": 159, "written": 159, "kept": 0,
                                                                 "closed_with_pick": 200}}
        try:
            c = counts.report(R, REC, as_of="2026-10-18")["month"]["criteria"]["resume_lines"]
        finally:
            counts.record_counts = was
        self.assertEqual((c["rate"], c["met"]), (0.8, False))   # 0.795 shows as 0.8 and is under 80%

    def test_what_a_script_cannot_decide_is_read_at_the_sitting(self):
        c = OUT["month"]["criteria"]
        self.assertIsNone(c["not_in_desolation"]["met"])
        self.assertIsNone(c["slot_empty"]["met"])
        self.assertEqual(c["not_in_desolation"]["this_week"], {"all_answered": 5, "slots_worked": 13})
        self.assertEqual(c["not_in_desolation"]["weeks_before"],
                         {"all_answered_mean": 5.67, "slots_worked_mean": 14.33, "weeks": 3, "omitted": ["2026-09-13"]})
        self.assertTrue(all(x["named"] for x in c["slot_empty"]["items"]))

    def test_each_criterion_carries_what_the_rule_says(self):
        self.assertTrue(OUT["month"]["criteria"]["anchors_run"]["says"].startswith(">=6 of 7"))


class ByYear(unittest.TestCase):
    def test_each_frontier_is_read_against_the_end_its_root_states(self):
        y = OUT["year"]
        self.assertEqual(set(y), {"canondb", "ordo"})   # nix_config keeps no notebook
        self.assertTrue(y["ordo"]["end"].startswith("That what he lives match what he decided"))
        self.assertEqual((y["ordo"]["frontier"], y["ordo"]["questions"]), (1, ["ti-esti"]))


class PerItem(unittest.TestCase):
    def test_an_item_holds_or_lapses_where_its_guard_reaches_and_where_it_does_not(self):
        it = OUT["items"]["now"]["items"]
        # Tuesday's evening bell is moved by improv: dishes lapsed there, and held on every other day.
        self.assertEqual(it["dishes"], {"guard": "bell", "blocks": ["evening"],
                                        "reached": {"held": 5, "days": 5}, "unreached": {"held": 0, "days": 1}})
        # Sunday's vespers bell is moved by the game and Thursday's went unanswered.
        self.assertEqual(it["dinner"]["unreached"], {"held": 1, "days": 2})
        # dog_2 is the evening's, and the vespers' on the improv Tuesday
        self.assertEqual(it["dog_2"]["blocks"], ["evening", "vespers"])

    def test_a_conditional_item_owes_no_day(self):
        # gym is owed a floor a week (the record's floors); groceries only when the ledger says
        self.assertNotIn("gym", OUT["items"]["now"]["items"])
        rec = copy.deepcopy(REC)
        for (c, i), d in rec.items():
            if c == "days":
                d["na"].pop("groceries", None)
        self.assertNotIn("groceries", again(rec)["items"]["now"]["items"])

    def test_an_item_marked_not_applicable_is_left_out(self):
        self.assertEqual(OUT["items"]["now"]["items"]["garden"]["reached"]["days"], 4)   # Friday's na

    def test_an_item_a_todo_item_blocked_is_left_out_that_day(self):
        rec = copy.deepcopy(REC)
        rec[("todo", "i777")] = {"id": "i777", "what": "Fix the sink", "project": "ordo", "blocks": ["dishes"],
                                 "captured": "2026-10-13", "done": True, "doneAt": "2026-10-14"}
        self.assertEqual(again(rec)["items"]["now"]["items"]["dishes"]["unreached"], {"held": 0, "days": 0})

    def test_a_group_with_a_part_blocked_holds_on_its_open_parts(self):
        rec = copy.deepcopy(REC)
        rec[("todo", "i778")] = {"id": "i778", "what": "Buy oats", "project": "ordo",
                                 "blocks": ["breakfast_prepared"], "captured": "2026-10-11"}
        for d in WEEK:
            day = rec.get(("days", d))
            if day and day["items"].pop("breakfast", None):
                day["items"]["breakfast_ate"] = True   # the page ticks the open parts only
        self.assertEqual(again(rec)["items"]["now"]["items"]["breakfast"],
                         OUT["items"]["now"]["items"]["breakfast"])

    def test_a_winter_item_is_not_expected_in_winter(self):
        self.assertEqual([it["id"] for _, it in counts.Day(R.anchors, "2026-12-01").items() if it["id"] == "garden"], [])
        self.assertNotIn("garden", counts.guarded(R.anchors, counts.days_of(REC), ["2026-12-01"])["items"])
        self.assertTrue(rule.winter(R.anchors, "2026-12-01"))
        self.assertFalse(rule.winter(R.anchors, "2026-10-12"))

    def test_a_guard_of_none_reaches_no_day(self):
        a = copy.deepcopy(R.anchors)
        for an in a["anchors"].values():
            for it in an["items"]:
                if it["id"] == "dishes":
                    it["guard"] = "none"
        out = counts.guarded(a, counts.days_of(REC), WEEK)["items"]["dishes"]
        self.assertEqual((out["reached"], out["unreached"]), ({"held": 0, "days": 0}, {"held": 5, "days": 6}))

    def test_a_whole_day_fixture_is_unreached_and_keeps_only_what_it_names(self):
        a = copy.deepcopy(R.anchors)
        a["commitments"].append({"id": "sick", "what": "A sick day", "date": "2026-10-16", "all_day": True,
                                 "keep": ["meds", "dog", "examen", "sleep"], "calendar_event": "x"})
        out = counts.guarded(a, counts.days_of(REC), ["2026-10-16"])["items"]
        self.assertEqual(set(out), {"meds", "dog", "examen", "sleep"})
        self.assertEqual(out["meds"], {"guard": "bell", "blocks": ["morning"],
                                       "reached": {"held": 0, "days": 0}, "unreached": {"held": 1, "days": 1}})
        self.assertEqual(counts.Day(a, "2026-10-16").bells(), ["morning", "midday", "evening"])   # vespers keeps nothing

    def test_a_block_with_nothing_on_it_keeps_its_bell_on_a_whole_day(self):
        a = copy.deepcopy(R.anchors)
        a["anchors"]["vespers"]["items"] = [it for it in a["anchors"]["vespers"]["items"] if it["id"] == "dog_2"]
        a["commitments"].append({"id": "sick", "what": "A sick day", "date": "2026-10-16", "all_day": True,
                                 "keep": ["meds"], "calendar_event": "x"})
        self.assertIn("vespers", counts.Day(a, "2026-10-16").bells())   # dog_2 is Tuesday's there: nothing on a Friday

    def test_a_guard_not_stated_is_said_so(self):
        a = copy.deepcopy(R.anchors)
        for an in a["anchors"].values():
            for it in an["items"]:
                it.pop("guard", None)
        self.assertEqual(counts.guarded(a, counts.days_of(REC), ["2026-10-12"])["items"]["dishes"]["guard"], "not stated")


class TheDay(unittest.TestCase):
    def test_a_meeting_takes_the_slot_of_the_session_it_falls_in(self):
        self.assertEqual(counts.Day(R.anchors, "2026-10-11").meetings(R.docket),
                         [("sunday_sitting", "ordo", "focus_1"), ("sunday_leisure", "ordo", "focus_3")])
        self.assertEqual(counts.Day(R.anchors, "2026-10-17").meetings(R.docket), [("trainer", "ordo", "focus_1")])

    def test_a_meeting_is_read_on_its_own_date(self):
        # a one-off that moves a bell on another Thursday changes nothing about this one
        a = copy.deepcopy(R.anchors)
        a["commitments"].append({"id": "call", "what": "A call", "weekday": "thu", "start": "11:30", "end": "12:00",
                                 "calendar_event": "x", "project": "ordo"})
        self.assertEqual(counts.Day(a, "2026-10-15").meetings(R.docket), [])   # inside the midday Office: a fixture
        a["commitments"].append({"id": "dentist", "what": "Dentist", "date": "2026-10-29", "start": "13:00", "end": "14:00",
                                 "calendar_event": "x", "sets_anchor_bell": "midday", "derived_anchor_bell": "13:00",
                                 "derived_leave_by": "12:30"})
        self.assertEqual(counts.Day(a, "2026-10-15").meetings(R.docket), [])

    def test_a_skipped_block_closes_no_slot(self):
        a = copy.deepcopy(R.anchors)
        a["anchors"]["vespers"]["skip_weekday"] = ["fri"]
        # the vespers block does not ring, so its slot is not expected and the slot before it has no closer
        self.assertEqual(counts.Day(a, "2026-10-16").slots(), [("focus_1", "midday"), ("focus_2", None)])

    def test_a_commitment_the_rule_refuses_is_an_error_not_a_silence(self):
        a = copy.deepcopy(R.anchors)
        a["commitments"].append({"id": "bad", "what": "Both", "weekday": "mon", "date": "2026-10-12", "start": "13:00",
                                 "end": "13:30", "calendar_event": "x"})
        with self.assertRaises(rule.RuleError):
            counts.Day(a, "2026-10-12")


class Run(unittest.TestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = counts.main([str(ruledir.FIXTURE), "--record", str(RECORD), "--as-of", "2026-10-18", *args])
        return code, out.getvalue(), err.getvalue()

    def test_json_for_the_skill(self):
        code, text, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["week"]["now"]["slots_worked"], 13)

    def test_text_names_the_denominators_and_the_gaps(self):
        code, text, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("slots worked 13 of 20 · gaps: 2026-10-14", text)
        self.assertIn("vespers 5/6", text)
        self.assertIn("bells recorded later: 2026-10-09 vespers", text)
        self.assertIn("resume lines 9 of 12 (7 written, 2 kept)", text)
        self.assertIn("gym 4 of 3", text)

    def test_an_error_is_said_on_stderr_and_nothing_on_stdout(self):
        # the skill redirects stdout into counts.json, which an error must not become
        code, text, err = self.run_main("--week", "2026-10-12")
        self.assertEqual((code, text), (1, ""))
        self.assertIn("ERROR", err)

    def test_a_day_that_is_not_shaped_as_the_page_writes_it_is_named(self):
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-12")]["bells"] = "x"
        with self.assertRaisesRegex(ruledir.RuleDirError, "days/2026-10-12: bells is not a map"):
            again(rec)
        rec = copy.deepcopy(REC)
        rec[("days", "2026-10-12")]["focus"]["focus_1"] = "canondb"
        with self.assertRaisesRegex(ruledir.RuleDirError, "focus.focus_1 is not a map"):
            again(rec)

    def test_nothing_printed_is_a_verdict(self):
        _, text, _ = self.run_main()
        for word in ("good", "bad", "failed", "behind", "streak", "lapse"):
            self.assertNotIn(word, text.lower())


if __name__ == "__main__":
    unittest.main()
