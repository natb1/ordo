#!/usr/bin/env python3
"""tradition/check.py: the note on un-audited sources names sources, and the
registry is read from the export it is given, strictly.

    python3 -m unittest tools/test_tradition.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from ruledir import loads  # noqa: E402

REGISTRY = ROOT / "tools" / "fixture" / "registry.json"
SOURCES = loads(REGISTRY.read_text(encoding="utf-8"))["sources"]
UNAUDITED = sorted(k for k, v in SOURCES.items() if v.get("verified") == "unverified"
                   and str(v.get("status", "")).upper() != "REJECTED")


def check(export, *extra):
    out = subprocess.run([sys.executable, "-B", str(ROOT / "tradition" / "check.py"), "--rule", str(export), *extra],
                         capture_output=True, text=True, cwd=ROOT)
    return out.returncode, out.stdout


def rule_citing(t, key):
    (Path(t) / "rule").mkdir()
    (Path(t) / "rule" / "office.json").write_text(json.dumps({"steps": [f"as [{key}] has it"]}))


class UnauditedNote(unittest.TestCase):
    def test_a_citation_in_a_list_field_is_named_by_its_key_not_its_index(self):
        """A Rule field path carries brackets of its own (`steps[0]`): the note takes the
        key from the citation, never from the first bracket in the warning's line."""
        key = UNAUDITED[0]
        with tempfile.TemporaryDirectory() as t:
            rule_citing(t, key)
            code, out = check(t)
        self.assertEqual(code, 0, out)
        note = [line for line in out.splitlines() if "un-audited source(s):" in line]
        self.assertEqual(len(note), 1, out)
        named = note[0].split(": ", 1)[1].split(", ")
        self.assertIn(key, named)
        self.assertNotIn("0", named)
        self.assertTrue(set(named) <= set(SOURCES), named)


class TheRegistryIsAnExport(unittest.TestCase):
    """The registry is the parties' works on the notebook, exported; the check reads the
    file it is given and keeps none of its own beyond the frozen copy."""

    def write(self, t, text):
        path = Path(t) / "registry.json"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_key_the_export_defines_passes_and_one_it_does_not_fails(self):
        with tempfile.TemporaryDirectory() as t:
            rule_citing(t, "NEW-SOURCE-2026")
            code, out = check(t)
            self.assertEqual(code, 1, out)
            self.assertIn("[NEW-SOURCE-2026] is not in the registry", out)
            registry = dict(SOURCES, **{"NEW-SOURCE-2026": {"work": "A new work", "verified": "web-2026-10-29",
                                                           "party": "Someone"}})
            path = self.write(t, json.dumps({"sources": registry}))
            code, out = check(t, "--registry", str(path))
            self.assertEqual(code, 0, out)

    def test_a_key_given_twice_in_the_export_is_an_error_not_a_last_one_wins(self):
        with tempfile.TemporaryDirectory() as t:
            rule_citing(t, "RB-5")
            path = self.write(t, '{"sources": {"RB-5": {"work": "a"}, "RB-5": {"work": "b"}}}')
            code, out = check(t, "--registry", str(path))
            self.assertEqual(code, 1, out)
            self.assertIn("duplicate key 'RB-5'", out)

    def test_a_rejected_source_still_fails(self):
        rejected = sorted(k for k, v in SOURCES.items() if str(v.get("status", "")).upper() == "REJECTED")
        self.assertTrue(rejected)
        with tempfile.TemporaryDirectory() as t:
            rule_citing(t, rejected[0])
            code, out = check(t)
        self.assertEqual(code, 1, out)
        self.assertIn("is REJECTED", out)


if __name__ == "__main__":
    unittest.main()
