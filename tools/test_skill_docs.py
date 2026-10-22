#!/usr/bin/env python3
"""The skill's reference and its own sections agree on where an item lives and how a
record write is made, and where a dictation runs.

    python3 -m unittest tools/test_skill_docs.py
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / ".claude" / "skills" / "ordo" / "SKILL.md").read_text(encoding="utf-8")
BLOCKERS = (ROOT / ".claude" / "skills" / "ordo" / "reference" / "blockers.md").read_text(encoding="utf-8")


def section(text, heading):
    m = re.search(r"^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, heading
    return m.group(1)


class Blockers(unittest.TestCase):
    def test_a_blocker_lives_in_todo_not_inbox(self):
        """The skill: `inbox` is read by nothing; a TODO item is `todo/<id>`."""
        self.assertIn("`todo/<id>`", BLOCKERS)
        self.assertNotIn("the store's `inbox`", BLOCKERS)
        self.assertIn("read by nothing", SKILL)

    def test_closing_one_goes_through_the_record_gate(self):
        """The skill: every record write goes through tools/record.py, whose close
        also closes breakdowns/<id>. Never a bare ArtifactData write."""
        closing = section(BLOCKERS, "Closing one")
        self.assertIn("tools/record.py", closing)
        self.assertIn("`close`", closing)
        self.assertIn("breakdowns/<id>", closing)
        self.assertNotIn("ArtifactData", closing)
        self.assertIn("goes through the record gate, `tools/record.py`, never by hand", " ".join(SKILL.split()))


class Dictations(unittest.TestCase):
    def test_the_rules_own_dictations_run_in_this_repository(self):
        """The Rule's notebook is named by this repository's .principal/notebook.json,
        so its dictations run here, natb1/ordo, not wherever an older rule.repo points."""
        text = section(SKILL, "The TODO list and dictations")
        para = text[text.index("**Dictations.**"):text.index("**Owned items.**")]
        self.assertIn("`natb1/ordo`", para)
        self.assertIn(".principal/notebook.json", para)
        self.assertIn("through the\ngate", para)
        self.assertTrue((ROOT / ".principal" / "notebook.json").is_file())


if __name__ == "__main__":
    unittest.main()
