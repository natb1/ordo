#!/usr/bin/env python3
"""The gate: what it lets through, what it writes, and what it refuses.

Run on a frozen copy of the Rule (tools/fixture/rule): an invented one, laid out as the store holds it.

    python3 -m unittest tools/test_gate.py
"""
import contextlib
import copy
import functools
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate  # noqa: E402
import ruledir  # noqa: E402
import compiler  # noqa: E402

NOW = "2026-10-13T12:00:00Z"


def as_stored(docs):
    """Documents as the store hands them back: keys sorted, nothing but JSON."""
    return {k: json.loads(json.dumps(v, sort_keys=True)) for k, v in docs.items()}


RULE = as_stored(ruledir.read(ruledir.FIXTURE))
PAGE_SRC = (Path(__file__).resolve().parent.parent / "web" / "cadence.html").read_text(encoding="utf-8")


PAGE = {("projects", "canondb"): {"id": "canondb", "thread": "the page's"},
        ("days", "2026-10-12"): {"date": "2026-10-12"}}
# The whole Rule as one change: its first write to a store that holds only the
# page's own documents.
FIRST = [{"op": "update", "collection": c, "doc_id": i, "data": {"rule": v["rule"]}} if c in gate.NESTED
         else {"op": "set", "collection": c, "doc_id": i, "data": v} for (c, i), v in sorted(RULE.items())]


@functools.lru_cache(maxsize=None)
def _built():
    """The store, built once: a build runs the whole gate, and it never comes out
    another way."""
    out = dict(PAGE)
    for op, key, data in gate.gate(PAGE, FIRST, now=NOW):
        out[key] = gate.merged(out.get(key) or {}, data) if op == "update" else data
    return out


def store():
    """A store with the page's own documents, and the Rule written through the gate.
    Each caller gets a copy of its own: a test may write to it."""
    return as_stored(_built())


def ops(writes):
    return [(op, "/".join(key)) for op, key, _ in writes]


class Compiles(unittest.TestCase):
    def test_the_compiled_rule_is_what_the_compiler_makes_of_it(self):
        compiler.errors.clear()
        want = compiler.stored(compiler.compile(ruledir.assemble(RULE)))
        self.assertEqual(compiler.errors, [])
        self.assertEqual(store()[gate.COMPILED], as_stored(want))
        self.assertEqual([b["name"] for b in want["BLOCKS"]], ["Lauds", "Sext", "Vespers", "Compline"])
        self.assertNotIn("TODO", want)   # TODO and periodic items are the page's collections

    def test_the_first_write_carries_every_document_and_keeps_the_pages(self):
        w = gate.gate(PAGE, FIRST, now=NOW)
        self.assertEqual({k for _, k, _ in w}, set(RULE) | {gate.COMPILED, gate.SNAPSHOT})
        self.assertEqual(next(op for op, k, _ in w if k == ("projects", "canondb")), "update")
        self.assertEqual(next(op for op, k, _ in w if k == ("projects", "ordo")), "set")
        self.assertEqual(store()[("projects", "canondb")]["thread"], "the page's")
        self.assertEqual(gate.raw(store()), RULE)

    def test_a_store_that_holds_the_rule_needs_no_write(self):
        self.assertEqual(gate.gate(store()), [])

    def test_the_snapshot_holds_the_rule_as_written(self):
        snap = store()[gate.SNAPSHOT]
        self.assertEqual({(d["collection"], d["doc_id"]): d["data"] for d in snap["docs"]}, RULE)

    def test_the_page_takes_every_constant_the_compiler_gives(self):
        # the compiler's names and the page's setters are written by hand, in two files
        table = PAGE_SRC.split("var RULE_SET={", 1)[1].split("var ruleSeen", 1)[0]
        compiler.errors.clear()
        self.assertEqual(set(re.findall(r"\b([A-Z_]+):function\(v\)", table)),
                         set(compiler.compile(ruledir.assemble(RULE))))


class Changes(unittest.TestCase):
    def test_an_allocation_touches_the_rule_field_and_nothing_of_the_pages(self):
        w = gate.gate(store(), [{"op": "update", "collection": "projects", "doc_id": "canondb",
                                 "data": {"rule": {"allocation": 6}}}], now=NOW)
        self.assertEqual(ops(w), [("update", "projects/canondb"), ("set", "rule/compiled"), ("set", "snapshots/last")])
        self.assertEqual(w[0][2], {"rule": {"allocation": 6}})

    def test_a_field_taken_out_is_deleted_in_the_update(self):
        w = gate.gate(store(), [{"op": "update", "collection": "projects", "doc_id": "canondb",
                                 "data": {"rule": {"calendar": gate.DELETE}}}], now=NOW)
        self.assertEqual(w[0], ("update", ("projects", "canondb"), {"rule": {"calendar": gate.DELETE}}))

    def test_a_one_time_event_is_one_new_document(self):
        c = {"id": "dentist", "seq": 99, "what": "Dentist", "date": "2026-10-28", "start": "11:00", "end": "11:20",
             "calendar_event": "abc"}
        w = gate.gate(store(), [{"op": "set", "collection": "commitments", "doc_id": "dentist", "data": c}], now=NOW)
        self.assertEqual(ops(w), [("set", "commitments/dentist"), ("set", "rule/compiled"), ("set", "snapshots/last")])
        self.assertIn("dentist", [x["id"] for x in w[1][2]["COMMITMENTS"]])

    def test_a_change_that_changes_nothing_writes_nothing(self):
        self.assertEqual(gate.gate(store(), [{"op": "update", "collection": "projects", "doc_id": "canondb",
                                              "data": {"rule": {"allocation": 7}}}]), [])


class Projects(unittest.TestCase):
    """A project's repo is owner/name on GitHub or a path on a named device, and its
    name is its own `what` or else the repo's last part."""

    def compiled(self, *changes):
        """PROJECTS as the page reads them: rule/compiled as the store holds it, or as
        the gate writes it for the changes, which must change it."""
        s = store()
        if not changes:
            c = s[gate.COMPILED]
        else:
            c = {k: d for _, k, d in gate.gate(s, list(changes), now=NOW)}.get(gate.COMPILED)
            self.assertIsNotNone(c, "the changes left rule/compiled as it was")
        return {p["id"]: p for p in c["PROJECTS"]}

    def rule(self, doc_id, **rule):
        return {"op": "update", "collection": "projects", "doc_id": doc_id, "data": {"rule": rule}}

    def repo(self, r, **rule):
        return self.rule("nix_config", repo=r, **rule)

    def test_a_local_repo_is_named_and_never_linked(self):
        p = self.compiled()["garden"]
        self.assertEqual((p["what"], p["checkout"], p["allocation"]),
                         ("The garden", "desk:/srv/git/allotment", 0))
        self.assertNotIn("repo", p)   # stored, an unset link is left out: the page has none to follow

    def test_a_github_repo_is_linked_and_named_by_its_what(self):
        # ordo's what is not its repo's last part, so only its what can name it so
        p = self.compiled()["ordo"]
        self.assertEqual((p["what"], p["repo"], p["checkout"]),
                         ("ordo — the Rule", "https://github.com/natb1/ordo", "natb1/ordo"))

    def test_the_default_project_is_marked_for_the_page(self):
        # an item that names no project is filed under the one the Rule marks default
        ps = self.compiled(self.rule("garden", what="Allotment"))
        self.assertTrue(ps["ordo"]["default"])
        self.assertNotIn("default", ps["garden"])

    def test_an_allocation_that_is_no_whole_number_is_refused(self):
        for v in ("3", True, -1):
            with self.subTest(allocation=v), self.assertRaisesRegex(gate.Refused, "whole number of slots"):
                gate.gate(store(), [self.rule("garden", allocation=v)])

    def test_a_bell_moved_past_midnight_is_refused(self):
        late = {"op": "set", "collection": "commitments", "doc_id": "late", "data": {
            "id": "late", "what": "A late show", "date": "2026-10-28", "start": "22:00", "end": "23:40",
            "calendar_event": "x", "seq": 9, "sets_anchor_bell": "evening", "derived_anchor_bell": "00:15",
            "derived_leave_by": "21:30"}}
        with self.assertRaisesRegex(gate.Refused, "not after meta.day_starts"):
            gate.gate(store(), [late])

    def test_day_starts_is_read_as_the_clock_reads_it(self):
        office = copy.deepcopy(store()[("rule", "office")])
        office["meta"]["day_starts"] = 400
        with self.assertRaisesRegex(gate.Refused, r"meta day_starts: 400 is not a quoted \"HH:MM\""):
            gate.gate(store(), [{"op": "set", "collection": "rule", "doc_id": "office", "data": office}], now=NOW)

    def test_one_default_project_named_alike_in_the_policy(self):
        # two marked default, or the mark on a project the policy does not name, or on a
        # shelved one: the page and the record gate would file an unnamed item apart
        for change, why in (([self.rule("garden", default=True)], "2 projects are marked default"),
                            ([self.rule("ordo", default=False), self.rule("garden", default=True)],
                             "the policy's default_project is ordo"),
                            ([self.rule("ordo", active=False)], "is not active")):
            with self.subTest(why=why), self.assertRaisesRegex(gate.Refused, why):
                gate.gate(store(), change)

    def test_with_no_what_a_project_is_named_after_its_repo(self):
        ps = self.compiled(self.rule("ordo", what=gate.DELETE), self.rule("garden", what=gate.DELETE))
        self.assertEqual(ps["ordo"]["what"], "ordo")
        self.assertEqual(ps["garden"]["what"], "allotment")   # its repo's last part, not its id

    def test_a_repo_that_is_neither_is_refused(self):
        for r in ("garden", "desk:srv/git/garden", "https://github.com/natb1/ordo", "desk:/", "a/b/c", "",
                  "github.com/natb1", "natb1/..", "../.."):
            with self.subTest(repo=r), self.assertRaisesRegex(gate.Refused, "device:/path"):
                gate.gate(store(), [self.repo(r)])

    def test_a_name_that_is_not_text_is_refused(self):
        with self.assertRaisesRegex(gate.Refused, "a project's name is text"):
            gate.gate(store(), [self.repo("natb1/nix-config", what="")])

    def test_a_notebook_that_is_not_a_map_is_refused_by_name(self):
        # not a crash in projects(), which runs first: frontier()'s refusal, active or not
        for active in (True, False):
            with self.subTest(active=active), self.assertRaisesRegex(gate.Refused, "it is a map with a notebook"):
                gate.gate(store(), [self.rule("nix_config", active=active, hypomnemata="https://claude.ai/artifact/x")])


class Snapshots(unittest.TestCase):
    def test_the_weekly_snapshot_is_kept_by_its_date_and_as_last(self):
        # with no change: snapshots/last is written too, so the counts ride on it
        w = gate.gate(store(), keep="2026-10-18", now=NOW)
        self.assertEqual(ops(w), [("set", "snapshots/last"), ("set", "snapshots/2026-10-18")])
        for _, _, data in w:
            self.assertEqual({(d["collection"], d["doc_id"]): d["data"] for d in data["docs"]}, RULE)
        with self.assertRaises(gate.Refused):
            gate.gate(store(), keep="last week")

    def test_a_restore_undoes_what_came_after_the_snapshot(self):
        s = store()
        snap = s[gate.SNAPSHOT]
        c = {"id": "dentist", "seq": 99, "what": "Dentist", "date": "2026-10-28", "start": "11:00", "end": "11:20",
             "calendar_event": "abc"}
        for op, key, data in gate.gate(s, [{"op": "set", "collection": "commitments", "doc_id": "dentist", "data": c},
                                           {"op": "update", "collection": "projects", "doc_id": "canondb",
                                            "data": {"rule": {"allocation": 6, "added": 1}}}], now=NOW):
            s[key] = gate.merged(s.get(key) or {}, data) if op == "update" else data
        w = gate.gate(as_stored(s), restore=snap, now=NOW)
        self.assertEqual(ops(w), [("delete", "commitments/dentist"), ("update", "projects/canondb"),
                                  ("set", "rule/compiled"), ("set", "snapshots/last")])
        self.assertEqual(w[1][2], {"rule": {"added": gate.DELETE, "allocation": 7}})

    def test_a_restore_carries_each_guard_the_snapshot_lacks(self):
        # a snapshot taken before the Office items named their guards
        snap = copy.deepcopy(store()[gate.SNAPSHOT])
        office = next(d["data"] for d in snap["docs"] if (d["collection"], d["doc_id"]) == ("rule", "office"))
        meds = office["anchors"][0]["items"][0]
        self.assertEqual(meds["id"], "meds")
        guard = meds.pop("guard")
        said = []
        w = gate.gate(store(), restore=snap, now=NOW, said=said)
        self.assertEqual(ops(w), [])     # the Rule as it stands: nothing to write
        self.assertEqual(said, [f"meds: the snapshot names no guard; carried over from rule/office: {guard}"])
        # one the current Office does not hold either is refused, to be asked
        s = store()
        cur = copy.deepcopy(s[("rule", "office")])
        del cur["anchors"][0]["items"][0]["guard"]
        s[("rule", "office")] = cur
        with self.assertRaisesRegex(gate.Refused, "item meds: names no guard"):
            gate.gate(s, restore=snap, now=NOW)

    def test_a_snapshot_that_cannot_be_kept_is_refused(self):
        snap = dict(store()[gate.SNAPSHOT])
        snap["docs"] = [d for d in snap["docs"] if d["doc_id"] != "ledger"]
        with self.assertRaisesRegex(gate.Refused, "rule/ledger is missing"):
            gate.gate(store(), restore=snap)

    def test_a_snapshot_cannot_name_a_file_of_its_own(self):
        # a restore takes its ids from the snapshot's content, and an id is a file's name
        snap = dict(store()[gate.SNAPSHOT])
        snap["docs"] = snap["docs"] + [{"collection": "backlog", "doc_id": "sub/dir",
                                        "data": {"id": "sub/dir", "seq": 9, "what": "X", "status": "parked"}}]
        with self.assertRaisesRegex(gate.Refused, "not a document's name"):
            gate.gate(store(), restore=snap)


class Refusals(unittest.TestCase):
    def refused(self, change, why):
        with self.assertRaisesRegex(gate.Refused, why):
            gate.gate(store(), [change])

    def test_an_event_the_calendar_does_not_hold(self):
        self.refused({"op": "set", "collection": "commitments", "doc_id": "x",
                      "data": {"id": "x", "seq": 99, "what": "X", "date": "2026-10-28", "start": "11:00", "end": "11:20"}},
                     "no calendar_event")

    def test_a_day_that_cannot_be_done(self):
        # four hours across the midday bell, on a weekday with nothing to give
        self.refused({"op": "set", "collection": "commitments", "doc_id": "x",
                      "data": {"id": "x", "seq": 99, "what": "X", "weekday": "mon", "start": "10:00", "end": "14:00",
                               "calendar_event": "abc"}}, "midday")

    def test_the_pages_fields_are_not_the_gates(self):
        self.refused({"op": "update", "collection": "projects", "doc_id": "canondb", "data": {"thread": "x"}},
                     "update its `rule` field only")
        self.refused({"op": "set", "collection": "days", "doc_id": "2026-10-13", "data": {}}, "not a document of the Rule")
        self.refused({"op": "set", "collection": "todo", "doc_id": "x", "data": {}}, "not a document of the Rule")

    def test_a_document_the_rule_needs(self):
        self.refused({"op": "delete", "collection": "rule", "doc_id": "ledger"}, "rule/ledger is missing")

    def test_a_rule_document_no_tool_reads(self):
        # raw() would never hand it back, so it could not be checked or deleted again
        self.refused({"op": "set", "collection": "rule", "doc_id": "offce", "data": {}}, "not a document of the Rule")
        self.refused({"op": "set", "collection": "rule", "doc_id": "compiled", "data": {}}, "not a document of the Rule")

    def test_a_change_with_no_data(self):
        self.refused({"op": "set", "collection": "commitments", "doc_id": "x"}, "needs data, an object")
        self.refused({"op": "update", "collection": "backlog", "doc_id": "filing", "data": ["what"]},
                     "needs data, an object")

    def test_a_weekday_rule_that_is_not_a_list(self):
        # rule.py's `in` takes a map; the page's indexOf does not
        office = json.loads(json.dumps(RULE[("rule", "office")]))
        gym = next(it for b in office["anchors"] for it in b["items"] if it["id"] == "gym")
        gym["skip_weekday"] = {"sun": True, "wed": True}
        self.refused({"op": "set", "collection": "rule", "doc_id": "office", "data": office}, "is not a list of")

    def test_a_date_the_page_would_not_match(self):
        self.refused({"op": "set", "collection": "commitments", "doc_id": "x",
                      "data": {"id": "x", "seq": 99, "what": "X", "date": "20261028", "start": "11:00", "end": "11:20",
                               "calendar_event": "abc"}}, "not a date")

    def test_a_removal_marker_in_a_list(self):
        # the store takes {"__delete__": true} only in a map of an update
        office = json.loads(json.dumps(RULE[("rule", "office")]))
        gym = next(it for b in office["anchors"] for it in b["items"] if it["id"] == "gym")
        gym["skip_weekday"] = {"__delete__": True}
        self.refused({"op": "update", "collection": "rule", "doc_id": "office", "data": {"anchors": office["anchors"]}},
                     "never in a list")


ALLOCATION = [{"op": "update", "collection": "projects", "doc_id": "canondb", "data": {"rule": {"allocation": 6}}}]


class Batch(unittest.TestCase):
    def test_each_write_names_its_file_and_its_version(self):
        w = gate.gate(store(), ALLOCATION, now=NOW)
        with tempfile.TemporaryDirectory() as t:
            b = gate.emit(w, {"projects/canondb": 5, "rule/compiled": 2, "snapshots/last": 3}, t, held=set(store()))
            self.assertEqual([e.get("if_version") for e in b], [5, 2, 3])
            self.assertEqual(json.loads(Path(b[0]["file_path"]).read_text()), {"rule": {"allocation": 6}})
            self.assertEqual(json.loads((Path(t) / "batch.json").read_text()), b)

    def test_a_write_to_a_document_the_store_holds_needs_its_version(self):
        # the store refuses a whole batch for one such write, and every batch writes snapshots/last
        w = gate.gate(store(), ALLOCATION, now=NOW)
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(gate.Refused, "snapshots/last"):
                gate.emit(w, {"projects/canondb": 5, "rule/compiled": 2}, t, held=set(store()))
            self.assertEqual(list(Path(t).iterdir()), [])


class Run(unittest.TestCase):
    """The command line: what it is given, what it leaves in OUT."""

    def exported(self, t, docs):
        """An export of `docs` under t with a version for each: the arguments naming it."""
        ruledir.write(t / "export", docs)
        (t / "versions.json").write_text(json.dumps({"/".join(k): 1 for k in docs}))
        return [str(t / "export"), "--versions", str(t / "versions.json"), "--out", str(t / "out")]

    def run_gate(self, argv):
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = gate.main(argv)
        return code, said.getvalue()

    def test_a_run_pins_every_write_snapshots_last_too(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            argv = self.exported(t, store())
            (t / "change.json").write_text(json.dumps(ALLOCATION))
            code, said = self.run_gate(argv + ["--change", str(t / "change.json")])
            self.assertEqual(code, 0, said)
            batch = json.loads((t / "out" / "batch.json").read_text())
            self.assertEqual([(e["op"], e["collection"] + "/" + e["doc_id"], e.get("if_version")) for e in batch],
                             [("update", "projects/canondb", 1), ("set", "rule/compiled", 1),
                              ("set", "snapshots/last", 1)])

    def test_a_refused_run_leaves_no_older_batch_to_send(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            argv = self.exported(t, RULE)
            (t / "change.json").write_text(json.dumps([{"op": "set", "collection": "days", "doc_id": "x", "data": {}}]))
            (t / "out").mkdir()
            (t / "out" / "batch.json").write_text("[]")
            code, said = self.run_gate(argv + ["--change", str(t / "change.json")])
            self.assertEqual(code, 1)
            self.assertIn("REFUSED", said)
            self.assertIn("days/x is not a document of the Rule", said)
            self.assertFalse((t / "out" / "batch.json").exists())

    def test_the_batch_does_not_go_in_the_export(self):
        # it is laid out as the export is, and the next run would read it as the store's
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            ruledir.write(t / "export", RULE)
            for out in (t / "export", t / "export" / "out"):
                code, said = self.run_gate([str(t / "export"), "--out", str(out)])
                self.assertEqual(code, 1)
                self.assertIn("is the export or inside it", said)

    def test_a_document_the_export_gave_no_version_for(self):
        # a file an earlier export left in the directory: out_dir removes nothing
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            argv = self.exported(t, RULE)
            ruledir.write(t / "export", {("commitments", "gone"): {"id": "gone", "seq": 98, "what": "Gone",
                                                                    "date": "2026-10-20", "start": "11:00",
                                                                    "end": "11:20", "calendar_event": "abc"}})
            code, said = self.run_gate(argv)
            self.assertEqual(code, 1)
            self.assertIn("--versions does not name commitments/gone", said)

    def test_a_second_snapshot_of_one_date_is_pinned(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            docs = store()
            docs[("snapshots", "2026-10-18")] = docs[gate.SNAPSHOT]
            argv = self.exported(t, docs)
            code, said = self.run_gate(argv + ["--snapshot", "2026-10-18"])
            self.assertEqual(code, 0, said)
            self.assertIn("snapshots/2026-10-18 is held already", said)
            batch = json.loads((t / "out" / "batch.json").read_text())
            self.assertEqual([(e["op"], e["collection"] + "/" + e["doc_id"], e.get("if_version")) for e in batch],
                             [("set", "snapshots/last", 1), ("set", "snapshots/2026-10-18", 1)])
            # held, and the versions do not name it: refused, never an unpinned set
            versions = {"/".join(k): 1 for k in docs if k != ("snapshots", "2026-10-18")}
            (t / "versions.json").write_text(json.dumps(versions))
            code, said = self.run_gate(argv + ["--snapshot", "2026-10-18"])
            self.assertEqual(code, 1, said)
            self.assertIn("--versions does not name snapshots/2026-10-18", said)

    def test_a_collection_the_export_left_out(self):
        # one not listed reads as empty, and would be compiled as none
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            argv = self.exported(t, {k: v for k, v in store().items() if k[0] != "backlog"})
            code, said = self.run_gate(argv)
            self.assertEqual(code, 1)
            self.assertIn("the export holds no backlog", said)


class Ledger(unittest.TestCase):
    """The change ledger (hypomnemata › record): what a review read rides on the
    snapshots it writes, so that two snapshots side by side say what a change did."""

    CHANGE = [{"op": "update", "collection": "projects", "doc_id": "canondb", "data": {"rule": {"allocation": 5}}}]
    COUNTS = {"as_of": "2026-10-19", "under_review": {"from": "2026-10-11", "to": "2026-10-17"},
              "week": {"slots_worked": 13}}

    def test_the_counts_ride_on_every_snapshot_written(self):
        writes = gate.gate(store(), self.CHANGE, now=NOW, keep="2026-10-19", counts=self.COUNTS)
        snaps = {key: data for op, key, data in writes if key[0] == "snapshots"}
        self.assertEqual(set(snaps), {gate.SNAPSHOT, ("snapshots", "2026-10-19")})
        for data in snaps.values():
            self.assertEqual(data["counts"], self.COUNTS)
            self.assertEqual(data["at"], NOW)

    def test_a_snapshot_without_counts_carries_none(self):
        for op, key, data in gate.gate(store(), self.CHANGE, now=NOW):
            if key[0] == "snapshots":
                self.assertNotIn("counts", data)

    def test_counts_that_are_not_the_tools_are_refused(self):
        # a list, or some other JSON object (a versions file, say): only what counts.py prints rides
        for counts in ([13], {"rule/office": 3, "snapshots/last": 1}):
            with self.subTest(counts=counts), self.assertRaisesRegex(gate.Refused, "counts.py"):
                gate.gate(store(), self.CHANGE, now=NOW, counts=counts)

    def test_counts_read_on_another_day_than_the_snapshots_are_refused(self):
        with self.assertRaisesRegex(gate.Refused, "read as of 2026-10-19 and the snapshot is dated 2026-10-26"):
            gate.gate(store(), self.CHANGE, now=NOW, keep="2026-10-26", counts=self.COUNTS)
        # without a dated snapshot the day is not held to
        self.assertTrue(gate.gate(store(), self.CHANGE, now=NOW, counts=self.COUNTS))


class Guards(unittest.TestCase):
    """The guard on each item (hypomnemata › unprompted): every Office item names
    what holds it in place, and the end a notebook's root states is text."""

    def office(self):
        return copy.deepcopy(store()[("rule", "office")])

    def test_an_office_item_that_names_no_guard_is_refused(self):
        office = self.office()
        del office["anchors"][0]["items"][0]["guard"]
        with self.assertRaisesRegex(gate.Refused, "item meds: names no guard"):
            gate.gate(store(), [{"op": "set", "collection": "rule", "doc_id": "office", "data": office}], now=NOW)

    def test_a_guard_the_rule_does_not_know_is_refused(self):
        office = self.office()
        office["anchors"][0]["items"][0]["guard"] = "hope"
        with self.assertRaisesRegex(gate.Refused, "bell, alarm, budget, plan, none"):
            gate.gate(store(), [{"op": "set", "collection": "rule", "doc_id": "office", "data": office}], now=NOW)

    def test_a_work_item_and_a_fixture_item_name_none(self):
        office = store()[("rule", "office")]
        kinds = {it.get("kind") for an in office["anchors"] for it in an["items"] if "guard" not in it}
        self.assertEqual(kinds, {"work", "fixture"})   # and the Rule compiles, as store() shows

    def test_an_end_that_is_not_text_is_refused(self):
        change = [{"op": "update", "collection": "projects", "doc_id": "canondb",
                   "data": {"rule": {"hypomnemata": {"end": 3}}}}]
        with self.assertRaisesRegex(gate.Refused, "hypomnemata.end"):
            gate.gate(store(), change, now=NOW)

    def test_an_end_is_carried_as_the_rules(self):
        change = [{"op": "update", "collection": "projects", "doc_id": "nix_config",
                   "data": {"rule": {"hypomnemata": {"notebook": "https://claude.ai/artifact/x", "end": "That it build."}}}}]
        writes = {key: data for op, key, data in gate.gate(store(), change, now=NOW)}
        self.assertEqual(writes[("projects", "nix_config")]["rule"]["hypomnemata"]["end"], "That it build.")

    def test_an_end_the_root_no_longer_states_is_deleted_not_left_out(self):
        # an update merges, so a field left out keeps its old value: the sync sends the marker
        left_out = [{"op": "update", "collection": "projects", "doc_id": "canondb",
                     "data": {"rule": {"hypomnemata": {"revision": "r2"}}}}]
        writes = {key: data for op, key, data in gate.gate(store(), left_out, now=NOW)}
        self.assertNotIn("end", writes[("projects", "canondb")]["rule"]["hypomnemata"])   # unchanged, so unsaid
        gone = [{"op": "update", "collection": "projects", "doc_id": "canondb",
                 "data": {"rule": {"hypomnemata": {"end": gate.DELETE}}}}]
        w = gate.gate(store(), gone, now=NOW)
        self.assertEqual(w[0], ("update", ("projects", "canondb"), {"rule": {"hypomnemata": {"end": gate.DELETE}}}))


# ---- the page ----------------------------------------------------------------
# The page's script has no test harness of its own. Where its behaviour can be run
# alone, the functions are lifted out of web/cadence.html by name and run under node
# (skipped where node is absent: preflight runs without it); where it cannot, these
# read the source and assert the shape that implements it.

def js_block(name, src=PAGE_SRC):
    """The text of `function name(...){...}` or `var name=...;` in the page, braces
    matched past string literals."""
    m = re.search(r"function " + re.escape(name) + r"\(", src) or re.search(r"var " + re.escape(name) + r"=", src)
    if not m:
        raise AssertionError(f"the page has no {name}")
    i, depth, quote = src.index("{", m.end() - 1) if src[m.start()] == "f" else m.end(), 0, None
    if src[m.start()] == "v" and src[i] != "{":
        return src[m.start():src.index(";", i) + 1]
    while True:
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if src[m.start()] == "v":
                    end = src.index(";", end) + 1
                return src[m.start():end]
        i += 1


def run_js(names, body, pre=""):
    """Run `body` under node with the named page functions defined; it prints JSON
    with out(...). The result, parsed."""
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed; the page's shape is still checked")
    script = '"use strict";\nvar out=function(v){ process.stdout.write(JSON.stringify(v)); };\n' + pre + "\n" + \
        "\n".join(js_block(n) for n in names) + "\n" + body
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60, env={"TZ": "UTC"})
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def page_fn(name):
    return js_block(name)


class Page(unittest.TestCase):
    """The Cadence page's own code: the clock, the lists, the sync, the cards."""

    CLOCK = ["ymd", "hm", "fmt", "wall", "wallMins", "nowMins", "dayMins", "dayEnd", "logicalDay"]

    def test_the_rule_defaults_name_every_constant(self):
        # a Rule adopted, or one fallen back to, starts from these: none may be missing
        table = PAGE_SRC.split("var RULE_SET={", 1)[1].split("var ruleSeen", 1)[0]
        defaults = PAGE_SRC.split("var RULE_DEFAULT={", 1)[1].split("};", 1)[0]
        self.assertEqual(set(re.findall(r"\b([A-Z_]+):", defaults)),
                         set(re.findall(r"\b([A-Z_]+):function\(v\)", table)))

    def test_a_rule_fallen_back_from_leaves_none_of_its_values(self):
        adopt = page_fn("adoptRule")
        self.assertLess(adopt.index("resetRule();"), adopt.index("RULE_SET[n](c[n])"))
        fallback = PAGE_SRC.split('console.error("cadence: the store\'s Rule could not be drawn"', 1)[1].split("drawOrSay();", 1)[0]
        self.assertLess(fallback.index("resetRule();"), fallback.index("adoptRule("))

    def test_the_compiler_gives_the_rules_timezone(self):
        compiler.errors.clear()
        self.assertEqual(compiler.compile(ruledir.assemble(RULE))["TIMEZONE"], "America/New_York")
        office = copy.deepcopy(RULE[("rule", "office")])
        office["meta"]["timezone"] = "Mars/Olympus"
        compiler.errors.clear()
        compiler.timezone(office)
        self.assertTrue(any("meta.timezone" in e for e in compiler.errors))
        compiler.errors.clear()

    def test_the_clock_is_the_rules_timezone(self):
        # 07:30 UTC is 03:30 in New York, before the day starts at 04:00: still the
        # 21st there, and 16:30 on the 22nd in Tokyo; with none, the browser's (UTC here)
        got = run_js(self.CLOCK, """
            var DAY_START="04:00", TIMEZONE=null, d=new Date("2026-10-22T07:30:00Z"), r={};
            r.local=[logicalDay(d), wallMins(d)];
            TIMEZONE="America/New_York"; r.ny=[logicalDay(d), wallMins(d)];
            TIMEZONE="Asia/Tokyo"; r.tokyo=[logicalDay(d), wallMins(d)];
            r.invalid=logicalDay(new Date("nonsense"));
            out(r);""", pre="var zoneFmt=null, zoneFor=null;")
        self.assertEqual(got["local"], ["2026-10-22", 450])
        self.assertEqual(got["ny"], ["2026-10-21", 210])
        self.assertEqual(got["tokyo"], ["2026-10-22", 990])
        self.assertIn("NaN", got["invalid"])   # an unreadable date does not throw

    def test_the_page_reads_its_clock_through_the_zone(self):
        self.assertIn("timeZone:TIMEZONE", page_fn("wall"))
        self.assertIn("wall(d)", page_fn("logicalDay"))
        self.assertIn("TIMEZONE:function(v)", PAGE_SRC)

    def test_a_fixture_past_midnight_is_shown(self):
        got = run_js(self.CLOCK + ["fixtureNote"], """
            var DAY_START="04:00", TIMEZONE=null, now=0;
            nowMins=function(){ return now; };
            var r={};
            now=1500; r.late=fixtureNote({what:"Show",start:"23:00",end:"01:30"});
            now=1500; r.small=fixtureNote({what:"Call",start:"00:30",end:"02:00"});
            now=1380; r.ahead=fixtureNote({what:"Call",start:"00:30",end:"02:00",leaveBy:"23:50"});
            now=1440; r.leave=fixtureNote({what:"Call",start:"00:30",end:"02:00",leaveBy:"23:50"});
            now=1500; r.over=fixtureNote({what:"Day",start:"10:00",end:"23:00"});
            out(r);""", pre="var nowMins;")
        self.assertEqual(got["late"], {"text": "Show until 1:30 AM", "late": True})
        self.assertEqual(got["small"], {"text": "Call until 2:00 AM", "late": True})
        self.assertFalse(got["ahead"]["late"])
        self.assertTrue(got["leave"]["late"])
        self.assertIsNone(got["over"])

    def test_the_meeting_under_way_is_on_the_days_count(self):
        self.assertIn("dayMins(c.start)<=now && now<dayEnd(c.start,c.end)", PAGE_SRC)

    def test_an_item_is_listed_under_the_project_it_is_charged_to(self):
        got = run_js(["seedIn", "projById", "projAny", "defaultProject", "homeProject"], """
            PROJECTS=[{id:"a"},{id:"b",default:true}]; SHELVED=[{id:"s"}];
            out([null,{},{project:null},{project:"gone"},{project:"s"},{project:"a"}].map(homeProject));""",
            pre="var PROJECTS, SHELVED;")
        self.assertEqual(got, ["b", "b", "b", "b", "s", "a"])
        for fn in ("todoFor", "periodicFor", "dictationDocs", "followUps"):
            with self.subTest(fn=fn):
                self.assertIn("homeProject(x)", page_fn(fn))
        self.assertIn("return o ? homeProject(o) : defaultProject();", page_fn("workProject"))
        blocked = page_fn("paintBlocked")
        self.assertIn("openTodo(homeProject(x),x.id)", blocked)
        self.assertIn("if(homeProject(x)) acts.appendChild(edit)", blocked)

    def test_other_days_are_read_again(self):
        # another device's write to a day not on screen reaches the cache: on show, on
        # the network back, at the turn
        self.assertIn("pastDays={}", page_fn("syncDays"))
        self.assertIn("resyncDays(false)", PAGE_SRC.split('document.addEventListener("visibilitychange"', 1)[1].split("\n});", 1)[0])
        self.assertIn("resyncDays(true)", PAGE_SRC.split('window.addEventListener("online"', 1)[1].split("\n", 1)[0])
        self.assertIn("resyncDays(true)", page_fn("clockTick"))

    def test_a_refused_patch_loses_only_the_refused_leaf(self):
        names = ["clone", "isObj", "canon", "applyPatch", "subtract", "stripNulls", "loadQ", "saveQ", "qList",
                 "clashes", "queue", "writeDoc", "sendDoc", "leavesOf", "leafByLeaf", "flushQ", "blank"]
        got = run_js(names, """
            var landed=[], warned=[];
            console.warn=function(m){ warned.push(m); };
            function bad(p){ return JSON.stringify(p).indexOf("BAD")>=0; }
            db={doc:function(path){ return {
              update:function(p){ if(bad(p)) return Promise.reject({code:"invalid_argument"}); landed.push(p); return Promise.resolve(); },
              acquire:function(){ return Promise.resolve({acquired:true}); },
              get:function(){ return Promise.resolve({exists:true,data:function(){ return {date:"2026-10-20"}; }}); },
              set:function(p){ landed.push(p); return Promise.resolve(); } }; }};
            queue("cadence:pending","2026-10-20",{items:{a:true,b:"BAD"},bells:{lauds:{at:"6:00 AM"}}});
            flushQ("cadence:pending","2026-10-20","days/2026-10-20",{date:"2026-10-20"},blank("2026-10-20"),"date").then(function(ok){
              out({ok:ok,landed:landed,left:loadQ("cadence:pending"),warned:warned});
            });""", pre="""var db=null, flushing={}, chains={}, retryTimer=null, leaseN=0, TAB="t", memQ={}, memQOnly={};
                var window={console:console}, localStorage={getItem:function(){ throw 1; }};
                var setTimeout=function(){ return 0; }, clearTimeout=function(){}, flushAll=function(){};""")
        self.assertTrue(got["ok"])
        self.assertEqual(got["landed"], [{"date": "2026-10-20", "items": {"a": True}},
                                         {"date": "2026-10-20", "bells": {"lauds": {"at": "6:00 AM"}}}])
        self.assertEqual(got["left"], {})
        self.assertEqual(len(got["warned"]), 1)
        self.assertIn('"b":"BAD"', got["warned"][0])

    def test_a_past_day_the_page_makes_is_backfilled(self):
        got = run_js(["blank", "daySeed"], """
            logicalToday=function(){ return "2026-10-22"; };
            out([daySeed("2026-10-20").backfilled, daySeed("2026-10-22").backfilled]);""", pre="var logicalToday;")
        self.assertEqual(got, [True, None])
        self.assertIn("daySeed(date)", page_fn("flushDay"))

    def test_done_today_pressed_twice_starts_once(self):
        done = PAGE_SRC.split('actButton("Done today"', 1)[1].split("putPeriodic(", 1)[0]
        self.assertIn("again=hs.indexOf(today)>=0", done)
        self.assertIn("if(x.then && !again && lastDoneDate(x.id)!==today) patch.started=sessionNow();", done)

    def test_a_count_typed_is_a_whole_number(self):
        got = run_js(["wholeNum"], 'out(["3"," 4 ","2.5","1e1","","-1","0",7,null,"99999999999999999999"].map(wholeNum));')
        self.assertEqual(got, [3, 4, None, None, None, None, 0, 7, None, None])
        self.assertNotIn("parseInt(", PAGE_SRC.split("<script>")[2])
        for said in ("Sessions this week is a whole number of sessions", "Every … days is a whole number of days"):
            self.assertIn(said, PAGE_SRC)

    def test_the_counts_are_worked_out_once_per_render(self):
        got = run_js(["memo", "focusCounts", "lastDoneDate"], """
            var n=0, m=0;
            focusCount=function(){ n++; return {a:1}; };
            lastDone=function(id){ m++; return id; };
            focusCounts(); focusCounts(); lastDoneDate("x"); lastDoneDate("x"); lastDoneDate("y");
            recRev++; focusCounts(); lastDoneDate("x");
            out([n,m]);""", pre="""var memoKey=null, memoBox={}, recRev=0, todoRev=0, viewDate="2026-10-22", focusCount, lastDone;
                function logicalToday(){ return "2026-10-22"; }""")
        self.assertEqual(got, [2, 3])
        for fn in ("render", "save", "cacheDay", "saveStore", "repaintCard", "paintCard"):
            with self.subTest(fn=fn):
                self.assertIn("recRev++", page_fn(fn))
        self.assertIn('memo("meetings"', page_fn("meetingCounts"))
        self.assertIn('memo("sessions"', page_fn("sessionsRecorded"))


if __name__ == "__main__":
    unittest.main()
