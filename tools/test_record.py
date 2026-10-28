#!/usr/bin/env python3
"""The record gate: what it writes for each fact, and what it refuses.

Run on the frozen Rule (tools/fixture/rule) with a small record beside it. The
clock is pinned: NOW is 08:00 on Thursday 2026-10-15 in New York.

    python3 -m unittest tools/test_record.py
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate  # noqa: E402
import items  # noqa: E402
import record  # noqa: E402
import ruledir  # noqa: E402

NOW = "2026-10-15T12:00:00Z"
TODAY = "2026-10-15"            # a Thursday
RULE = ruledir.read(ruledir.FIXTURE)


def export(**extra):
    """The Rule plus the record documents a test gives, keyed 'collection/id'."""
    docs = dict(RULE)
    for key, data in extra.items():
        c, i = key.split("/", 1)
        docs[(c, i)] = data
    return docs


def gated(docs, *facts, now=NOW):
    rec = record.run(docs, list(facts), now)
    return {"/".join(k): (op, data) for op, k, data in rec.writes_out()}, rec.said


class Clock(unittest.TestCase):
    def test_today_is_the_rules_clock(self):
        rec = record.run(export(), [], "2026-10-16T03:30:00Z")   # 23:30 on the 15th in New York
        self.assertEqual(rec.today, "2026-10-15")

    def test_a_date_after_today_is_refused_not_moved(self):
        with self.assertRaisesRegex(record.Refused, "after today"):
            gated(export(), {"fact": "tick", "date": "2026-10-16", "item": "brush"})
        with self.assertRaisesRegex(record.Refused, "not a date"):
            gated(export(), {"fact": "tick", "date": "15/10/2026", "item": "brush"})


class Ticks(unittest.TestCase):
    def test_a_group_is_written_as_its_parts_with_the_time_now_today(self):
        w, _ = gated(export(), {"fact": "tick", "date": TODAY, "item": "teeth"})
        op, d = w["days/" + TODAY]
        self.assertEqual(op, "set")
        self.assertEqual(d["items"], {"brush": True, "floss": True, "rinse": True})
        self.assertEqual(d["times"], {"brush": "8:00 AM", "floss": "8:00 AM", "rinse": "8:00 AM"})
        self.assertEqual(d["date"], TODAY)
        self.assertNotIn("backfilled", d)
        self.assertEqual(sorted(d), sorted(record.blank(TODAY)) + [])

    def test_a_day_the_store_holds_is_updated_with_the_leaves_only(self):
        docs = export(**{"days/" + TODAY: {"date": TODAY, "items": {"meds": True}, "times": {"brush": "7:50 AM"}}})
        w, _ = gated(docs, {"fact": "tick", "date": TODAY, "item": "brush"})
        self.assertEqual(w["days/" + TODAY], ("update", {"date": TODAY, "items": {"brush": True}}))

    def test_a_past_day_takes_no_time_and_is_backfilled(self):
        w, _ = gated(export(), {"fact": "tick", "date": "2026-10-13", "item": "trash"})   # a Tuesday
        op, d = w["days/2026-10-13"]
        self.assertEqual((op, d["items"], d.get("times"), d.get("backfilled")), ("set", {"trash": True}, {}, True))

    def test_a_given_time_is_written_as_given(self):
        w, _ = gated(export(), {"fact": "tick", "date": TODAY, "item": "brush", "time": "9:40 AM"})
        self.assertEqual(w["days/" + TODAY][1]["times"], {"brush": "9:40 AM"})
        with self.assertRaisesRegex(record.Refused, "9:40 AM"):
            gated(export(), {"fact": "tick", "date": TODAY, "item": "brush", "time": "09:40"})

    def test_an_item_not_on_that_date(self):
        with self.assertRaisesRegex(record.Refused, "trash is not on"):            # Tuesdays only
            gated(export(), {"fact": "tick", "date": TODAY, "item": "trash"})
        with self.assertRaisesRegex(record.Refused, "gym is not on"):              # skip_weekday sun
            gated(export(), {"fact": "tick", "date": "2026-10-11", "item": "gym"})
        with self.assertRaisesRegex(record.Refused, "off in winter"):
            gated(export(), {"fact": "tick", "date": "2026-11-20", "item": "garden"}, now="2026-12-01T12:00:00Z")
        w, _ = gated(export(), {"fact": "tick", "date": TODAY, "item": "garden"})
        self.assertIn("garden", w["days/" + TODAY][1]["items"])

    def test_an_item_a_fixture_causes_is_on_the_fixtures_days_only(self):
        # dog_2 is in vespers on improv's days (Tuesday) and in the evening otherwise;
        # either way it is on, so the tick is taken; freshen_up is improv's alone
        for d in ("2026-10-13", TODAY):
            w, _ = gated(export(), {"fact": "tick", "date": d, "item": "dog_2"})
            self.assertIn("dog_2", w["days/" + d][1]["items"])
        w, _ = gated(export(), {"fact": "tick", "date": "2026-10-13", "item": "freshen_up"})
        self.assertIn("freshen_up", w["days/2026-10-13"][1]["items"])
        with self.assertRaisesRegex(record.Refused, "freshen_up is not on"):
            gated(export(), {"fact": "tick", "date": TODAY, "item": "freshen_up"})

    def test_the_examen_is_answered_on_the_page(self):
        with self.assertRaisesRegex(record.Refused, "Examen"):
            gated(export(), {"fact": "tick", "date": TODAY, "item": "examen"})

    def test_meds_and_the_weigh_in(self):
        w, _ = gated(export(), {"fact": "tick", "date": TODAY, "item": "meds"})
        self.assertIs(w["days/" + TODAY][1]["meds"], True)
        w, _ = gated(export(), {"fact": "tick", "date": TODAY, "item": "weight", "weight": 181.26})
        self.assertEqual(w["days/" + TODAY][1]["weight"], 181.3)
        w, _ = gated(export(), {"fact": "tick", "date": TODAY, "item": "weight", "weight": 150.25})
        self.assertEqual(w["days/" + TODAY][1]["weight"], 150.3)   # half up, as the page rounds
        with self.assertRaisesRegex(record.Refused, "needs the number"):
            gated(export(), {"fact": "tick", "date": TODAY, "item": "weight"})

    def test_a_not_needed_mark_is_cleared(self):
        docs = export(**{"days/" + TODAY: {"date": TODAY, "na": {"brush": True, "teeth": True}}})
        w, _ = gated(docs, {"fact": "tick", "date": TODAY, "item": "brush"})
        self.assertEqual(w["days/" + TODAY][1]["na"], {"brush": None, "teeth": None})

    def test_an_unknown_item(self):
        with self.assertRaisesRegex(record.Refused, "not an item of rule/office"):
            gated(export(), {"fact": "tick", "date": TODAY, "item": "nap"})


class Blocked(unittest.TestCase):
    WASHER = {"id": "i1", "project": "ordo", "what": "Fix the washer", "blocks": ["gym"],
              "captured": "2026-10-10", "at": "2026-10-10T10:00:00Z"}

    def test_an_open_blocker_refuses_the_tick(self):
        with self.assertRaisesRegex(record.Refused, "blocked, not missed"):
            gated(export(**{"todo/i1": self.WASHER}), {"fact": "tick", "date": TODAY, "item": "gym"})

    def test_a_lone_id_an_older_writer_left_in_blocks_blocks_too(self):
        lone = dict(self.WASHER, blocks="gym")   # read as the page and the counts read it (items.blocks_of)
        with self.assertRaisesRegex(record.Refused, "blocked, not missed"):
            gated(export(**{"todo/i1": lone}), {"fact": "tick", "date": TODAY, "item": "gym"})

    def test_blocked_on_that_day_not_today(self):
        shut = dict(self.WASHER, done=True, doneAt="2026-10-13")
        # closed on the 13th: the 15th is free, the 11th was blocked
        w, _ = gated(export(**{"todo/i1": shut}), {"fact": "tick", "date": TODAY, "item": "gym"})
        self.assertIn("gym", w["days/" + TODAY][1]["items"])
        with self.assertRaisesRegex(record.Refused, "blocked"):
            gated(export(**{"todo/i1": shut}), {"fact": "tick", "date": "2026-10-13", "item": "gym"})   # a Tuesday
        # captured after the day: it did not block it
        later = dict(self.WASHER, captured="2026-10-14")
        w, _ = gated(export(**{"todo/i1": later}), {"fact": "tick", "date": "2026-10-13", "item": "gym"})
        self.assertIn("gym", w["days/2026-10-13"][1]["items"])

    def test_a_blocked_part_is_left_out_and_the_rest_written(self):
        groceries = dict(self.WASHER, id="i2", what="No groceries", blocks=["breakfast_prepared"])
        w, said = gated(export(**{"todo/i2": groceries}), {"fact": "tick", "date": TODAY, "item": "breakfast"})
        self.assertEqual(w["days/" + TODAY][1]["items"], {"breakfast_ate": True})
        self.assertTrue(any("breakfast_prepared" in s for s in said))


class Pours(unittest.TestCase):
    def test_a_pour_under_its_key(self):
        w, _ = gated(export(), {"fact": "pour", "date": "2026-10-14", "n": 2, "key": "pour 2026-10-14, told at the 2026-10-15 sync"})
        op, d = w["days/2026-10-14"]
        self.assertEqual(d["pours"], {"b:pour 2026-10-14, told at the 2026-10-15 sync": 2})
        self.assertIs(d["backfilled"], True)

    def test_the_bounds(self):
        for n in (0, 11, -11, "2"):
            with self.assertRaisesRegex(record.Refused, "whole number"):
                gated(export(), {"fact": "pour", "date": TODAY, "n": n, "key": "k"})
        with self.assertRaisesRegex(record.Refused, "needs its key"):
            gated(export(), {"fact": "pour", "date": TODAY, "n": 1, "key": " "})

    def test_the_same_fact_is_the_same_leaf(self):
        docs = export(**{"days/" + TODAY: {"date": TODAY, "pours": {"b:k": 2}}})
        w, said = gated(docs, {"fact": "pour", "date": TODAY, "n": 2, "key": "k"})
        self.assertEqual(w, {})
        self.assertTrue(said)
        with self.assertRaisesRegex(record.Refused, "second number"):
            gated(docs, {"fact": "pour", "date": TODAY, "n": 3, "key": "k"})

    def test_a_correction_no_deeper_than_the_day_holds(self):
        docs = export(**{"days/" + TODAY: {"date": TODAY, "drinks": 1, "pours": {"b:k": 1}}})
        w, _ = gated(docs, {"fact": "pour", "date": TODAY, "n": -2, "key": "took two off"})
        self.assertEqual(w["days/" + TODAY], ("update", {"date": TODAY, "pours": {"b:took two off": -2}}))
        with self.assertRaisesRegex(record.Refused, "more than that"):
            gated(docs, {"fact": "pour", "date": TODAY, "n": -3, "key": "took three off"})


class Items(unittest.TestCase):
    def test_a_todo_item_captured(self):
        doc = {"id": "iabc", "what": "Call the plumber", "blocks": ["laundry"], "next": "find the number"}
        docs = export(**{"periodic/laundry": {"id": "laundry", "what": "Laundry", "cadence": 7, "project": "ordo"}})
        w, _ = gated(docs, {"fact": "todo", "doc": doc})
        op, d = w["todo/iabc"]
        self.assertEqual(op, "set")
        self.assertEqual((d["project"], d["captured"], d["blocks"]), ("ordo", TODAY, ["laundry"]))
        self.assertEqual(d["at"], "2026-10-15T12:00:00Z")
        self.assertEqual(d["nextAt"], d["at"])

    def test_what_a_todo_item_may_name(self):
        with self.assertRaisesRegex(record.Refused, "not an active project"):
            gated(export(), {"fact": "todo", "doc": {"id": "i1", "what": "x", "project": "CanonDB"}})
        with self.assertRaisesRegex(record.Refused, "does not carry"):
            gated(export(), {"fact": "todo", "doc": {"id": "i1", "what": "x", "blocks": ["haircut"]}})
        with self.assertRaisesRegex(record.Refused, "list of ids"):
            gated(export(), {"fact": "todo", "doc": {"id": "i1", "what": "x", "blocks": "gym"}})
        w, _ = gated(export(), {"fact": "todo", "doc": {"id": "i1", "what": "x", "blocks": ["gym", "improv", "q:canondb:priority"]}})
        self.assertIn("todo/i1", w)
        with self.assertRaisesRegex(record.Refused, "not a date"):
            gated(export(), {"fact": "todo", "doc": {"id": "i1", "what": "x", "by": "2026-11-10T00:00:00Z"}})

    def test_an_item_the_store_holds_is_updated(self):
        docs = export(**{"todo/i1": {"id": "i1", "what": "x", "project": "ordo", "captured": "2026-10-01"}})
        w, _ = gated(docs, {"fact": "todo", "doc": {"id": "i1", "what": "x", "next": "step two"}})
        op, d = w["todo/i1"]
        self.assertEqual(op, "update")
        self.assertNotIn("captured", d)

    def test_a_periodic_items_shape(self):
        with self.assertRaisesRegex(record.Refused, "cadence"):
            gated(export(), {"fact": "periodic", "doc": {"id": "p1", "what": "Haircut", "cadence": "21"}})
        with self.assertRaisesRegex(record.Refused, "then is"):
            gated(export(), {"fact": "periodic", "doc": {"id": "p1", "what": "Laundry", "cadence": 7, "then": {"sessions": 2}}})
        w, _ = gated(export(), {"fact": "periodic", "doc": {"id": "p1", "what": "Laundry", "cadence": 7,
                                                            "then": {"what": "Rotate the laundry", "sessions": 2}}})
        self.assertEqual(w["periodic/p1"][0], "set")

    def test_a_periodic_done_in_chat_is_as_the_card_would_write_it(self):
        laundry = {"id": "laundry", "what": "Laundry", "cadence": 7, "project": "ordo",
                   "then": {"what": "Rotate the laundry", "sessions": 2}}
        docs = export(**{"periodic/laundry": laundry})
        with self.assertRaisesRegex(record.Refused, "needs focus"):
            gated(docs, {"fact": "periodic-done", "id": "laundry"})
        w, _ = gated(docs, {"fact": "periodic-done", "id": "laundry", "focus": "focus_2"})
        self.assertEqual(w["periodic/laundry"][1], {"id": "laundry", "history": {TODAY: True}, "due": None,
                                                    "at": "2026-10-15T12:00:00Z",
                                                    "started": {"date": TODAY, "focus": "focus_2"}})
        w, _ = gated(docs, {"fact": "periodic-done", "id": "laundry", "date": "2026-10-13"})
        self.assertNotIn("started", w["periodic/laundry"][1])
        older = export(**{"periodic/laundry": dict(laundry, history=["2026-10-01"])})
        w, _ = gated(older, {"fact": "periodic-done", "id": "laundry", "date": "2026-10-13"})
        self.assertEqual(w["periodic/laundry"][1]["history"], {"2026-10-01": True, "2026-10-13": True})

    def test_close_and_restore(self):
        docs = export(**{"todo/i1": {"id": "i1", "what": "x", "project": "ordo"},
                         "breakdowns/i1": {"open": True}})
        w, _ = gated(docs, {"fact": "close", "id": "i1", "date": "2026-10-14"})
        self.assertEqual(w["todo/i1"], ("update", {"id": "i1", "done": True, "doneAt": "2026-10-14", "at": "2026-10-15T12:00:00Z"}))
        self.assertEqual(w["breakdowns/i1"], ("update", {"open": False, "closed": "2026-10-14"}))
        done = export(**{"todo/i1": {"id": "i1", "what": "x", "done": True, "doneAt": "2026-10-01"}})
        w, said = gated(done, {"fact": "close", "id": "i1"})
        self.assertEqual((w, bool(said)), ({}, True))
        # done and not removed: a restore is only of a Remove not meant, so it is left as it is
        w, said = gated(done, {"fact": "restore", "collection": "todo", "id": "i1"})
        self.assertEqual(w, {})
        self.assertTrue(any("not removed" in x for x in said))
        removed = export(**{"todo/i1": {"id": "i1", "what": "x", "done": True, "doneAt": "2026-10-01", "removed": True}})
        w, _ = gated(removed, {"fact": "restore", "collection": "todo", "id": "i1"})
        self.assertEqual(w["todo/i1"][1], {"id": "i1", "removed": False, "at": "2026-10-15T12:00:00Z", "done": False,
                                           "doneAt": None})
        w, _ = gated(export(**{"periodic/p1": {"id": "p1", "what": "x", "cadence": 7, "removed": True}}),
                     {"fact": "restore", "collection": "periodic", "id": "p1"})
        self.assertEqual(w["periodic/p1"][1], {"id": "p1", "removed": False, "at": "2026-10-15T12:00:00Z"})
        with self.assertRaisesRegex(record.Refused, "not in the export"):
            gated(export(), {"fact": "close", "id": "nobody"})

    def test_a_dictation_is_never_closed_here(self):
        docs = export(**{"todo/d1": {"id": "d1", "what": "x", "project": "ordo", "kind": "dictation"}})
        with self.assertRaisesRegex(record.Refused, "dictation, never closed here"):
            gated(docs, {"fact": "close", "id": "d1"})

    def test_an_owned_item_carries_its_source_and_is_closed_by_its_owner(self):
        src = {"owner": "garden", "url": "https://github.com/natb1/garden/blob/main/plan/beds.toml"}
        with self.assertRaisesRegex(record.Refused, "written by its owner"):
            gated(export(), {"fact": "todo", "doc": {"id": "garden-beds_2026", "what": "Plant the beds", "source": src}})
        docs = export(**{"todo/garden-beds_2026": {"id": "garden-beds_2026", "what": "Plant the beds", "project": "ordo",
                                                   "source": src}})
        with self.assertRaisesRegex(record.Refused, "its owner closes it"):
            gated(docs, {"fact": "close", "id": "garden-beds_2026"})
        # a run writes only its next step; an owner's close it already made is said, not refused
        with self.assertRaisesRegex(record.Refused, "only its next step"):
            gated(docs, {"fact": "todo", "doc": {"id": "garden-beds_2026", "what": "Plant the beds", "done": True}})
        w, _ = gated(docs, {"fact": "todo", "doc": {"id": "garden-beds_2026", "next": "open the seed catalogue"}})
        self.assertEqual(w["todo/garden-beds_2026"][1]["next"], "open the seed catalogue")
        self.assertNotIn("project", w["todo/garden-beds_2026"][1])   # merged: the held project stands
        done = export(**{"todo/garden-beds_2026": dict(docs[("todo", "garden-beds_2026")], done=True, doneAt="2026-10-14")})
        w, said = gated(done, {"fact": "close", "id": "garden-beds_2026"})
        self.assertEqual((w, bool(said)), ({}, True))


class Asks(unittest.TestCase):
    """An ask (hypomnemata › kinds): the sync writes the notebook's as owner `notebook`,
    an answer said in chat is the answer fact, and the owner closes it."""
    SRC = {"owner": "notebook", "url": "https://claude.ai/artifact/x#tab"}

    def ask(self, **more):
        return dict({"id": "notebook-ordo-ti-esti", "what": "What is a rule?", "kind": "ask", "project": "ordo",
                     "captured": "2026-10-10", "asked": "2026-10-10", "source": self.SRC}, **more)

    def test_a_run_writes_an_owners_ask_only_as_that_owner(self):
        doc = {"id": "notebook-ordo-ti-esti", "what": "What is a rule?", "kind": "ask", "asked": TODAY, "source": self.SRC}
        with self.assertRaisesRegex(record.Refused, "written by its owner"):
            gated(export(), {"fact": "todo", "doc": doc})
        with self.assertRaisesRegex(record.Refused, "short id"):
            gated(export(), {"fact": "todo", "doc": doc, "owner": 7})
        with self.assertRaisesRegex(record.Refused, "writes its own source"):
            gated(export(), {"fact": "todo", "doc": dict(doc, id="ledger-ask"), "owner": "ledger"})
        w, _ = gated(export(), {"fact": "todo", "doc": doc, "owner": "notebook"})
        op, d = w["todo/notebook-ordo-ti-esti"]
        self.assertEqual((op, d["kind"], d["captured"], d["source"]), ("set", "ask", TODAY, self.SRC))
        # a re-run is an update under the protocol, and the kind is never written again
        docs = export(**{"todo/notebook-ordo-ti-esti": self.ask()})
        w, _ = gated(docs, {"fact": "todo", "doc": {"id": "notebook-ordo-ti-esti", "source": self.SRC, "what": "What is a rule, asked again?"},
                            "owner": "notebook"})
        self.assertEqual(w["todo/notebook-ordo-ti-esti"][0], "update")
        with self.assertRaisesRegex(record.Refused, "the answer is the user's"):
            gated(docs, {"fact": "todo", "doc": {"id": "notebook-ordo-ti-esti", "source": self.SRC, "answer": "x"}, "owner": "notebook"})

    def test_an_answer_said_in_chat_is_written_as_the_page_writes_one(self):
        docs = export(**{"todo/notebook-ordo-ti-esti": self.ask()})
        w, _ = gated(docs, {"fact": "answer", "id": "notebook-ordo-ti-esti", "text": " A trellis. "})
        op, d = w["todo/notebook-ordo-ti-esti"]
        self.assertEqual((op, d["answer"], d["answeredAt"]), ("update", "A trellis.", NOW))
        with self.assertRaisesRegex(record.Refused, "carries text"):
            gated(docs, {"fact": "answer", "id": "notebook-ordo-ti-esti", "text": ""})
        with self.assertRaisesRegex(record.Refused, "not in the export"):
            gated(docs, {"fact": "answer", "id": "nope", "text": "x"})
        plain = export(**{"todo/i1": {"id": "i1", "what": "x", "project": "ordo"}})
        with self.assertRaisesRegex(record.Refused, "only an ask takes an answer"):
            gated(plain, {"fact": "answer", "id": "i1", "text": "x"})
        shut = export(**{"todo/notebook-ordo-ti-esti": self.ask(done=True, doneAt="2026-10-14")})
        with self.assertRaisesRegex(record.Refused, "is closed"):
            gated(shut, {"fact": "answer", "id": "notebook-ordo-ti-esti", "text": "x"})

    def test_the_owner_closes_an_answered_ask_and_nobody_else_does(self):
        docs = export(**{"todo/notebook-ordo-ti-esti": self.ask(answer="A trellis.", answeredAt=NOW)})
        with self.assertRaisesRegex(record.Refused, "its owner closes it"):
            gated(docs, {"fact": "close", "id": "notebook-ordo-ti-esti"})
        with self.assertRaisesRegex(record.Refused, "its owner closes it"):
            gated(docs, {"fact": "close", "id": "notebook-ordo-ti-esti", "owner": "ledger"})
        w, _ = gated(docs, {"fact": "close", "id": "notebook-ordo-ti-esti", "owner": "notebook"})
        self.assertEqual(w["todo/notebook-ordo-ti-esti"][1]["doneAt"], TODAY)


class Batch(unittest.TestCase):
    """Each fact is checked against the record as the facts before it leave it."""

    def test_one_key_takes_one_number_across_the_batch(self):
        k = {"fact": "pour", "date": TODAY, "key": "k"}
        with self.assertRaisesRegex(record.Refused, "second number"):
            gated(export(), dict(k, n=2), dict(k, n=3))
        w, said = gated(export(), dict(k, n=2), dict(k, n=2))
        self.assertEqual(w["days/" + TODAY][1]["pours"], {"b:k": 2})
        self.assertTrue(said)

    def test_corrections_count_the_ones_before_them(self):
        docs = export(**{"days/" + TODAY: {"date": TODAY, "pours": {"b:k": 1}}})
        c = {"fact": "pour", "date": TODAY, "n": -1}
        with self.assertRaisesRegex(record.Refused, "more than that"):
            gated(docs, dict(c, key="first"), dict(c, key="second"))
        # a pour earlier in the batch is held, so a correction after it may take it away
        w, _ = gated(export(), {"fact": "pour", "date": TODAY, "n": 2, "key": "a"}, dict(c, key="b"))
        self.assertEqual(w["days/" + TODAY][1]["pours"], {"b:a": 2, "b:b": -1})

    def test_an_item_captured_earlier_may_be_blocked_on(self):
        w, _ = gated(export(), {"fact": "todo", "doc": {"id": "i1", "what": "x"}},
                     {"fact": "todo", "doc": {"id": "i2", "what": "y", "blocks": ["i1"]}})
        self.assertEqual(w["todo/i2"][1]["blocks"], ["i1"])
        # and a second fact of one item in the batch is its update, not a second capture
        w, _ = gated(export(), {"fact": "todo", "doc": {"id": "i1", "what": "x"}},
                     {"fact": "todo", "doc": {"id": "i1", "what": "x", "next": "step"}})
        self.assertEqual(w["todo/i1"], ("set", w["todo/i1"][1]))
        self.assertEqual((w["todo/i1"][1]["captured"], w["todo/i1"][1]["next"]), (TODAY, "step"))

    def test_a_close_earlier_unblocks_the_tick_after_it(self):
        docs = export(**{"todo/i1": Blocked.WASHER})
        w, _ = gated(docs, {"fact": "close", "id": "i1"}, {"fact": "tick", "date": TODAY, "item": "gym"})
        self.assertIn("gym", w["days/" + TODAY][1]["items"])

    def test_a_second_sync_of_the_day_is_added_to_its_text(self):
        docs = export(**{"synclog/" + TODAY: {"date": TODAY, "text": "08:00 in sync"}})
        w, _ = gated(docs, {"fact": "synclog", "date": TODAY, "text": "14:00 dentist added"})
        self.assertEqual(w["synclog/" + TODAY], ("update", {"date": TODAY, "text": "08:00 in sync\n\n14:00 dentist added"}))
        w, _ = gated(export(), {"fact": "synclog", "date": TODAY, "text": "a"}, {"fact": "synclog", "date": TODAY, "text": "b"})
        self.assertEqual(w["synclog/" + TODAY], ("set", {"date": TODAY, "text": "a\n\nb"}))


class Contract(unittest.TestCase):
    def test_a_new_day_is_the_pages_blank(self):
        # the page's blank() and the item contract's are one shape; the gate sets it
        page = (Path(__file__).resolve().parent.parent / "web" / "cadence.html").read_text(encoding="utf-8")
        m = re.search(r"function blank\(date\)\{return \{(.*?)\};\}", page)
        self.assertIsNotNone(m, "the page's blank() is not where this test reads it")
        values = {"{}": {}, "null": None, "date": "D"}
        theirs = {k: values[v] for k, v in (kv.split(":", 1) for kv in m.group(1).split(","))}
        self.assertEqual(theirs, items.blank_day("D"))
        self.assertIs(record.blank, items.blank_day)

    def test_one_refusal(self):
        # an item contract refusal and a gate refusal are caught by one except
        self.assertIs(record.Refused, items.Refused)
        self.assertIs(gate.Refused, items.Refused)
        with self.assertRaisesRegex(record.Refused, "not a date"):
            gated(export(), {"fact": "synclog", "date": "soon", "text": "x"})


class Run(unittest.TestCase):
    def test_the_batch_is_pinned_and_a_bad_fact_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            docs = export(**{"days/" + TODAY: {"date": TODAY}})
            ruledir.write(t / "export", docs)
            (t / "versions.json").write_text(json.dumps({"/".join(k): 1 for k in docs}))
            (t / "facts.json").write_text(json.dumps([{"fact": "tick", "date": TODAY, "item": "brush"},
                                                      {"fact": "synclog", "date": TODAY, "text": "ok"}]))
            argv = [str(t / "export"), "--facts", str(t / "facts.json"), "--versions", str(t / "versions.json"),
                    "--out", str(t / "out"), "--now", NOW]
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = record.main(argv)
            self.assertEqual(code, 0, said.getvalue())
            batch = json.loads((t / "out" / "batch.json").read_text())
            self.assertEqual([(e["op"], e["collection"] + "/" + e["doc_id"], e.get("if_version")) for e in batch],
                             [("update", "days/" + TODAY, 1), ("set", "synclog/" + TODAY, None)])
            (t / "facts.json").write_text(json.dumps([{"fact": "tick", "date": TODAY, "item": "nap"}]))
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = record.main(argv)
            self.assertEqual(code, 1)
            self.assertIn("REFUSED", said.getvalue())
            self.assertFalse((t / "out" / "batch.json").exists())


if __name__ == "__main__":
    unittest.main()
