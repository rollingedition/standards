"""Which examples a change could affect: `re-check examples --affected --base-ref REF` runs only those.

An example's output depends on its own code, the local modules it imports, the libraries it imports and what they in
turn use, the files it reads, and the runtime. Against the base (the commit whose examples passed, such as a pull
request's base), an example runs again when the change touches:

- **its own files:** examples/{id}.py or examples/{id}.out;
- **a local module it imports,** directly or through another: any .py file in a folder beside the examples, such as
  examples/lib/, or an example file another imports by name. Imports are read with `ast` from the example and from
  every local module it reaches, relative imports included;
- **a pin for a distribution it imports,** or one that a distribution it imports requires, directly or not, extras
  included: a version that changed in examples/requirements.txt. Import names come from the runtime's own metadata
  (top_level.txt and RECORD), which the harness reads inside the runtime;
- **a pin for a distribution it loaded when it last ran,** when a record of that run is given (the latest edition's
  sections.json, or an examples report): the harness records every distribution an example loaded, so a library that
  imports another only when it's installed is seen too.

The harness's record is used only to add examples, never to leave one out: it comes from the last run, not the base,
and an example that starts another program loads what that program does without the harness seeing it.

When unsure, every example runs, and the selection says why:
- examples/.python-version changed: a new Python;
- a pin was added or removed: what's installed changed, and a library can import another only once it's there;
- a file under examples/data/ changed: what each example reads isn't recorded;
- any other file beside the examples changed, such as a SQL file, a module's data file or requirements.in: any
  example may read it;
- a changed distribution, or one that requires it, has no import names in its metadata, or isn't installed;
- the runtime's installed packages couldn't be read, or the base commit isn't in the checkout;
- the runtime outside the book changed, when the last run's record says what it was: its backend, its Python, its
  image's definition, or the code that runs the examples.

An example whose imports can't all be read (`importlib.import_module` or `__import__` with a computed name, `exec` of a
computed string, `runpy`, or another program it starts) runs on every change to a pin or a local module. One that
imports a name that's neither local, nor in the standard library, nor named by an installed package's metadata runs on
every change to a pin.

What no diff shows, such as a new build of the runtime's base image or a new version of these checks when no record
says which ran, is left to a run of every example: each book's checks run them all every week.
"""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .bookfmt import Book
from .examples import DOCKERFILE, HARNESS, Runtime

EXAMPLES = "examples/"
DATA = "examples/data/"
PYTHON_VERSION = "examples/.python-version"
REQUIREMENTS = "examples/requirements.txt"
SKIPPED = re.compile(r"(^|/)__pycache__/|\.pyc$")          # never copied into an example's scratch folder
IMPORTS = {"import_module", "__import__"}                    # an import by name: read when the name is written out
RUNS_CODE = {"exec", "eval", "compile"}                       # builtins that run a string: read when it's written out
RUNS_FILES = {"run_path", "run_module", "spec_from_file_location", "spec_from_loader", "SourceFileLoader",
              "load_module", "exec_module", "load_source"}
STARTS_PROGRAMS = {"subprocess", "pty"}                       # modules whose use starts another program
OS_STARTS = re.compile(r"^(system|popen|exec[lv]p?e?|spawn[lv]p?e?|posix_spawnp?|startfile)$")
RUNNER_FILES = (HARNESS, Path(__file__).with_name("examples.py"), DOCKERFILE)


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runner_key() -> str:
    """A hash of the code that runs the examples: the harness, the runner and the runtime image's definition. A record
    that keeps it says which ran, so a later selection can tell when it changed."""
    h = hashlib.sha256()
    for path in RUNNER_FILES:
        h.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- what changed


@dataclass
class Change:
    """What differs between the base and the tree checked."""
    base: str                                   # the base commit
    paths: list[str]                            # every changed path, relative to the book's root
    base_python: str | None = None              # examples/.python-version at the base, stripped; None without one
    base_requirements: str | None = None        # examples/requirements.txt at the base; None without one


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def change_from_git(root: Path, base_ref: str | None) -> tuple[Change | None, str]:
    """What changed from `base_ref` to the checkout as it is: its working tree, with untracked files under examples/.
    (None, why) when git can't say, so every example runs."""
    if not base_ref:
        return None, "no base commit was given to compare with"
    found = _git(root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}")
    if found.returncode != 0:
        return None, f"the base commit {base_ref[:12]} isn't in this checkout, so what changed is unknown"
    sha = found.stdout.strip()
    diff = _git(root, "diff", "--name-only", "--no-renames", "--relative", "-z", sha, "--")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", "examples")
    if diff.returncode != 0 or untracked.returncode != 0:
        return None, f"git can't compare this checkout with {sha[:12]}"
    paths = sorted({p for out in (diff.stdout, untracked.stdout) for p in out.split("\0") if p})

    def at_base(rel: str) -> str | None:
        shown = _git(root, "show", f"{sha}:./{rel}")
        return shown.stdout if shown.returncode == 0 else None
    python = at_base(PYTHON_VERSION)
    return Change(sha, paths, (python or "").strip() or None, at_base(REQUIREMENTS)), ""


def changed_pins(book: Book, change: Change) -> tuple[dict[str, tuple[str, str]], list[str], list[str]]:
    """(pins whose version changed: name -> (from, to), pins added, pins removed), base to head."""
    if REQUIREMENTS not in change.paths:
        return {}, [], []
    req = book.root / REQUIREMENTS
    head = Runtime("", req.read_text(encoding="utf-8") if req.exists() else "").pins()
    base = Runtime("", change.base_requirements or "").pins()
    moved = {n: (base[n], head[n]) for n in sorted(set(base) & set(head)) if base[n] != head[n]}
    return moved, sorted(set(head) - set(base)), sorted(set(base) - set(head))


# ---------------------------------------------------------------- what an example imports


@dataclass
class Imports:
    """What one example runs, as far as its source and its local modules' sources say. Paths are relative to examples/."""
    files: dict[str, str]                       # each local file it loads -> the file that imports it ("" for itself)
    candidates: set[str]                        # every local path one of its imports would load, were it there
    names: dict[str, str]                       # each top-level name it imports from outside the book -> who imports it
    unknown: list[str] = field(default_factory=list)   # why its imports can't all be read
    folders: set[str] = field(default_factory=set)     # names in `names` that are also local folders with no __init__.py

    def chain(self, path: str) -> list[str]:
        """The local files through which it reaches `path`, nearest the example first, the example itself left out."""
        out, at = [], self.files.get(path, "")
        while at and at in self.files and self.files[at]:
            out.insert(0, at)
            at = self.files[at]
        return out


def _call_name(func: ast.expr) -> tuple[str, str]:
    """(name, the name it's called on): `importlib.import_module` is ("import_module", "importlib")."""
    if isinstance(func, ast.Name):
        return func.id, ""
    if isinstance(func, ast.Attribute):
        return func.attr, func.value.id if isinstance(func.value, ast.Name) else ""
    return "", ""


def _text(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _referenced(tree: ast.AST, package: str, rel: str, unknown: list[str]):
    """(module, star) for every module a source's imports may load, as absolute dotted names; why it can't say all
    goes to `unknown`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, False
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".") if package else []
                if node.level - 1 >= len(parts):
                    continue                    # past the top: Python refuses it, so the example fails anyway
                base = ".".join(parts[:len(parts) - node.level + 1] + ([node.module] if node.module else []))
            if not base:
                continue
            names = [a.name for a in node.names]
            yield base, "*" in names
            yield from ((f"{base}.{n}", False) for n in names if n != "*")
        elif isinstance(node, ast.Call):
            name, on = _call_name(node.func)
            first = _text(node.args[0]) if node.args else None
            if name in IMPORTS:
                if first and not first.startswith("."):
                    yield first, False
                else:
                    unknown.append(f"{name} with a computed name in {rel}")
            elif name in RUNS_CODE and not on:
                try:
                    inner = ast.parse(first) if first is not None else None
                except SyntaxError:
                    inner = ast.Module(body=[], type_ignores=[])    # an expression for eval: no import statement
                if inner is None:
                    unknown.append(f"{name} of a computed string in {rel}")
                else:
                    yield from _referenced(inner, package, rel, unknown)
            elif name in RUNS_FILES:
                unknown.append(f"{name} in {rel}")
            elif on == "os" and OS_STARTS.match(name):
                unknown.append(f"os.{name} in {rel} starts another program")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and not getattr(node, "level", 0):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                if m.split(".")[0] in STARTS_PROGRAMS:
                    unknown.append(f"{rel} imports {m.split('.')[0]}, so it can start another program")


def _module_paths(module: str) -> list[str]:
    """The local files importing `module` loads, were they there: each package on the way, then the module."""
    parts = module.split(".")
    out = []
    for i in range(1, len(parts) + 1):
        stem = "/".join(parts[:i])
        out += [f"{stem}.py", f"{stem}/__init__.py"]
    return out


def imports_of(folder: Path, example_file: str) -> Imports:
    """What an example imports, following its local modules (files beside it, in examples/) as far as they go."""
    out = Imports(files={example_file: ""}, candidates=set(), names={})
    queue = [example_file]
    while queue:
        rel = queue.pop(0)
        try:
            tree = ast.parse((folder / rel).read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as e:
            out.unknown.append(f"{rel} can't be read ({type(e).__name__})")
            continue
        package = ".".join(rel[:-3].split("/")[:-1])
        for module, star in _referenced(tree, package, rel, out.unknown):
            top = module.split(".")[0]
            regular = (folder / f"{top}.py").is_file() or (folder / top / "__init__.py").is_file()
            if not regular:
                # Not a local module, or a folder without __init__.py, which an installed package of the same name
                # would win over: either way, the name may come from outside the book.
                out.names.setdefault(top, rel)
                if (folder / top).is_dir():
                    out.folders.add(top)
            paths = _module_paths(module)
            out.candidates.update(paths)
            if star and (folder / module.replace(".", "/")).is_dir():
                paths += sorted(p.relative_to(folder).as_posix() for p in (folder / module.replace(".", "/")).rglob("*.py"))
            for p in paths:
                if p not in out.files and (folder / p).is_file():
                    out.files[p] = rel
                    queue.append(p)
    out.unknown = list(dict.fromkeys(out.unknown))
    return out


# ---------------------------------------------------------------- what the runtime installs


@dataclass
class Environment:
    """The runtime's installed distributions, as the harness reports them (harness.installed)."""
    distributions: dict[str, dict]
    stdlib: set[str] | None

    @classmethod
    def from_report(cls, report: dict) -> "Environment":
        dists = {norm(k): v for k, v in (report.get("distributions") or {}).items()}
        stdlib = report.get("stdlib")
        return cls(dists, set(stdlib) if stdlib is not None else None)

    def providers(self) -> dict[str, set[str]]:
        """Each top-level import name -> the distributions whose metadata names it."""
        out: dict[str, set[str]] = {}
        for name, d in self.distributions.items():
            for top in d.get("imports") or []:
                out.setdefault(top, set()).add(name)
        return out

    def needs(self) -> dict[str, set[str]]:
        """Each distribution -> every installed distribution it requires, directly or not."""
        direct = {n: {norm(r) for r in d.get("requires") or [] if norm(r) in self.distributions and norm(r) != n}
                  for n, d in self.distributions.items()}
        out: dict[str, set[str]] = {}
        for start in direct:
            seen, todo = set(), list(direct[start])
            while todo:
                n = todo.pop()
                if n not in seen:
                    seen.add(n)
                    todo += direct.get(n, ())
            out[start] = seen
        return out


def recorded_loaded(record: dict | None) -> dict[str, set[str]]:
    """Each example -> the distributions it loaded when it last ran, from a sections.json or an examples report."""
    out = {}
    for e in (record or {}).get("examples") or []:
        if isinstance(e, dict) and e.get("example_id") and isinstance(e.get("versions"), dict):
            out[e["example_id"]] = {norm(k) for k in e["versions"] if k != "python"}
    return out


def runtime_changes(previous: dict | None, current: dict | None) -> list[str]:
    """How the runtime outside the book changed between the last run's record and now: its backend, Python, network,
    image definition or runner. Nothing when either is unknown, save a record that doesn't say which runner it used."""
    if not previous or not current:
        return []
    out = [f"the runtime's {key} changed from {previous[key]} to {current[key]}"
           for key in ("backend", "python", "network") if previous.get(key) and previous.get(key) != current.get(key)]
    before, now = str(previous.get("image") or ""), str(current.get("image") or "")
    if before and now and before.rsplit("-", 1)[-1] != now.rsplit("-", 1)[-1]:
        out.append("the runtime image's definition changed")
    if "runner" in current:
        if not previous.get("runner"):
            out.append("the last run doesn't record which version of the code that runs the examples it used")
        elif previous["runner"] != current["runner"]:
            out.append("the code that runs the examples changed")
    return out


# ---------------------------------------------------------------- the selection


@dataclass
class Selection:
    total: int                                  # examples in the book
    examples: dict[str, list[str]]              # each example that runs -> why
    everything: list[str] = field(default_factory=list)   # why every example runs; empty when only `examples` do
    notes: list[str] = field(default_factory=list)
    base: str = ""

    @property
    def ids(self) -> list[str]:
        return sorted(self.examples)

    def as_json(self) -> dict:
        return {"scope": "affected", "base": self.base, "all": bool(self.everything), "why_all": self.everything,
                "total": self.total, "run": {eid: self.examples[eid] for eid in self.ids}, "notes": self.notes}

    def lines(self) -> list[str]:
        against = f"against {self.base[:12]}" if self.base else "with no base to compare"
        if self.everything:
            out = [f"Every example runs ({self.total}), {against}:"] + [f"  - {why}" for why in self.everything]
        elif not self.examples:
            out = [f"No example can be affected by this change, {against}: none of {self.total} runs"]
        else:
            out = [f"Examples this change could affect, {against}: {len(self.examples)} of {self.total} run"]
            out += [f"  run   {eid}: {'; '.join(self.examples[eid])}" for eid in self.ids]
            out.append(f"  {self.total - len(self.examples)} more: nothing this change touches reaches them")
        return out + [f"  note: {n}" for n in self.notes]


def _classify(book: Book, change: Change) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """(each example whose own files changed -> why, the local module files that changed, why every example runs)."""
    own: dict[str, list[str]] = {}
    modules, data, other, everything = [], [], [], []
    for path in change.paths:
        if not path.startswith(EXAMPLES) or SKIPPED.search(path) or path == REQUIREMENTS:
            continue
        rel = path[len(EXAMPLES):]
        if path == PYTHON_VERSION:
            pv = book.root / PYTHON_VERSION
            head = pv.read_text(encoding="utf-8").strip() if pv.exists() else None
            if head != change.base_python:
                everything.append(f"examples/.python-version changed from {change.base_python or 'nothing'} to "
                                  f"{head or 'nothing'}: every example runs on the new Python")
        elif path.startswith(DATA):
            data.append(path)
        elif "/" not in rel and rel.endswith((".py", ".out")):
            stem = rel.rsplit(".", 1)[0]
            if rel.endswith(".py"):
                modules.append(rel)             # another example may import it by name
            if stem in book.examples:
                own.setdefault(stem, []).append("its code changed" if rel.endswith(".py") else "its recorded output changed")
        elif rel.endswith(".py"):
            modules.append(rel)
        else:
            other.append(path)
    if data:
        more = f" and {len(data) - 1} more" if len(data) > 1 else ""
        everything.append(f"{data[0]}{more} changed under examples/data/, and what each example reads isn't recorded")
    if other:
        more = f" (and {len(other) - 1} more)" if len(other) > 1 else ""
        everything.append(f"{other[0]} changed{more}: a file beside the examples, which any of them may read")
    return own, modules, everything


def select(book: Book, change: Change | None, environment: Environment | None = None, recorded: dict | None = None,
           runtimes: tuple[dict | None, dict | None] | None = None, why_unknown: str = "",
           environment_problem: str = "") -> Selection:
    """The examples `change` could affect, each with why, or every example and why. `environment` is the runtime's
    installed packages, needed only when a pin's version changed; `recorded` a record of the last run (recorded_loaded);
    `runtimes` the last run's runtime and this one's, to compare (runtime_changes)."""
    ids = sorted(book.examples)
    sel = Selection(len(ids), {}, base=change.base if change else "")
    if change is None:
        sel.everything.append(why_unknown or "what changed is unknown")
    else:
        own, modules, everything = _classify(book, change)
        sel.everything += everything + runtime_changes(*(runtimes or (None, None)))
        moved, added, removed = changed_pins(book, change)
        if added or removed:
            words = ([f"{', '.join(added)} newly pinned"] if added else []) + ([f"{', '.join(removed)} unpinned"] if removed else [])
            sel.everything.append(f"{' and '.join(words)}: what's installed changed, and a library can import another "
                                  "only once it's there")
        if not sel.everything:
            sel.examples = {eid: list(why) for eid, why in own.items()}
            _by_imports(book, sel, modules, moved, environment, recorded_loaded(recorded), environment_problem)
    if sel.everything:
        sel.examples = {eid: ["every example runs"] for eid in ids}
    return sel


def _by_imports(book: Book, sel: Selection, modules: list[str], moved: dict[str, tuple[str, str]],
                environment: Environment | None, loaded: dict[str, set[str]], environment_problem: str) -> None:
    """Add the examples that import a changed local module, or a distribution whose pin moved, to `sel`."""
    if not modules and not moved:
        return
    folder = book.root / "examples"
    dependents: dict[str, set[str]] = {}
    providers: dict[str, set[str]] = {}
    if moved:
        if environment is None:
            sel.everything.append(f"the runtime's installed packages couldn't be read"
                                  f"{': ' + environment_problem if environment_problem else ''}, so what imports "
                                  f"{', '.join(moved)} isn't known")
            return
        needs = environment.needs()
        for name in moved:
            if name not in environment.distributions:
                sel.everything.append(f"{name} isn't installed in the runtime, so what imports it isn't known")
                continue
            dependents[name] = {name} | {d for d, req in needs.items() if name in req}
            nameless = sorted(d for d in dependents[name] if environment.distributions[d].get("imports") is None)
            if nameless:
                d = nameless[0]
                how = ("installs a .pth file, which runs at every start of Python and can change what any import finds"
                       if environment.distributions[d].get("pth") else "has no metadata naming what it can be imported as")
                sel.everything.append(f"{name} {moved[name][0]} to {moved[name][1]}: "
                                      + (f"{d} {how}" if d == name else f"{d}, which depends on it, {how}"))
        if sel.everything:
            return
        providers = environment.providers()
    for eid in sorted(book.examples):
        imp = imports_of(folder, f"{eid}.py")
        why = sel.examples.setdefault(eid, [])
        reached = [m for m in modules if m != f"{eid}.py" and (m in imp.files or m in imp.candidates)]
        for m in reached:
            through = imp.chain(m)
            why.append(f"it imports {m}, which changed" + (f", through {' and '.join(through)}" if through else ""))
        if imp.unknown and not reached and [m for m in modules if m != f"{eid}.py"]:
            why.append(f"a local module changed, and its imports can't all be read: {imp.unknown[0]}")
        if moved:
            imported = {top: providers.get(top, set()) for top in imp.names}
            unnamed = sorted(top for top, dists in imported.items() if not dists and top not in imp.folders and
                             (environment.stdlib is None or top not in environment.stdlib))
            for name, (old, new) in moved.items():
                change = f"{name} {old} to {new}"
                hits = sorted((top, d) for top, dists in imported.items() for d in dists if d in dependents[name])
                direct = [top for top, d in hits if d == name]
                if direct:
                    via = imp.names[direct[0]]
                    why.append(f"{change}: it imports {direct[0]}" + ("" if via == f"{eid}.py" else f", through {via}"))
                elif hits:
                    top, d = hits[0]
                    why.append(f"{change}: it imports {top}" + (f" ({d})" if norm(top) != d else "") +
                               f", which depends on {name}")
                elif name in loaded.get(eid, set()):
                    why.append(f"{change}: it loaded {name} when it last ran")
                elif imp.unknown:
                    why.append(f"{change}: its imports can't all be read: {imp.unknown[0]}")
                elif unnamed:
                    why.append(f"{change}: it imports {unnamed[0]}, which no installed package's metadata names")
        if not why:
            del sel.examples[eid]


# ---------------------------------------------------------------- reading the record of the last run


def load_recorded(source: str | None, slug: str) -> tuple[dict | None, str]:
    """A record of the last run to add examples from: a sections.json or an examples report, from a path or URL, or
    `latest`, the latest edition's sections.json. (None, why) when there's none or it can't be read: the selection then
    rests on the imports alone."""
    from . import checks
    if not source or source == "none":
        return None, ""
    url = checks.latest_sections_url(slug) if source == "latest" else source
    try:
        record, _ = checks.load_previous_manifest(url)
    except Exception as e:                      # a site that can't be reached leaves the imports to decide
        return None, f"the last run's record couldn't be read ({type(e).__name__}), so the imports alone decide"
    return record, ""


def choose(book: Book, base_ref: str | None, backend, recorded_source: str | None = None,
           timeout: float = 120) -> tuple[Selection, bool]:
    """The selection for the checkout against `base_ref`. The runtime's installed packages are read only when a pin's
    version changed: the runtime is then built first, its pins read by the resolver as for any run. Returns the
    selection and whether the runtime is now built. Raises examples.UnsatisfiablePins when the pins can't be installed
    together, and examples.ExamplesError when the runtime isn't pinned."""
    from . import examples
    change, why = change_from_git(book.root, base_ref)
    record, note = load_recorded(recorded_source, book.slug)
    environment, problem, prepared, runtimes = None, "", False, None
    if change is not None and changed_pins(book, change)[0]:
        runtime = examples.read_runtime(book.root)
        examples.check_pins(runtime, backend)
        backend.prepare(runtime)
        prepared = True
        try:
            environment = Environment.from_report(examples.installed(runtime, backend, timeout))
        except examples.ExamplesError as e:
            problem = str(e)
    if record and isinstance(record.get("runtime"), dict):        # an examples report says what it ran in
        runtimes = (record["runtime"], backend.describe(examples.read_runtime(book.root)))
    sel = select(book, change, environment, record, runtimes, why_unknown=why, environment_problem=problem)
    if note:
        sel.notes.append(note)
    return sel, prepared
