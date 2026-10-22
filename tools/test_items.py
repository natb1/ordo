#!/usr/bin/env python3
"""The item contract: the shape of a todo or periodic document, and an owner's protocol.

It needs no Rule, only the lists; the lists themselves are read from the frozen Rule
(tools/fixture/rule) once, to show they are what the record gate checks against.

    python3 -m unittest tools/test_items.py
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import items  # noqa: E402
import ruledir  # noqa: E402

TODAY = "2026-10-15"
LISTS = {"projects": ["canondb", "ordo"], "default_project": "ordo",
         "known": ["gym", "laundry", "garden-beds_2026"], "today": TODAY}
SRC = {"owner": "garden", "url": "https://github.com/natb1/garden/blob/main/plan/beds.toml"}


def check(collection, doc, held=None, owner=None, lists=LISTS):
    return items.check(collection, doc, held=held, owner=owner, projects=lists["projects"],
                       default_project=lists["default_project"], known=set(lists["known"]), today=lists["today"])


class Shape(unittest.TestCase):
    def test_a_capture_takes_the_default_project_and_today(self):
        d = check("todo", {"id": "i1", "what": "Call the plumber", "blocks": ["gym", "q:canondb:priority"]})
        self.assertEqual((d["project"], d["captured"], d["blocks"]), ("ordo", TODAY, ["gym", "q:canondb:priority"]))

    def test_a_project_that_is_no_id_is_refused(self):
        for p in (["ordo"], {"a": 1}, "", 0):
            with self.subTest(project=p), self.assertRaisesRegex(items.Refused, "a project's id"):
                check("todo", {"id": "i1", "what": "x", "project": p})

    def test_what_it_refuses(self):
        for doc, why in [({"id": "I1", "what": "x"}, "id of lowercase"),
                         ({"id": "i1"}, "needs what"),
                         ({"id": "i1", "what": "x", "project": "nix"}, "not an active project"),
                         ({"id": "i1", "what": "x", "blocks": ["haircut"]}, "does not carry"),
                         ({"id": "i1", "what": "x", "blocks": ["i1"]}, "does not carry"),
                         ({"id": "i1", "what": "x", "by": "2026-02-30"}, "not a date"),
                         ({"id": "i1", "what": "x", "kind": "note"}, "kind is dictation")]:
            with self.subTest(why=why), self.assertRaisesRegex(items.Refused, why):
                check("todo", doc)
        with self.assertRaisesRegex(items.Refused, "cadence"):
            check("periodic", {"id": "p1", "what": "Haircut", "cadence": 0})
        with self.assertRaisesRegex(items.Refused, "todo or a periodic"):
            check("days", {"id": "p1", "what": "x"})

    def test_a_source_is_owner_and_https_url(self):
        self.assertEqual(check("todo", {"id": "i1", "what": "x", "source": SRC})["source"], SRC)
        for s, why in [({"owner": "Garden", "url": SRC["url"]}, "source.owner"),
                       ({"owner": "garden", "url": "http://example.com"}, "source.url"),
                       ({"owner": "garden", "url": SRC["url"], "rank": 1}, "source is"),
                       ("garden", "source is")]:
            with self.subTest(s=s), self.assertRaisesRegex(items.Refused, why):
                check("todo", {"id": "i1", "what": "x", "source": s})
        with self.assertRaisesRegex(items.Refused, "periodic item has no owner"):
            check("periodic", {"id": "garden-mulch", "what": "Mulch", "cadence": 90, "source": SRC})
        self.assertEqual(items.owner_of({"source": SRC}), "garden")
        self.assertIsNone(items.owner_of({"what": "x"}))

    def test_notes_are_plain_text(self):
        notes = "Recommend $1M 20-year term.\nQuote by Saturday."
        self.assertEqual(check("todo", {"id": "i1", "what": "x", "notes": notes})["notes"], notes)
        self.assertEqual(check("periodic", {"id": "p1", "what": "x", "cadence": 7, "notes": "y"})["notes"], "y")
        self.assertEqual(check("todo", {"id": "garden-x", "what": "x", "source": SRC, "notes": notes},
                               owner="garden")["notes"], notes)
        for n in (["a", "b"], {"a": 1}, 3):
            with self.subTest(notes=n), self.assertRaisesRegex(items.Refused, "notes is plain text"):
                check("todo", {"id": "i1", "what": "x", "notes": n})

    def test_the_input_is_not_changed(self):
        doc = {"id": "i1", "what": "x"}
        check("todo", doc)
        self.assertEqual(doc, {"id": "i1", "what": "x"})


class Protocol(unittest.TestCase):
    held = {"id": "garden-beds_2026", "what": "Plant the beds", "project": "ordo", "captured": "2026-10-01",
            "source": SRC, "at": "2026-10-01T12:00:00Z"}

    def test_an_owners_capture_and_update(self):
        d = check("todo", {"id": "garden-bed_prep", "what": "Prepare the beds", "by": "2026-12-31",
                           "source": SRC}, owner="garden")
        self.assertEqual((d["project"], d["captured"]), ("ordo", TODAY))
        d = check("todo", {"id": "garden-beds_2026", "what": "Plant the beds", "by": "2027-04-15", "source": SRC},
                  held=self.held, owner="garden")
        self.assertNotIn("project", d)      # merged: what the owner did not say is left as held
        self.assertNotIn("captured", d)
        self.assertNotIn("blocks", d)
        self.assertNotIn("at", d)           # the held stamp is left alone; the writer stamps its own
        d = check("todo", {"id": "garden-beds_2026", "what": "Plant the beds", "source": SRC, "done": True,
                           "doneAt": "2027-04-10"}, held=self.held, owner="garden")
        self.assertTrue(d["done"])          # its owner closes it, dated
        d = check("todo", {"id": "garden-beds_2026", "source": SRC, "done": True, "doneAt": "2027-04-10"},
                  held=self.held, owner="garden")
        self.assertNotIn("what", d)         # an update says only what changed
        with self.assertRaisesRegex(items.Refused, "needs what"):
            check("todo", {"id": "garden-x", "source": SRC}, owner="garden")

    def test_what_an_owner_never_writes(self):
        held = self.held
        for doc, held, why in [
                ({"id": "beds_2026", "what": "x", "source": SRC}, None, "namespaced"),
                ({"id": "garden-x", "what": "x"}, None, "its own source"),
                ({"id": "garden-x", "what": "x", "source": dict(SRC, owner="kitchen")}, None, "its own source"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC}, dict(held, source=None), "not this owner"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC, "removed": True}, held, "never writes removed"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC, "next": "call"}, held, "never writes next"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC, "nextAt": "z"}, held, "never writes nextAt"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC, "project": "canondb"}, held, "another project"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC, "done": True}, held, "carries doneAt"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC, "done": True, "doneAt": "soon"}, held, "not a date"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC, "done": False}, held, "never reopens"),
                ({"id": "garden-beds_2026", "source": SRC, "captured": TODAY}, held, "never re-dates"),
                ({"id": "garden-x", "what": "x", "source": SRC, "kind": "dictation"}, None, "never a dictation"),
                ({"id": "garden-beds_2026", "what": "x", "source": SRC},
                 dict(held, done=True, removed=True), "removed on the page")]:
            with self.subTest(why=why), self.assertRaisesRegex(items.Refused, why):
                check("todo", doc, held=held, owner="garden")
        # the same project, said again, is not a move
        check("todo", {"id": "garden-beds_2026", "what": "x", "source": SRC, "project": "ordo"},
              held=self.held, owner="garden")


class Lists(unittest.TestCase):
    def test_the_lists_from_the_frozen_rule(self):
        docs = ruledir.read(ruledir.FIXTURE)
        docs[("todo", "i9")] = {"id": "i9", "what": "x"}
        l = items.lists_from(docs, now="2026-10-15T12:00:00Z")   # 08:00 in New York
        self.assertEqual(l["today"], TODAY)
        self.assertIn("ordo", l["projects"])
        self.assertEqual(l["default_project"], "ordo")
        for i in ("gym", "brush", "improv", "i9"):
            self.assertIn(i, l["known"])

    def test_the_cli_checks_and_refuses(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "lists.json").write_text(json.dumps(LISTS))
            (t / "docs.json").write_text(json.dumps([{"collection": "todo", "doc": {
                "id": "garden-x", "what": "x", "source": SRC}}]))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = items.main(["check", "--lists", str(t / "lists.json"), "--docs", str(t / "docs.json"),
                                   "--owner", "garden"])
            self.assertEqual(code, 0, out.getvalue())
            self.assertEqual(json.loads(out.getvalue())[0]["op"], "set")
            # one item may block another captured in the same batch, and each is stamped
            (t / "docs.json").write_text(json.dumps([
                {"collection": "todo", "doc": {"id": "garden-seedlings", "what": "Seedlings", "source": SRC}},
                {"collection": "todo", "doc": {"id": "garden-trellis", "what": "Trellis", "source": SRC,
                                               "blocks": ["garden-seedlings"]}}]))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = items.main(["check", "--lists", str(t / "lists.json"), "--docs", str(t / "docs.json"),
                                   "--owner", "garden", "--now", "2026-10-15T12:00:00Z"])
            self.assertEqual(code, 0, out.getvalue())
            self.assertEqual([x["doc"]["at"] for x in json.loads(out.getvalue())], ["2026-10-15T12:00:00Z"] * 2)
            (t / "docs.json").write_text(json.dumps([{"collection": "todo", "doc": {"id": "x", "what": "x"}}]))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = items.main(["check", "--lists", str(t / "lists.json"), "--docs", str(t / "docs.json"),
                                   "--owner", "garden"])
            self.assertEqual(code, 1)
            self.assertIn("REFUSED", out.getvalue())

    def cli(self, t, docs, owner="garden"):
        (t / "lists.json").write_text(json.dumps(LISTS))
        (t / "docs.json").write_text(json.dumps(docs))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = items.main(["check", "--lists", str(t / "lists.json"), "--docs", str(t / "docs.json"),
                               "--owner", owner, "--now", "2026-10-15T12:00:00Z"])
        return code, out.getvalue()

    def test_a_held_id_is_never_captured_again(self):
        # a set would replace it whole, past the protocol: removed, another owner's, captured once
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            code, out = self.cli(t, [{"collection": "todo", "doc": {
                "id": "garden-beds_2026", "what": "Plant the beds", "source": SRC}}])
            self.assertEqual(code, 1, out)
            self.assertIn("give held", out)
            held = Protocol.held
            code, out = self.cli(t, [{"collection": "todo", "held": held, "doc": {
                "id": "garden-beds_2026", "what": "Plant the beds", "source": SRC}}])
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)[0]["op"], "update")
            code, out = self.cli(t, [{"collection": "todo", "held": dict(held, removed=True), "doc": {
                "id": "garden-beds_2026", "what": "Plant the beds", "source": SRC}}])
            self.assertIn("removed on the page", out)

    def test_an_id_is_written_once_in_a_batch(self):
        with tempfile.TemporaryDirectory() as t:
            doc = {"collection": "todo", "doc": {"id": "garden-x", "what": "x", "source": SRC}}
            code, out = self.cli(Path(t), [doc, doc])
            self.assertEqual(code, 1, out)
            self.assertIn("written twice", out)


if __name__ == "__main__":
    unittest.main()
