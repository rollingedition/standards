"""Runs one example inside its pinned runtime and reports what it actually ran against.

Copied next to the examples and run as `python -I .re_harness.py EXAMPLE.py`. The example's stdout
passes straight through; the report (Python version, the distributions it loaded and the ones it
imports directly) goes to the file named by RE_EXAMPLE_REPORT. Standard library only, and it must run
on every Python version a book may pin.
"""
import ast
import importlib.metadata as metadata
import json
import os
import platform
import re
import runpy
import sys
import traceback


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _imported(source):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def _local_files(folder, top):
    """The .py files of a module or package that lives next to the example, or [] if it isn't local."""
    package, module = os.path.join(folder, top), os.path.join(folder, top + ".py")
    if os.path.isdir(package):
        return [os.path.join(root, f) for root, _, files in os.walk(package) for f in files if f.endswith(".py")]
    return [module] if os.path.isfile(module) else []


def direct_imports(source, folder="."):
    """Top-level names the example imports. Imports of its own local modules, such as examples/lib/, are
    followed, so an example that reaches pandas through lib still reports pandas."""
    tops, local = set(), set()
    for top in _imported(source):
        files = _local_files(folder, top)
        if files:
            local.update(files)
        else:
            tops.add(top)
    for path in sorted(local):
        with open(path, encoding="utf-8") as f:
            tops.update(top for top in _imported(f.read()) if not _local_files(folder, top))
    return tops


def main():
    path = sys.argv[1]
    report = os.environ.pop("RE_EXAMPLE_REPORT")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    code = 0
    sys.argv = [path]
    # -I keeps the user's environment out, and with it the script's own folder; put that back, as a plain
    # `python example.py` would, so examples can import shared modules such as examples/lib/.
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    dists = metadata.packages_distributions()
    loaded = {}
    for name in list(sys.modules):
        for dist in dists.get(name.split(".")[0], []):
            try:
                loaded[norm(dist)] = metadata.version(dist)
            except metadata.PackageNotFoundError:
                pass
    direct = sorted({norm(d) for top in direct_imports(source, os.path.dirname(os.path.abspath(path))) for d in dists.get(top, [])})
    with open(report, "w", encoding="utf-8") as f:
        json.dump({"python": platform.python_version(), "loaded": loaded, "direct": direct, "exit": code}, f)
    sys.exit(code)


if __name__ == "__main__":
    main()
