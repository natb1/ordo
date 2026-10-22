#!/usr/bin/env python3
"""tradition/check.py: the note on un-audited sources names sources.

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
from ruleyaml import load  # noqa: E402

SOURCES = load(ROOT / "tradition" / "sources.yaml")["sources"]
UNAUDITED = sorted(k for k, v in SOURCES.items() if v.get("verified") == "unverified"
                   and str(v.get("status", "")).upper() != "REJECTED")


def check(export):
    out = subprocess.run([sys.executable, "-B", str(ROOT / "tradition" / "check.py"), "--rule", str(export)],
                         capture_output=True, text=True, cwd=ROOT)
    return out.returncode, out.stdout


class UnauditedNote(unittest.TestCase):
    def test_a_citation_in_a_list_field_is_named_by_its_key_not_its_index(self):
        """A Rule field path carries brackets of its own (`steps[0]`): the note takes the
        key from the citation, never from the first bracket in the warning's line."""
        key = UNAUDITED[0]
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "rule").mkdir()
            (Path(t) / "rule" / "office.json").write_text(json.dumps({"steps": [f"as [{key}] has it"]}))
            code, out = check(t)
        self.assertEqual(code, 0, out)
        note = [line for line in out.splitlines() if "un-audited source(s):" in line]
        self.assertEqual(len(note), 1, out)
        named = note[0].split(": ", 1)[1].split(", ")
        self.assertIn(key, named)
        self.assertNotIn("0", named)
        self.assertTrue(set(named) <= set(SOURCES), named)


if __name__ == "__main__":
    unittest.main()
