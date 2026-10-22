#!/usr/bin/env python3
"""The Rule read from a directory of store documents.

    python3 -m unittest tools/test_ruledir.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ruledir  # noqa: E402

SINGLE = {("rule", n): {} for n in ruledir.SINGLE}


def docs(**more):
    d = dict(SINGLE)
    d[("rule", "office")] = {"anchors": [{"key": "morning", "bell": "07:00"}, {"key": "evening", "bell": "20:00"},
                                         {"key": "midday", "bell": "11:00"}]}
    d.update({tuple(k.split("/")): v for k, v in more.items()})
    return d


class Load(unittest.TestCase):
    def test_a_directory_reads_back_what_was_written(self):
        with tempfile.TemporaryDirectory() as t:
            ruledir.write(t, docs())
            self.assertEqual(ruledir.read(t), docs())

    def test_the_blocks_keep_the_order_of_their_list(self):
        # the store sorts a map's keys, so the order is the list's
        self.assertEqual(list(ruledir.assemble(docs()).anchors["anchors"]), ["morning", "evening", "midday"])

    def test_a_collection_is_ordered_by_seq(self):
        r = ruledir.assemble(docs(**{"commitments/a": {"id": "a", "seq": 1}, "commitments/b": {"id": "b", "seq": 0}}))
        self.assertEqual(r.anchors["commitments"], [{"id": "b"}, {"id": "a"}])

    def test_the_rule_is_one_field_of_a_document_the_page_also_writes(self):
        r = ruledir.assemble(docs(**{"projects/p": {"id": "p", "thread": "x", "rule": {"id": "p", "seq": 0, "repo": "o/p"}},
                                     "projects/q": {"id": "q", "thread": "the page's alone"}}))
        self.assertEqual(r.docket["projects"], [{"id": "p", "repo": "o/p"}])

    def test_the_frozen_rule_loads(self):
        r = ruledir.load(ruledir.FIXTURE)
        self.assertEqual(list(r.anchors["anchors"]), ["morning", "midday", "vespers", "evening"])
        self.assertTrue(r.anchors["commitments"] and r.docket["projects"] and r.backlog["items"])


class Refusals(unittest.TestCase):
    def test_a_key_given_twice(self):
        with self.assertRaises(ruledir.RuleDirError):
            ruledir.loads('{"a": 1, "a": 2}')

    def test_a_missing_document(self):
        d = docs()
        del d[("rule", "ledger")]
        with self.assertRaisesRegex(ruledir.RuleDirError, "rule/ledger is missing"):
            ruledir.assemble(d)

    def test_an_id_that_is_not_the_document_name(self):
        with self.assertRaises(ruledir.RuleDirError):
            ruledir.assemble(docs(**{"commitments/a": {"id": "b", "seq": 0}}))

    def test_a_block_given_twice(self):
        d = docs()
        d[("rule", "office")] = {"anchors": [{"key": "morning"}, {"key": "morning"}]}
        with self.assertRaises(ruledir.RuleDirError):
            ruledir.assemble(d)

    def test_a_name_that_is_a_path_is_not_written(self):
        # a document's name is a file's name, and one may come out of a snapshot's content
        for key in (("backlog", "../elsewhere"), ("backlog", "sub/dir"), ("backlog", ".."), ("../up", "a")):
            with tempfile.TemporaryDirectory() as t:
                with self.assertRaises(ruledir.RuleDirError):
                    ruledir.write(t, {key: {}})
                self.assertEqual(list(Path(t).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
