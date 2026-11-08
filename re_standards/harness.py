"""Runs one example inside its pinned runtime and reports what it actually ran against.

Copied next to the examples and run as `python -I .re_harness.py EXAMPLE.py`. The example's stdout
passes straight through; the report (Python version, the distributions it loaded and the ones it
imports directly) goes to the file named by RE_EXAMPLE_REPORT. Standard library only, and it must run
on every Python version a book may pin.

`python -I .re_harness.py --metadata` runs no example: it reports what the runtime has installed (installed()), which
the choice of the examples a change to the pins could affect reads (affected.py).
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

METADATA = "--metadata"
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def import_names(dist):
    """The top-level names a distribution can be imported as: its top_level.txt and the top-level modules and packages
    its RECORD lists, together. None when neither says, or when it installs a .pth file, which can put anything on
    the path."""
    import inspect                                  # only here: an example's run never loads more than it did
    names = set()
    text = dist.read_text("top_level.txt")
    if text is not None:
        names.update(line.strip() for line in text.splitlines() if line.strip())
    files = dist.files
    if files is None:
        return sorted(names) if text is not None else None
    for f in files:
        parts = f.parts
        if not parts or parts[0] in ("..", "__pycache__") or parts[0].endswith((".dist-info", ".egg-info", ".data")):
            continue
        if parts[-1].endswith(".pth"):
            return None
        if len(parts) > 1:
            names.add(parts[0])
        else:
            module = inspect.getmodulename(parts[0])
            if module:
                names.add(module)
    return sorted(names)


def installed():
    """What the runtime has installed: each distribution's version, its import names (import_names) and every
    distribution it requires, whatever the markers and extras say, so a library that only sometimes uses another still
    counts as using it. Also the standard library's module names, where this Python lists them."""
    dists = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name or norm(name) in dists:         # the first one on the path is the one an import finds
            continue
        requires = sorted({norm(m.group(1)) for r in (dist.requires or []) for m in [REQUIREMENT.match(r)] if m})
        pth = any(f.parts and f.parts[-1].endswith(".pth") for f in dist.files or [])
        dists[norm(name)] = {"version": dist.version, "imports": import_names(dist), "requires": requires, "pth": pth}
    names = getattr(sys, "stdlib_module_names", None)
    stdlib = sorted(set(names) | set(sys.builtin_module_names)) if names is not None else None
    return {"python": platform.python_version(), "stdlib": stdlib, "distributions": dists}


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


def loopback_up():
    """Bring the loopback interface up where a fresh network namespace left it down. `unshare -rn` (the venv backend)
    does, and a container's --network none doesn't, so without this an example that serves and calls 127.0.0.1, such
    as a server and its client, would pass in one backend and fail in the other. Nothing beyond the machine becomes
    reachable. Linux only; where loopback is already up, or the right to change it is missing, it does nothing."""
    if not sys.platform.startswith("linux"):
        return
    import fcntl
    import socket
    import struct
    get_flags, set_flags, up = 0x8913, 0x8914, 0x1          # SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            flags = struct.unpack("16sh", fcntl.ioctl(s, get_flags, struct.pack("16sh", b"lo", 0)))[1]
            if not flags & up:
                fcntl.ioctl(s, set_flags, struct.pack("16sh", b"lo", flags | up))
    except OSError:
        pass


def main():
    path = sys.argv[1]
    report = os.environ.pop("RE_EXAMPLE_REPORT")
    if path == METADATA:
        with open(report, "w", encoding="utf-8") as f:
            json.dump(installed(), f)
        return
    loopback_up()
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
