#!/usr/bin/env python3
"""The gate every write to the Rule passes: check it, compile it, hand back a batch.

The Rule lives in the page's store (tools/ruledir.py), and nothing runs there
when a document changes. So the check runs here, before the write. /ordo exports
the store with ArtifactData (`out_dir`), says what it means to change, and sends
only what this prints. A change that is refused writes nothing.

    python3 tools/gate.py DIR --change FILE --versions FILE --out OUT

DIR       the export: <collection>/<doc_id>.json, as ArtifactData leaves it
--change  a JSON list of {op, collection, doc_id, data}: `set` replaces a document,
          `update` merges into it ({"__delete__": true} removes a field), `delete`
          removes it. Without it nothing changes and the Rule is compiled again.
          A document the page also writes (projects/<id>) takes only an update of
          its `rule` field. TODO and periodic items are not the Rule's: /ordo
          writes todo/<id> and periodic/<id> directly.
--snapshot DATE  also write snapshots/<DATE>, the Rule as it stands: the weekly
          review's copy, kept apart from snapshots/last, which every write replaces
          and a --snapshot run writes too, with no change, so that --counts ride on
          it. A second run of one date replaces snapshots/<DATE>: the export lists
          `snapshots`, and both are pinned to the versions it gave
--restore FILE  make the Rule what a snapshot holds (FILE is a snapshots/<id>
          document as exported), in place of --change: checked like any change. An
          Office item the snapshot gives no guard takes the one rule/office gives it
          now, by id, and the run says which
--counts FILE  the counts read at this review, as tools/counts.py --json prints
          them: carried on snapshots/last and on the dated snapshot, so that a later
          reading can tell what a change did (hypomnemata › record, the change ledger).
          They are read as of the date the snapshot is kept by, and only what the
          counts tool printed is taken
--versions  a JSON map {"<collection>/<doc_id>": version}, from the export's result;
          each write to a document named there is pinned to that version. With
          --out it names every document of the Rule the export holds, and every
          other document a write replaces (snapshots/last, once it exists): the
          store refuses a whole batch for one write to a document that exists and
          carries no version
--out     where the batch goes: OUT/batch.json is ArtifactData's `writes`, each
          entry naming its document's file under OUT. A directory of its own,
          never the export or inside it; a batch an earlier run left there goes

It runs the compiler's refusals (compiler.py) and the capacity check, strictly.
On a pass the batch holds the changed documents, `rule/compiled` (the constants the
page reads) where it changed, and `snapshots/last` (the whole Rule as it now
stands, the way back from a write that did not come through here).
"""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import ruledir
import compiler
import items

TOOLS = Path(__file__).resolve().parent
# Where the Rule is. In these the document is the Rule's; in NESTED the page writes
# beside it, and the Rule is the one field `rule`.
OWNED = ("commitments", "backlog")
NESTED = ("projects",)
COMPILED, SNAPSHOT = ("rule", "compiled"), ("snapshots", "last")
DELETE = {"__delete__": True}
MOST = 50   # entries in one ArtifactData batch


# One refusal for every gate: the item contract's, so that tools/record.py, which
# calls both, catches either with one `except`.
Refused = items.Refused


def raw(docs):
    """The Rule's own documents out of an export, the page's fields left behind."""
    out = {}
    for (c, i), data in docs.items():
        if c == "rule" and i in ruledir.SINGLE or c in OWNED:
            out[(c, i)] = data
        elif c in NESTED and data.get("rule") is not None:
            out[(c, i)] = {"id": i, "rule": data["rule"]}
    return out


def merged(old, new):
    """`new` merged into `old` as the store's update does it."""
    out = dict(old)
    for k, v in new.items():
        if v == DELETE:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merged(out[k], v)
        else:
            out[k] = strip(v)
    return out


def strip(v):
    if isinstance(v, dict):
        return {k: strip(x) for k, x in v.items() if x != DELETE}
    return v


def apply(docs, changes):
    docs = copy.deepcopy(docs)
    if not isinstance(changes, (list, tuple)):
        raise Refused("a change is a JSON list of {op, collection, doc_id, data}")
    for n, ch in enumerate(changes):
        try:
            op, key = ch["op"], (ch["collection"], ch["doc_id"])
        except (KeyError, TypeError):
            raise Refused(f"change {n}: needs op, collection and doc_id")
        if not (isinstance(key[0], str) and isinstance(key[1], str)):
            raise Refused(f"change {n}: collection and doc_id are text")
        # What raw() takes for the Rule is all a change may touch: a rule/<id> no tool
        # reads would be written, and never seen here again to be checked or deleted.
        if not (key[0] in OWNED + NESTED or key[0] == "rule" and key[1] in ruledir.SINGLE):
            raise Refused(f"change {n}: {'/'.join(key)} is not a document of the Rule")
        if not ruledir.named(key[1]):
            raise Refused(f"change {n}: {key[1]!r} is not a document's id")
        if op in ("set", "update") and not isinstance(ch.get("data"), dict):
            raise Refused(f"change {n}: {'/'.join(key)} needs data, an object")
        if key[0] in NESTED and (op != "update" or set(ch.get("data") or {}) != {"rule"}):
            raise Refused(f"change {n}: {'/'.join(key)} is the page's too; update its `rule` field only")
        if op == "delete":
            if docs.pop(key, None) is None:
                raise Refused(f"change {n}: {'/'.join(key)} is not there to delete")
        elif op == "set":
            docs[key] = ch["data"]
        elif op == "update":
            docs[key] = merged(docs.get(key) or ({"id": key[1]} if key[0] in NESTED else {}), ch["data"])
            if key[0] in NESTED and "rule" not in docs[key]:
                del docs[key]
        else:
            raise Refused(f"change {n}: op {op!r} is not set, update or delete")
    return docs


def patch(old, new):
    """The update that turns `old` into `new`: changed fields, and a delete for each
    one gone. A list is written whole."""
    out = {}
    for k in old:
        if k not in new:
            out[k] = DELETE
    for k, v in new.items():
        if k not in old:
            out[k] = v
        elif isinstance(v, dict) and isinstance(old[k], dict):
            p = patch(old[k], v)
            if p:
                out[k] = p
        elif v != old[k]:
            out[k] = v
    return out


def sound(cand):
    """Every document of a candidate is an object under a name the store takes. The
    name is a file's too (in the export, under --out, in the copy the capacity check
    reads), and a restore takes it from a snapshot's content: one that is a path
    would be written wherever it points."""
    for (c, i), data in cand.items():
        if not (ruledir.named(c) and ruledir.named(i)):
            raise Refused(f"{c!r}/{i!r} is not a document's name")
        if not isinstance(data, dict):
            raise Refused(f"{c}/{i}: a document is an object")
        if marked(data):
            raise Refused(f"{c}/{i}: a {DELETE} is taken only in a map of an update, never in a "
                          "list or a set: give the list whole, without what is to go")


def marked(v):
    """Whether a removal marker is left in a value, where the store would refuse it."""
    if v == DELETE:
        return True
    if isinstance(v, dict):
        return any(marked(x) for x in v.values())
    if isinstance(v, list):
        return any(marked(x) for x in v)
    return False


def whole(docs):
    """Refused where the export lacks a collection snapshots/last holds documents of:
    a collection not listed reads as an empty one, and would be compiled as none."""
    last = docs.get(SNAPSHOT)
    if not isinstance(last, dict):
        return
    held = {c for c, _ in raw(docs)}
    had = {d.get("collection") for d in last.get("docs") or [] if isinstance(d, dict)}
    gone = sorted(c for c in had - held if c in OWNED + NESTED)
    if gone:
        raise Refused("the export holds no " + ", ".join(gone) + ", which snapshots/last has: "
                      "list every collection of the Rule into the export")


def check(cand):
    """The compiled constants, or Refused with every reason."""
    try:
        r = ruledir.assemble(cand)
    except ruledir.RuleDirError as e:
        raise Refused(str(e))
    compiler.errors.clear()
    try:
        consts = compiler.compile(r)
    except (KeyError, TypeError, AttributeError) as e:
        raise Refused("\n".join(compiler.errors + [f"the Rule will not compile: {type(e).__name__}: {e}"]))
    if compiler.errors:
        raise Refused("\n".join(compiler.errors))
    with tempfile.TemporaryDirectory() as t:
        ruledir.write(t, cand)
        p = subprocess.run([sys.executable, str(TOOLS / "check_capacity.py"), "--strict"],
                           env=dict(os.environ, **{ruledir.ENV: t}), capture_output=True, text=True)
    if p.returncode:
        raise Refused((p.stdout + p.stderr).rstrip())
    return compiler.stored(consts)


def restored(snap, current=None, said=None):
    """The Rule a snapshot holds, as raw() gives one. A snapshot taken before the
    Office items named their guards (hypomnemata › unprompted, the guard on each
    item) gives an item none: it takes the guard `current` (rule/office as the store
    holds it now) gives the same id, and each so carried is said."""
    try:
        out = raw({(d["collection"], d["doc_id"]): copy.deepcopy(d["data"]) for d in snap["docs"]})
    except (KeyError, TypeError, AttributeError):
        raise Refused("that is not a snapshot: it has no docs")
    guards = {it["id"]: it["guard"] for it in office_items(current) if "guard" in it}
    for it in office_items(out.get(("rule", "office"))):
        if "guard" not in it and it["id"] in guards:
            it["guard"] = guards[it["id"]]
            if said is not None:
                said.append(f"{it['id']}: the snapshot names no guard; carried over from rule/office: {guards[it['id']]}")
    return out


def office_items(office):
    """Every item of a rule/office document and each of their parts, as they stand
    in it (a change to one is a change to the document)."""
    out = []
    if not isinstance(office, dict) or not isinstance(office.get("anchors"), list):
        return out
    for an in office["anchors"]:
        for it in (an.get("items") if isinstance(an, dict) else None) or []:
            if isinstance(it, dict) and isinstance(it.get("id"), str):
                out.append(it)
                out += [k for k in it.get("children") or [] if isinstance(k, dict) and isinstance(k.get("id"), str)]
    return out


def gate(docs, changes=(), now=None, restore=None, keep=None, counts=None, said=None):
    """The writes that carry a checked change: [(op, (collection, doc_id), data)].
    `restore` is a snapshot to go back to, in place of changes; `keep` names a
    snapshot to write beside snapshots/last (the weekly one, by its date), which is
    written with it; `counts` is what the counts tool read at this review, carried
    on every snapshot written. What is done that is not a refusal is added to `said`."""
    if keep is not None and not (isinstance(keep, str) and compiler.YMD.fullmatch(keep)):
        raise Refused(f"a snapshot is kept by its date, YYYY-MM-DD, not {keep!r}")
    if counts is not None:
        if not isinstance(counts, dict) or not {"as_of", "under_review"} <= set(counts):
            raise Refused("--counts is what tools/counts.py --json prints: a JSON object naming as_of and under_review")
        if keep and counts.get("as_of") != keep:
            raise Refused(f"--counts were read as of {counts.get('as_of')} and the snapshot is dated {keep}: "
                          "run tools/counts.py again, at this sitting")
    before = raw(docs)
    cand = restored(restore, before.get(("rule", "office")), said) if restore is not None else apply(before, changes)
    sound(cand)
    compiled = check(cand)
    writes = []
    for key in sorted(set(before) | set(cand)):
        old, new = before.get(key), cand.get(key)
        if new == old:
            continue
        if key[0] in NESTED and key in docs:
            # The page's document: only the `rule` field is touched.
            p = patch({"rule": old["rule"]} if old else {}, {"rule": new["rule"]} if new else {})
            writes.append(("update", key, p))
        elif new is None:
            writes.append(("delete", key, None))
        else:
            writes.append(("set", key, new))
    if docs.get(COMPILED) != compiled:
        writes.append(("set", COMPILED, compiled))
    at = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if writes or keep:
        writes.append(("set", SNAPSHOT, snapshot(cand, at, counts)))
    if keep:
        if ("snapshots", keep) in docs and said is not None:
            said.append(f"snapshots/{keep} is held already: this run replaces it")
        writes.append(("set", ("snapshots", keep), snapshot(cand, at, counts)))
    return writes


def snapshot(rule_docs, at, counts=None):
    """The Rule as it stands, and the counts it was read against where the review
    gave them: two snapshots' counts side by side are what a change did."""
    out = {"at": at, "docs": [{"collection": c, "doc_id": i, "data": d}
                              for (c, i), d in sorted(rule_docs.items())]}
    if counts is not None:
        out["counts"] = counts
    return out


def emit(writes, versions, out, held=()):
    """Lay the batch out for ArtifactData: OUT/batch.json and a file per document.
    `held` is the documents the export holds. The store refuses a whole batch for
    one write to a document that exists and carries no version, so such a batch is
    refused here, and before anything is laid out."""
    for op, (c, i), _ in writes:
        if f"{c}/{i}" in versions:
            continue
        if op == "delete":
            raise Refused(f"{c}/{i}: a delete needs the document's version")
        if (c, i) in held:
            raise Refused(f"{c}/{i}: the store holds it, so the write needs its version (--versions)")
    out = Path(out)
    batch = []
    for op, (c, i), data in writes:
        e = {"op": op, "collection": c, "doc_id": i}
        if data is not None:
            f = out / c / (i + ".json")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            e["file_path"] = str(f.resolve())
        if f"{c}/{i}" in versions:
            e["if_version"] = versions[f"{c}/{i}"]
        batch.append(e)
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch.json").write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
    return batch


def given(path, what):
    """A JSON file named on the command line, or Refused with why it will not read."""
    try:
        return ruledir.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, ruledir.RuleDirError) as e:
        raise Refused(f"{what} {path}: {e}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("--change")
    ap.add_argument("--snapshot")
    ap.add_argument("--restore")
    ap.add_argument("--versions")
    ap.add_argument("--counts")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    try:
        if args.out:
            out, export = Path(args.out).resolve(), Path(args.dir).resolve()
            # The batch is laid out as the export is: in the export it would be read
            # back as the store's own documents by the next run.
            if out == export or export in out.parents:
                raise Refused(f"--out {args.out} is the export or inside it; give the batch a directory of its own")
            # A run that is refused, or finds nothing to write, leaves no batch of an
            # earlier run in OUT to be sent in its place.
            try:
                (out / "batch.json").unlink(missing_ok=True)
            except OSError as e:
                raise Refused(f"--out {args.out}: {e}")
        docs = ruledir.read(args.dir)
        changes = given(args.change, "--change") if args.change else []
        versions = given(args.versions, "--versions") if args.versions else {}
        if not isinstance(versions, dict):
            raise Refused('--versions is a JSON map {"<collection>/<doc_id>": version}')
        if args.change and args.restore:
            raise Refused("--change or --restore, not both")
        snap = given(args.restore, "--restore") if args.restore else None
        counts = given(args.counts, "--counts") if args.counts else None
        if args.out:
            # Every export gives each document its version. A document of the Rule
            # with none was not in this export: a file an earlier one left in the
            # directory (out_dir removes nothing), or a version not copied.
            # snapshots/last and a dated snapshot of this date are replaced whole, so
            # each the export holds is pinned too.
            pinned = {COMPILED, SNAPSHOT} | ({("snapshots", args.snapshot)} if args.snapshot else set())
            unread = sorted("/".join(k) for k in set(raw(docs)) | (pinned & set(docs))
                            if "/".join(k) not in versions)
            if unread:
                raise Refused("--versions does not name " + ", ".join(unread) + ": export into a new "
                              "directory, and give every document's version")
        whole(docs)
        said = []
        writes = gate(docs, changes, restore=snap, keep=args.snapshot, counts=counts, said=said)
        for line in said:
            print("said    " + line)
        if not writes:
            print("ok  nothing to write: the store holds this Rule, compiled"
                  + ("; the counts ride on no snapshot" if counts is not None else ""))
            return 0
        if len(writes) > MOST:
            raise Refused(f"{len(writes)} writes, and one batch takes {MOST}; make the change in parts")
        if not args.out:
            for op, key, _ in writes:
                print(f"would {op:<7}{'/'.join(key)}")
            print("ok  passed; give --out to write the batch")
            return 0
        batch = emit(writes, versions, args.out, held=set(docs))
    except (Refused, ruledir.RuleDirError) as e:
        for line in str(e).splitlines():
            print("REFUSED ", line)
        print("nothing is to be written")
        return 1
    for e in batch:
        pin = f"  if_version {e['if_version']}" if "if_version" in e else "  (new)"
        print(f"{e['op']:<8}{e['collection']}/{e['doc_id']}{pin}")
    print(f"ok  {len(batch)} writes in {Path(args.out) / 'batch.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
