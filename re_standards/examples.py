"""Run every example in a book's pinned runtime and compare its output: the first check on every book pull request.

The pinned runtime is two files in the book repo:

    examples/.python-version     an exact Python version, such as 3.12.15
    examples/requirements.txt    exact pins, such as pandas==2.2.3

Backends build that runtime differently:

    venv       local: uv builds a virtual environment with a managed CPython; the network is blocked
               with `unshare -rn`. Where the kernel won't allow that, it refuses to run rather than run online,
               unless RE_EXAMPLES_ALLOW_NETWORK=1 says so, and the runtime then records the network as open
    container  CI and Cloud Run: the image built from runtime/Dockerfile, run with --network none; with
               RE_EXAMPLES_REGISTRY set, pulled from that registry, or built and pushed there once
    host       tests only: the current interpreter, nothing installed

Each example runs in a scratch copy of examples/, so it can't change the repo and its output never
contains repository paths. Only stdout is compared, after trimming trailing spaces and blank lines.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .bookfmt import Book

HARNESS = Path(__file__).with_name("harness.py")
DOCKERFILE = Path(__file__).resolve().parent.parent / "runtime" / "Dockerfile"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)")


class ExamplesError(RuntimeError):
    """The pinned runtime is missing, unpinned or can't be built."""


@dataclass
class Runtime:
    python: str
    requirements: str

    @property
    def key(self) -> str:
        h = hashlib.sha256(f"{self.python}\n{self.requirements}".encode()).hexdigest()
        return h[:16]

    def pins(self) -> dict[str, str]:
        out = {}
        for line in self.requirements.splitlines():
            m = PIN.match(line.strip())
            if m:
                out[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
        return out


def read_runtime(book_root: Path) -> Runtime:
    ex = Path(book_root) / "examples"
    pv, req = ex / ".python-version", ex / "requirements.txt"
    if not pv.exists():
        raise ExamplesError("examples/.python-version is missing: pin an exact Python version, such as 3.12.15")
    python = pv.read_text().strip()
    if not re.fullmatch(r"3\.\d+\.\d+", python):
        raise ExamplesError(f"examples/.python-version must be an exact version like 3.12.15, not {python!r}")
    requirements = req.read_text() if req.exists() else ""
    for line in requirements.splitlines():
        line = line.split("#")[0].strip()
        if line and not PIN.match(line):
            raise ExamplesError(f"examples/requirements.txt: {line!r} is not pinned to an exact version (name==version)")
    return Runtime(python, requirements)


@dataclass
class ExampleResult:
    example_id: str
    passing: bool
    exit_code: int
    stdout: str
    expected: str | None
    diff: str = ""
    stderr_tail: str = ""
    versions: dict = field(default_factory=dict)
    direct: list = field(default_factory=list)
    seconds: float = 0.0

    def manifest_entry(self) -> dict:
        return {"passing": self.passing, "versions": self.versions, "direct": self.direct}


def normalize_output(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def compare(example_id: str, stdout: str, expected: str | None) -> tuple[bool, str]:
    if expected is None:
        return False, "no expected output recorded"
    a, b = normalize_output(expected), normalize_output(stdout)
    if a == b:
        return True, ""
    diff = difflib.unified_diff(a.splitlines(), b.splitlines(), f"{example_id}.out (expected)", f"{example_id} (actual)", lineterm="")
    return False, "\n".join(diff)


# ---------------------------------------------------------------- backends


def _uv() -> list[str]:
    found = shutil.which("uv") or (str(Path(sys.executable).with_name("uv")) if Path(sys.executable).with_name("uv").exists() else None)
    return [found] if found else [sys.executable, "-m", "uv"]


def env_root() -> Path:
    env = os.environ.get("RE_EXAMPLES_ENV_DIR")
    base = Path(env) if env else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "rolling-edition" / "examples"
    return base


def can_block_network() -> bool:
    if not shutil.which("unshare"):
        return False
    return subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode == 0


class Backend:
    name = "base"

    def prepare(self, runtime: Runtime) -> None:
        pass

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        raise NotImplementedError

    def describe(self, runtime: Runtime) -> dict:
        return {"backend": self.name, "python": runtime.python, "key": runtime.key,
                "requirements_sha256": hashlib.sha256(runtime.requirements.encode()).hexdigest()}


THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


def _thread_caps() -> dict:
    """When this process may run on fewer CPUs than the machine has, as under taskset or a container's cpuset, cap the
    numeric libraries' threads at that number. OpenBLAS and OpenMP otherwise start a thread for every CPU in the
    machine, and pinned runs sharing a few CPUs slow past the timeout. An unpinned run, such as CI's, gets no cap and
    runs exactly as before, so no recorded output can change with it."""
    try:
        allowed = len(os.sched_getaffinity(0))
    except AttributeError:                                  # no CPU affinity on this platform, such as macOS
        return {}
    return {name: str(allowed) for name in THREAD_VARS} if allowed < (os.cpu_count() or allowed) else {}


def _clean_env(extra: dict) -> dict:
    # Nothing from the caller's environment reaches an example: no user name, home folder or tokens.
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
           "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", **_thread_caps()}
    env.update(extra)
    return env


class VenvBackend(Backend):
    name = "venv"

    def __init__(self, block_network: bool = True):
        allow = os.environ.get("RE_EXAMPLES_ALLOW_NETWORK") == "1"
        self.block_network = block_network and not (allow and not can_block_network())

    def env_dir(self, runtime: Runtime) -> Path:
        return env_root() / f"py{runtime.python}-{runtime.key}"

    def prepare(self, runtime: Runtime) -> None:
        target = self.env_dir(runtime)
        if (target / ".ready").exists():
            return
        shutil.rmtree(target, ignore_errors=True)     # a half-built runtime is rebuilt from scratch
        target.parent.mkdir(parents=True, exist_ok=True)
        uv = _uv()
        steps = [uv + ["venv", "--quiet", "--python", runtime.python, "--python-preference", "only-managed", str(target)]]
        if runtime.pins():
            req = target.parent / f"{target.name}.requirements.txt"
            req.write_text(runtime.requirements)
            steps.append(uv + ["pip", "install", "--quiet", "--python", str(target / "bin" / "python"), "-r", str(req)])
        for step in steps:
            r = subprocess.run(step, capture_output=True, text=True)
            if r.returncode != 0:
                raise ExamplesError(f"could not build the pinned runtime: {r.stderr.strip()[-2000:]}")
        (target / ".ready").write_text(json.dumps(self.describe(runtime)))   # written last: the runtime is complete

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        python = self.env_dir(runtime) / "bin" / "python"
        cmd = [str(python), "-I", ".re_harness.py", example]
        if self.block_network:
            if not can_block_network():                 # fail closed: never run an example online by accident
                raise ExamplesError("the network can't be blocked here: `unshare -rn` isn't allowed (on Ubuntu 24.04, "
                                    "unprivileged user namespaces are restricted). Use the container backend, or set "
                                    "RE_EXAMPLES_ALLOW_NETWORK=1 to run with the network open, for local use only")
            cmd = ["unshare", "-rn"] + cmd
        return cmd, _clean_env({"HOME": str(workdir), "RE_EXAMPLE_REPORT": str(workdir / ".re_report.json")})

    def describe(self, runtime: Runtime) -> dict:
        return dict(super().describe(runtime), network="blocked" if self.block_network else "open")


class HostBackend(Backend):
    """Tests only: the current interpreter, so tiny examples run without installing anything."""
    name = "host"

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        return [sys.executable, "-I", ".re_harness.py", example], \
            _clean_env({"HOME": str(workdir), "RE_EXAMPLE_REPORT": str(workdir / ".re_report.json")})


def dockerfile_key() -> str:
    """The runtime Dockerfile's own hash: an image is built from it as well as from the pins, so a changed
    Dockerfile gets new images rather than a cached one built from the old file."""
    return hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest()[:8]


class ContainerBackend(Backend):
    """CI and Cloud Run: an image per runtime, built from runtime/Dockerfile and run without a network.

    The image is tagged by its pins and the Dockerfile: `re-examples:py{python}-{runtime key}-{Dockerfile hash}`.
    With a registry (`registry`, or RE_EXAMPLES_REGISTRY, such as `{region}-docker.pkg.dev/{project}/runtime`),
    images are a cache every run shares: `prepare` pulls `{registry}/{tag}` and only when that fails builds it and
    pushes it, so each runtime is built once. The caller signs the engine in to the registry first. A failed push
    only costs the next run a build, so it warns rather than failing the examples. Without a registry, as in a
    book repository's own checks, the image is built on the runner every time and nothing is pushed.

    Inside the container an example sees what the venv backend gives it: the same clean environment, HOME in its
    scratch folder, and the caller's user and group, so it can write its report into the mounted folder.
    """
    name = "container"

    def __init__(self, engine: str = "docker", repository: str = "re-examples", registry: str | None = None):
        self.engine = engine
        self.repository = repository
        self.registry = (os.environ.get("RE_EXAMPLES_REGISTRY", "") if registry is None else registry).strip().rstrip("/")

    def tag(self, runtime: Runtime) -> str:
        """The image's name without a registry: the same locally and in CI, so it's what a description records."""
        return f"{self.repository}:py{runtime.python}-{runtime.key}-{dockerfile_key()}"

    def image(self, runtime: Runtime) -> str:
        """The image as the engine names it: pulled from, pushed to and run from the registry when there is one."""
        return f"{self.registry}/{self.tag(runtime)}" if self.registry else self.tag(runtime)

    def pull_command(self, runtime: Runtime) -> list[str]:
        return [self.engine, "pull", "--quiet", self.image(runtime)]

    def build_command(self, runtime: Runtime, context: Path) -> list[str]:
        return [self.engine, "build", "--quiet", "-f", str(DOCKERFILE), "--build-arg", f"PYTHON_VERSION={runtime.python}",
                "-t", self.image(runtime), str(context)]

    def push_command(self, runtime: Runtime) -> list[str]:
        return [self.engine, "push", "--quiet", self.image(runtime)]

    def prepare(self, runtime: Runtime, context: Path | None = None) -> None:
        if self.registry and subprocess.run(self.pull_command(runtime), capture_output=True, text=True).returncode == 0:
            return                                  # an earlier run built it
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "requirements.txt").write_text(runtime.requirements)
            r = subprocess.run(self.build_command(runtime, Path(tmp)), capture_output=True, text=True)
            if r.returncode != 0:
                raise ExamplesError(f"could not build the example image: {r.stderr.strip()[-2000:]}")
        if self.registry:
            r = subprocess.run(self.push_command(runtime), capture_output=True, text=True)
            if r.returncode != 0:
                print(f"warning: could not push {self.image(runtime)}, so the next run builds it again: "
                      f"{r.stderr.strip()[-500:]}", file=sys.stderr)

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        inside = {k: v for k, v in _clean_env({"HOME": "/work", "RE_EXAMPLE_REPORT": "/work/.re_report.json"}).items()
                  if k != "PATH"}               # the image's own PATH finds its Python
        user = ["--user", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
        return [self.engine, "run", "--rm", "--network", "none", *user, "-v", f"{workdir}:/work", "-w", "/work",
                *[x for k, v in sorted(inside.items()) for x in ("-e", f"{k}={v}")], self.image(runtime),
                "python", "-I", ".re_harness.py", example], _clean_env({})

    def describe(self, runtime: Runtime) -> dict:
        return dict(super().describe(runtime), image=self.tag(runtime), network="none")


def backend_named(name: str, block_network: bool = True) -> Backend:
    if name == "venv":
        return VenvBackend(block_network)
    if name == "container":
        return ContainerBackend()
    if name == "host":
        return HostBackend()
    raise ValueError(f"unknown examples backend {name!r}: use venv, container or host")


# ---------------------------------------------------------------- running


def run_examples(book: Book, backend: Backend, timeout: float = 120, only: list[str] | None = None) -> tuple[list[ExampleResult], dict]:
    runtime = read_runtime(book.root)
    backend.prepare(runtime)
    results = []
    for eid in sorted(book.examples):
        if only and eid not in only:
            continue
        results.append(run_one(book, eid, runtime, backend, timeout))
    return results, backend.describe(runtime)


def run_one(book: Book, eid: str, runtime: Runtime, backend: Backend, timeout: float) -> ExampleResult:
    example = book.examples[eid]
    with tempfile.TemporaryDirectory(prefix="re-example-") as tmp:
        work = Path(tmp) / "examples"
        shutil.copytree(book.root / "examples", work, ignore=shutil.ignore_patterns("*.out", "__pycache__", ".python-version", "requirements.txt"))
        shutil.copy(HARNESS, work / ".re_harness.py")
        cmd, env = backend.command(runtime, work, f"{eid}.py")
        start = time.monotonic()
        try:
            r = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=timeout)
            code, stdout, stderr = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            code, stdout, stderr = 124, (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), f"timed out after {timeout:g} seconds"
        seconds = round(time.monotonic() - start, 2)
        report = {}
        if (work / ".re_report.json").exists():
            report = json.loads((work / ".re_report.json").read_text())
    same, diff = compare(eid, stdout, example.expected)
    versions = dict({"python": report.get("python", runtime.python)}, **dict(sorted(report.get("loaded", {}).items())))
    tail = "\n".join(stderr.strip().splitlines()[-15:])
    return ExampleResult(eid, passing=(code == 0 and same), exit_code=code, stdout=stdout, expected=example.expected,
                         diff=diff if code == 0 else "", stderr_tail=tail, versions=versions,
                         direct=report.get("direct", []), seconds=seconds)


def results_json(results: list[ExampleResult], runtime: dict) -> dict:
    return {"runtime": runtime, "passing": sum(r.passing for r in results), "total": len(results),
            "examples": [asdict(r) for r in results]}


def describe_versions(versions: dict, direct: list[str]) -> str:
    """'Python 3.12.15 · pandas 2.2.3': the Python version and every library the example imports directly."""
    parts = [f"Python {versions['python']}"] if "python" in versions else []
    parts += [f"{d} {versions[d]}" for d in direct if d in versions]
    return " · ".join(parts)
