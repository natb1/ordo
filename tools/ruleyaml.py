#!/usr/bin/env python3
"""Load yaml strictly: a key given twice in one mapping is an error.

yaml.safe_load keeps the last of two equal keys and says nothing. When the Rule was
yaml, a merge that left two `done:` lists in its TODO file dropped one of them whole,
and a second `when:` on an item replaced the first — both passed every check. The
Rule is store documents now, and tools/ruledir.py holds them to the same. This loads
the one yaml file left, tradition/sources.yaml: tradition/check.py reads it through
here, and preflight runs this over it.

    python3 tools/ruleyaml.py FILE...    # fail if any file will not load strictly
"""
import sys

try:
    import yaml
except ImportError:
    sys.exit("needs pyyaml: pip install pyyaml")


class StrictLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    # Only the mapping's own keys can repeat. A merge (<<) brings keys in that the
    # mapping may override, as merges are meant to, so it is left to flatten after.
    seen = {}
    for k, _ in node.value:
        if k.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(k, deep=True)
        try:
            hash(key)
        except TypeError:
            continue  # the base constructor refuses an unhashable key with its own message
        if key in seen:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"found duplicate key {key!r} (first at line {seen[key].line + 1})", k.start_mark)
        seen[key] = k.start_mark
    return loader.construct_mapping(node, deep=True)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def loads(text):
    return yaml.load(text, Loader=StrictLoader)


def load(path):
    with open(path, encoding="utf-8") as f:  # a file, so an error names it
        return yaml.load(f, Loader=StrictLoader)


def main():
    bad = 0
    for f in sys.argv[1:]:
        try:
            load(f)
            print("ok", f)
        except yaml.YAMLError as e:
            print(f"ERROR  {f}: {e}")
            bad = 1
    return bad


if __name__ == "__main__":
    sys.exit(main())
