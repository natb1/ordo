#!/usr/bin/env python3
"""This repository is public: the fixtures and the docs hold example values only.

The frozen Rule (tools/fixture/rule) and the frozen record (tools/fixture/record) are
invented, and stay so by an allowlist, not a denylist: a list of what to keep out would
itself have to name it. Every string in every fixture document is read, and

- an e-mail address is at an example domain, and a `calendar` is one or null;
- a URL's host is an example host, or a link into this repository on GitHub;
- an address (a `from`, a `to`, or a street address in any text) is the placeholder
  "<place>, <n> <street>, Springfield";
- an IP address is loopback or in a documentation range (never 100.64.0.0/10, a
  tailnet's), and a phone number is a 555-01xx one;
- a `repo` on GitHub is one of the public repositories named here; one on a device
  (`device:/path`, which the page names and never links) is allowed as it stands.

The docs name no one's own page or notebook by link: the keeper's Cadence page is read
from `ordo.local.json`, which git ignores, and the notebook from
`.principal/notebook.json`. The bootstrap manifest's links into the private repository
it was built in say they are.

    python3 -m unittest tools/test_fixture_public.py
"""
import ipaddress
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = [ROOT / "tools" / "fixture" / "rule", ROOT / "tools" / "fixture" / "record"]

EXAMPLE_DOMAINS = {"example.com", "example.org", "example.net"}
REPO_LINK = "https://github.com/natb1/ordo"
PUBLIC_REPOS = {"natb1/ordo", "natb1/CanonDB", "natb1/nix-config", "natb1/blogs"}
DEVICE_REPO = re.compile(r"[a-z][a-z0-9-]*:/[A-Za-z0-9_./-]+")
PLACE = re.compile(r"^(?:[^,]+, )?\d{1,4} [A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*, Springfield$")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
URL = re.compile(r"https?://[^\s\"'<>)\]]+")
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
STREET = re.compile(r"\b\d{1,5} [A-Z][a-z]+(?: [A-Z][a-z]+)* "
                    r"(?:St|Street|Rd|Road|Ave|Avenue|Blvd|Way|Ln|Lane|Dr|Drive|Ct|Court|Pl|Park)\b")
PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?(\d{3})\)?[ .-](\d{3})[ .-](\d{4})(?!\d)")
DOC_NETS = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]


def example_host(host):
    host = (host or "").lower()
    return host.endswith(".example") or host in EXAMPLE_DOMAINS or any(
        host.endswith("." + d) for d in EXAMPLE_DOMAINS)


def allowed_url(url):
    return example_host(urlsplit(url).hostname) or url == REPO_LINK or url.startswith(REPO_LINK + "/")


def strings(value, at=""):
    """Every string leaf, with its field path and the key it stands under."""
    if isinstance(value, str):
        yield at, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(v, f"{at}.{k}" if at else str(k))
            if isinstance(k, str):
                yield f"{at}<key>", k
    elif isinstance(value, list):
        for n, v in enumerate(value):
            yield from strings(v, f"{at}[{n}]")


def findings(name, value):
    """What in one document is not an example value: [(where, why)]."""
    out = []
    for at, text in strings(value):
        field = re.sub(r"\[\d+\]$", "", at).rsplit(".", 1)[-1]
        where = f"{name}:{at}"
        for m in EMAIL.finditer(text):
            if not example_host(m.group(1)):
                out.append((where, f"e-mail {m.group(0)!r} is not at an example domain"))
        for m in URL.finditer(text):
            if not allowed_url(m.group(0)):
                out.append((where, f"URL {m.group(0)!r} is not an example host or this repository"))
        for m in IPV4.finditer(text):
            try:
                ip = ipaddress.ip_address(m.group(1))
            except ValueError:
                continue
            if not any(ip in n for n in DOC_NETS):
                out.append((where, f"IP address {m.group(1)} is not loopback or a documentation range"))
        for m in PHONE.finditer(text):
            if not (m.group(2) == "555" and m.group(3).startswith("01")):
                out.append((where, f"phone number {m.group(0)!r} is not a 555-01xx one"))
        if field in ("from", "to") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):   # a date: a counted period's end
            if not PLACE.match(text):
                out.append((where, f"address {text!r} is not '<place>, <n> <street>, Springfield'"))
        else:
            for m in STREET.finditer(text):
                if not text[m.end():].startswith(", Springfield"):
                    out.append((where, f"street address {m.group(0)!r} is not in Springfield"))
        if field == "repo" and text not in PUBLIC_REPOS and not DEVICE_REPO.fullmatch(text):
            out.append((where, f"repo {text!r} is not one of the public repositories"))
    if isinstance(value, dict):
        out += calendars(name, value)
    return out


def calendars(name, value, at=""):
    out = []
    if isinstance(value, dict):
        for k, v in value.items():
            here = f"{at}.{k}" if at else k
            if k == "calendar" and not (v is None or (isinstance(v, str) and re.fullmatch(
                    r"[A-Za-z0-9._%+-]+@example\.com", v))):
                out.append((f"{name}:{here}", f"calendar {v!r} is not null or an @example.com account"))
            out += calendars(name, v, here)
    elif isinstance(value, list):
        for n, v in enumerate(value):
            out += calendars(name, v, f"{at}[{n}]")
    return out


class TheChecksCatchWhatTheyAreFor(unittest.TestCase):
    """The allowlist refuses each kind of real value, so a pass means something."""

    def assertFinds(self, doc, why):
        self.assertTrue(any(why in w for _, w in findings("x", doc)), findings("x", doc))

    def test_each_kind_of_real_value_is_found(self):
        self.assertFinds({"calendar": "someone@gmail.com"}, "calendar")
        self.assertFinds({"note": "write to someone@mail.net"}, "e-mail")
        self.assertFinds({"directions": "https://maps.google.com/?q=x"}, "URL")
        self.assertFinds({"notebook": "https://claude.ai/artifact/abc"}, "URL")
        self.assertFinds({"note": "on 100.101.102.103"}, "IP address")
        self.assertFinds({"to": "The shop, 12 Elm St, Shelbyville"}, "address")
        self.assertFinds({"note": "meet at 40 Oak Street, Boston"}, "street address")
        self.assertFinds({"note": "call 617-253-1000"}, "phone")
        self.assertFinds({"repo": "natb1/private"}, "repo")
        self.assertFinds({"repo": "someone/their-repo"}, "repo")

    def test_example_values_pass(self):
        self.assertEqual(findings("x", {
            "calendar": "rule@example.com", "directions": "https://maps.example/x",
            "to": "The gym, 6 Market St, Springfield", "from": "1 Example St, Springfield",
            "link": REPO_LINK + "/pull/1", "note": "at 127.0.0.1, or 555-555-0123",
            "repo": "natb1/ordo"}), [])


class TheFixturesHoldExampleValuesOnly(unittest.TestCase):
    def test_every_fixture_document(self):
        docs = [f for d in FIXTURES for f in sorted(d.rglob("*.json"))]
        self.assertTrue(docs)
        found = []
        for f in docs:
            found += findings(str(f.relative_to(ROOT)), json.loads(f.read_text(encoding="utf-8")))
        self.assertEqual(found, [], "\n".join(f"{w}: {why}" for w, why in found))

    def test_the_record_generator(self):
        """make.py writes the record: its source holds example values too."""
        f = ROOT / "tools" / "fixture" / "record" / "make.py"
        found = findings(str(f.relative_to(ROOT)), f.read_text(encoding="utf-8"))
        self.assertEqual(found, [], found)


ARTIFACT_LINK = re.compile(r"https://claude\.ai/(?:code/)?artifact/([A-Za-z0-9-]+)")


class TheDocsNameNoOnesOwnPage(unittest.TestCase):
    def test_no_artifact_is_linked_by_id(self):
        """README and the skill give a placeholder, never a page's or a notebook's id."""
        for f in [ROOT / "README.md", *sorted((ROOT / ".claude").rglob("*.md"))]:
            for m in ARTIFACT_LINK.finditer(f.read_text(encoding="utf-8")):
                self.fail(f"{f.relative_to(ROOT)} links an artifact by id: {m.group(0)}")

    def test_the_page_is_read_from_an_ignored_local_file(self):
        skill = (ROOT / ".claude" / "skills" / "ordo" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ordo.local.json", skill)
        self.assertIn(".principal/notebook.json", skill)
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
        self.assertIn("ordo.local.json", ignored)


class TheManifestSaysWhereItsPullRequestsAre(unittest.TestCase):
    def test_a_private_link_is_said_to_be_private(self):
        manifest = json.loads((ROOT / ".principal" / "bootstrap.json").read_text(encoding="utf-8"))
        links = [a["pull_request"] for a in manifest["applications"] if a.get("pull_request")]
        for link in links:
            self.assertRegex(link, r"^https://github\.com/natb1/(ordo|private)/pull/\d+$")
        if any("/natb1/private/" in link for link in links):
            note = manifest.get("pull_requests", "")
            self.assertIn("natb1/private", note)
            self.assertIn("private repository", note)
            self.assertIn("not readable", note)
        for a in manifest["applications"]:  # the entries keep the plugin's shape
            self.assertLessEqual(set(a), {"question", "application", "files", "pull_request", "rounds"})


if __name__ == "__main__":
    unittest.main()
