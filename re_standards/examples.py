"""Run every example in a book's pinned runtime and compare its output: the first check on every book pull request.

The pinned runtime is two files in the book repo, and a third for a book whose examples load open models:

    examples/.python-version     an exact Python version, such as 3.12.15
    examples/requirements.txt    exact pins, such as pandas==2.2.3
    examples/models.toml         open model files, each at a full commit with its SHA-256 (models.py)

Backends build that runtime differently:

    venv       local: uv builds a virtual environment with a managed CPython; the network is blocked
               with `unshare -rn`. Where the kernel won't allow that, it refuses to run rather than run online,
               unless RE_EXAMPLES_ALLOW_NETWORK=1 says so, and the runtime then records the network as open
    container  CI and Cloud Run: the image built from runtime/Dockerfile, run with --network none; with
               RE_EXAMPLES_REGISTRY set, pulled from that registry, or built and pushed there once
    host       tests only: the current interpreter, nothing installed

Before a backend that installs the pins builds the runtime, a resolver reads them (resolve.py). Pins that can't be
installed together stop the run with UnsatisfiablePins, which names the conflict in plain words, so it's never
reported as an example's failure or as a build's last lines.

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

from . import models as model_files, resolve
from .bookfmt import Book

HARNESS = Path(__file__).with_name("harness.py")
DOCKERFILE = Path(__file__).resolve().parent.parent / "runtime" / "Dockerfile"
MODELS_DOCKERFILE = DOCKERFILE.with_name("models.Dockerfile")
FETCH_MODELS = Path(__file__).with_name("fetch_models.py")
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)")
INDEX = re.compile(r"^--extra-index-url\s+(\S+)$")     # an index beside PyPI, from [runtime] extra_indexes only
BEST_MATCH = ["--index-strategy", "unsafe-best-match"]   # with an extra index, uv reads all of them, as pip does


def extra_indexes_allowed() -> list[str]:
    import tomllib
    from . import data_path
    return tomllib.loads(data_path("examples.toml").read_text(encoding="utf-8"))["runtime"]["extra_indexes"]


class ExamplesError(RuntimeError):
    """The pinned runtime is missing, unpinned or can't be built."""


class UnsatisfiablePins(ExamplesError):
    """The resolver says the pins can't be installed together: the runtime wasn't built and no example ran."""

    def __init__(self, resolution: resolve.Resolution):
        self.resolution = resolution
        super().__init__(resolution.explanation)


@dataclass
class Runtime:
    python: str
    requirements: str
    models: str = ""            # examples/models.toml's text, or "" for a book that loads no model

    @property
    def key(self) -> str:
        """The pins' hash, and the models' too when there are any: a runtime without models keeps the key it had."""
        text = f"{self.python}\n{self.requirements}"
        if self.models:
            text += "\n" + model_files.canonical(self.model_list())
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def model_list(self) -> list[model_files.Model]:
        return model_files.parse(self.models) if self.models else []

    def indexes(self) -> list[str]:
        """The package indexes the pins add beside PyPI."""
        return [m.group(1) for line in self.requirements.splitlines() if (m := INDEX.match(line.split("#")[0].strip()))]

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
    allowed = None
    for line in requirements.splitlines():
        line = line.split("#")[0].strip()
        index = INDEX.match(line)
        if index:
            allowed = allowed if allowed is not None else extra_indexes_allowed()
            if index.group(1).rstrip("/") not in [a.rstrip("/") for a in allowed]:
                raise ExamplesError(f"examples/requirements.txt: {index.group(1)} isn't an index a book may use; "
                                    f"allowed: {', '.join(allowed)}")
            continue
        if line and not PIN.match(line):
            raise ExamplesError(f"examples/requirements.txt: {line!r} is not pinned to an exact version (name==version)")
    pinned = Path(book_root) / model_files.MODELS
    models = pinned.read_text(encoding="utf-8") if pinned.exists() else ""
    if models:
        try:
            model_files.parse(models)
        except model_files.ModelsError as e:
            raise ExamplesError(str(e)) from None
    return Runtime(python, requirements, models)


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
    installs = True                 # builds the runtime from the pins, so the resolver reads them first

    def ready(self, runtime: Runtime) -> bool:
        """Whether this runtime is already built here: then its pins installed together, and needn't be read again."""
        return False

    def prepare(self, runtime: Runtime) -> None:
        pass

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        raise NotImplementedError

    def describe(self, runtime: Runtime) -> dict:
        out = {"backend": self.name, "python": runtime.python, "key": runtime.key,
               "requirements_sha256": hashlib.sha256(runtime.requirements.encode()).hexdigest()}
        if runtime.models:
            out["models_sha256"] = model_files.digest(runtime.model_list())
        return out


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


# What may hold a credential, by its variable's name: a word of the name (split at underscores), a prefix, or a whole
# name. A URL with a user name or password in it counts too, whatever its variable is called.
CREDENTIAL_WORDS = {"KEY", "KEYS", "APIKEY", "TOKEN", "TOKENS", "SECRET", "SECRETS", "PASSWORD", "PASSWORDS", "PASSWD",
                    "PASS", "CREDENTIAL", "CREDENTIALS", "CREDS", "AUTH", "COOKIE", "COOKIES", "PRIVATE"}
CREDENTIAL_PREFIXES = ("ANTHROPIC_", "CLAUDE_", "AWS_", "AZURE_", "GOOGLE_", "GCLOUD_", "CLOUDSDK_", "GCP_", "GH_",
                       "GITHUB_", "GITLAB_", "OPENAI_", "STRIPE_", "FIREBASE_", "HF_", "HUGGING_FACE_", "NPM_", "TWINE_",
                       "PYPI_", "GPG_", "SSH_", "VAULT_", "RE_GCP_", "RE_GITHUB_")
CREDENTIAL_NAMES = {"NETRC", "KRB5CCNAME", "PGPASSFILE", "BOTO_CONFIG"}
URL_WITH_USER = re.compile(r"://[^/\s@]+@")


def holds_credential(name: str, value: str) -> bool:
    upper = name.upper()
    return (upper in CREDENTIAL_NAMES or upper.startswith(CREDENTIAL_PREFIXES)
            or bool(CREDENTIAL_WORDS & set(upper.split("_"))) or bool(URL_WITH_USER.search(value or "")))


def credential_free_env(environ: dict | None = None) -> dict[str, str]:
    """The caller's environment without any variable that is, or may hold, a credential: what the venv backend builds a
    runtime with and the resolver reads the pins with. Both install from the package index, and a package that has no
    wheel runs its own build code, which never needs a key, a token or a password. An example itself never sees the
    caller's environment at all (_clean_env)."""
    source = os.environ if environ is None else environ
    return {k: v for k, v in source.items() if not holds_credential(k, v)}


class VenvBackend(Backend):
    name = "venv"

    def __init__(self, block_network: bool = True):
        allow = os.environ.get("RE_EXAMPLES_ALLOW_NETWORK") == "1"
        self.block_network = block_network and not (allow and not can_block_network())

    def env_dir(self, runtime: Runtime) -> Path:
        return env_root() / f"py{runtime.python}-{runtime.key}"

    def ready(self, runtime: Runtime) -> bool:
        return (self.env_dir(runtime) / ".ready").exists()

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
            steps.append(uv + ["pip", "install", "--quiet", "--python", str(target / "bin" / "python"), "-r", str(req),
                               *(BEST_MATCH if runtime.indexes() else [])])
        for step in steps:
            r = subprocess.run(step, capture_output=True, text=True, env=credential_free_env())
            if r.returncode != 0:
                raise ExamplesError(f"could not build the pinned runtime: {r.stderr.strip()[-2000:]}")
        if runtime.models:
            try:
                model_files.fetch(runtime.model_list(), self.models_dir(runtime))
            except (OSError, ValueError) as e:
                raise ExamplesError(f"could not fetch the pinned model files: {e}") from None
        (target / ".ready").write_text(json.dumps(self.describe(runtime)))   # written last: the runtime is complete

    def models_dir(self, runtime: Runtime) -> Path:
        """The runtime's Hugging Face cache, beside its venv: where its examples find their models offline."""
        return self.env_dir(runtime) / "hf"

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        python = self.env_dir(runtime) / "bin" / "python"
        cmd = [str(python), "-I", ".re_harness.py", example]
        if self.block_network:
            if not can_block_network():                 # fail closed: never run an example online by accident
                raise ExamplesError("the network can't be blocked here: `unshare -rn` isn't allowed (on Ubuntu 24.04, "
                                    "unprivileged user namespaces are restricted). Use the container backend, or set "
                                    "RE_EXAMPLES_ALLOW_NETWORK=1 to run with the network open, for local use only")
            cmd = ["unshare", "-rn"] + cmd
        extra = model_files.env(self.models_dir(runtime)) if runtime.models else {}
        return cmd, _clean_env({"HOME": str(workdir), "RE_EXAMPLE_REPORT": str(workdir / ".re_report.json"), **extra})

    def describe(self, runtime: Runtime) -> dict:
        return dict(super().describe(runtime), network="blocked" if self.block_network else "open")


class HostBackend(Backend):
    """Tests only: the current interpreter, so tiny examples run without installing anything."""
    name = "host"
    installs = False

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        return [sys.executable, "-I", ".re_harness.py", example], \
            _clean_env({"HOME": str(workdir), "RE_EXAMPLE_REPORT": str(workdir / ".re_report.json")})


def dockerfile_key() -> str:
    """The runtime Dockerfile's own hash: an image is built from it as well as from the pins, so a changed
    Dockerfile gets new images rather than a cached one built from the old file."""
    return hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest()[:8]


def models_dockerfile_key() -> str:
    """For a runtime with models: the hash of both image definitions and the fetch, which build its image together."""
    h = hashlib.sha256()
    for path in (DOCKERFILE, MODELS_DOCKERFILE, FETCH_MODELS):
        h.update(path.read_bytes() + b"\0")
    return h.hexdigest()[:8]


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
        """The image's name without a registry: the same locally and in CI, so it's what a description records. Its
        last part is the image definition's hash, which affected.py compares between runs."""
        definition = models_dockerfile_key() if runtime.models else dockerfile_key()
        return f"{self.repository}:py{runtime.python}-{runtime.key}-{definition}"

    def image(self, runtime: Runtime) -> str:
        """The image as the engine names it: pulled from, pushed to and run from the registry when there is one."""
        return f"{self.registry}/{self.tag(runtime)}" if self.registry else self.tag(runtime)

    def pull_command(self, runtime: Runtime) -> list[str]:
        return [self.engine, "pull", "--quiet", self.image(runtime)]

    def build_command(self, runtime: Runtime, context: Path) -> list[str]:
        """The pins' image. For a runtime with models, the base that models_build_command's layer goes on."""
        target = self.base_image(runtime) if runtime.models else self.image(runtime)
        return [self.engine, "build", "--quiet", "-f", str(DOCKERFILE), "--build-arg", f"PYTHON_VERSION={runtime.python}",
                "-t", target, str(context)]

    def base_image(self, runtime: Runtime) -> str:
        """A local name for the pins' image under a runtime with models: built, never pushed."""
        return f"{self.repository}-base:py{runtime.python}-{runtime.key}-{dockerfile_key()}"

    def models_build_command(self, runtime: Runtime, context: Path) -> list[str]:
        return [self.engine, "build", "--quiet", "-f", str(MODELS_DOCKERFILE), "--build-arg", f"BASE={self.base_image(runtime)}",
                "--build-arg", f"BASE_URL={model_files.settings()['base_url']}",
                "--build-arg", f"CACHE={model_files.settings()['image_cache']}", "-t", self.image(runtime), str(context)]

    def push_command(self, runtime: Runtime) -> list[str]:
        return [self.engine, "push", "--quiet", self.image(runtime)]

    def prepare(self, runtime: Runtime, context: Path | None = None) -> None:
        if self.registry and subprocess.run(self.pull_command(runtime), capture_output=True, text=True).returncode == 0:
            return                                  # an earlier run built it
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "requirements.txt").write_text(runtime.requirements)
            r = subprocess.run(self.build_command(runtime, Path(tmp)), capture_output=True, text=True)
            if r.returncode != 0:
                raise ExamplesError(f"could not build the example image: {build_failure(r.stderr)}")
        if runtime.models:
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "models.json").write_text(json.dumps([m.as_json() for m in runtime.model_list()]))
                shutil.copy(FETCH_MODELS, Path(tmp) / "fetch_models.py")
                r = subprocess.run(self.models_build_command(runtime, Path(tmp)), capture_output=True, text=True)
                if r.returncode != 0:
                    raise ExamplesError(f"could not add the pinned model files to the example image: {r.stderr.strip()[-2000:]}")
        if self.registry:
            r = subprocess.run(self.push_command(runtime), capture_output=True, text=True)
            if r.returncode != 0:
                print(f"warning: could not push {self.image(runtime)}, so the next run builds it again: "
                      f"{r.stderr.strip()[-500:]}", file=sys.stderr)

    def command(self, runtime: Runtime, workdir: Path, example: str) -> tuple[list[str], dict]:
        extra = model_files.env(model_files.settings()["image_cache"]) if runtime.models else {}
        inside = {k: v for k, v in _clean_env({"HOME": "/work", "RE_EXAMPLE_REPORT": "/work/.re_report.json", **extra}).items()
                  if k != "PATH"}               # the image's own PATH finds its Python
        user = ["--user", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
        return [self.engine, "run", "--rm", "--network", "none", *user, "-v", f"{workdir}:/work", "-w", "/work",
                *[x for k, v in sorted(inside.items()) for x in ("-e", f"{k}={v}")], self.image(runtime),
                "python", "-I", ".re_harness.py", example], _clean_env({})

    def describe(self, runtime: Runtime) -> dict:
        return dict(super().describe(runtime), image=self.tag(runtime), network="none")


def build_failure(stderr: str) -> str:
    """Why an image didn't build. The build's last lines name only the Dockerfile's step, so pip's own errors from the
    step that failed come first: "ERROR: Cannot install ...", and what it says the conflict is caused by."""
    lines = [re.sub(r"^\s*(?:#\d+ )?\d+\.\d+ ", "", line).rstrip() for line in stderr.splitlines()]   # BuildKit's step and time
    pip, keep = [], False
    for line in lines:
        if re.match(r"^(ERROR|error):", line) and "failed to solve" not in line:
            keep = True
        if keep and line.strip() and not line.startswith(("--------", "Dockerfile:")):
            pip.append(line.strip())
        if keep and not line.strip():
            keep = False
    tail = stderr.strip()[-1200:]
    return ("\n".join(pip[:30]) + "\n" + tail) if pip else stderr.strip()[-2000:]


def backend_named(name: str, block_network: bool = True) -> Backend:
    if name == "venv":
        return VenvBackend(block_network)
    if name == "container":
        return ContainerBackend()
    if name == "host":
        return HostBackend()
    raise ValueError(f"unknown examples backend {name!r}: use venv, container or host")


# ---------------------------------------------------------------- running


def check_pins(runtime: Runtime, backend: Backend) -> resolve.Resolution | None:
    """The resolver's reading of the pins, when this backend is about to install them; None when it isn't."""
    if not backend.installs or not runtime.pins() or backend.ready(runtime):
        return None
    found = resolve.check(runtime.python, runtime.requirements, runtime.pins(), env=credential_free_env(),
                          extra_args=BEST_MATCH if runtime.indexes() else None)
    if found.outcome == "unsatisfiable":
        raise UnsatisfiablePins(found)
    return found


def run_examples(book: Book, backend: Backend, timeout: float = 120, only: list[str] | None = None,
                 prepared: bool = False, jobs: int = 1, seconds: dict[str, float] | None = None
                 ) -> tuple[list[ExampleResult], dict]:
    """Every example, or those in `only`, in the pinned runtime. `prepared` says the caller has already read the pins and
    built the runtime (as the choice of affected examples does, to read what it installs). With `jobs` above 1, up to
    that many run side by side, packed by `seconds`, each one's time in the last run (side_by_side)."""
    runtime = read_runtime(book.root)
    if not prepared:
        check_pins(runtime, backend)
        backend.prepare(runtime)
    ids = [eid for eid in sorted(book.examples) if not only or eid in only]
    results = side_by_side(ids, lambda eid: run_one(book, eid, runtime, backend, timeout), jobs, seconds or {}, timeout)
    return results, backend.describe(runtime)


def installed(runtime: Runtime, backend: Backend, timeout: float = 120) -> dict:
    """What the runtime has installed, read inside it by the harness (`--metadata`), with the network blocked as for an
    example: each distribution's version, the names it can be imported as and what it requires, and the standard
    library's module names. Only metadata is read: no package's code runs. The runtime must already be prepared."""
    with tempfile.TemporaryDirectory(prefix="re-metadata-") as tmp:
        work = Path(tmp) / "examples"
        work.mkdir()
        shutil.copy(HARNESS, work / ".re_harness.py")
        cmd, env = backend.command(runtime, work, "--metadata")
        try:
            r = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ExamplesError(f"reading the runtime's installed packages took more than {timeout:g} seconds") from None
        report = work / ".re_report.json"
        if r.returncode != 0 or not report.exists():
            raise ExamplesError(f"could not read the runtime's installed packages: {r.stderr.strip()[-500:] or r.returncode}")
        return json.loads(report.read_text(encoding="utf-8"))


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


def results_json(results: list[ExampleResult], runtime: dict, outcome: str | None = None) -> dict:
    """The report: each example's result. With `outcome`, the check's verdict too: passed, failed (an example ran and
    didn't match), unsatisfiable (the pins can't be installed together, so nothing ran) or error (the runtime couldn't
    be built for another reason)."""
    out = {"outcome": outcome} if outcome else {}
    return {**out, "runtime": runtime, "passing": sum(r.passing for r in results), "total": len(results),
            "examples": [asdict(r) for r in results]}


def describe_versions(versions: dict, direct: list[str]) -> str:
    """'Python 3.12.15 · pandas 2.2.3': the Python version and every library the example imports directly."""
    parts = [f"Python {versions['python']}"] if "python" in versions else []
    parts += [f"{d} {versions[d]}" for d in direct if d in versions]
    return " · ".join(parts)


# ---------------------------------------------------------------- side by side


# The share of the limit an example's last time may take, multiplied by the examples running beside it, for it to share
# the machine: each starts its numeric libraries' threads as if the machine were its own, so beside N others a busy one
# may take up to N times as long. Half leaves the limit twice that worst case.
SHARE_OF_LIMIT = 0.5


def plan_side_by_side(ids: list[str], seconds: dict[str, float], jobs: int, timeout: float) -> tuple[list[str], list[str]]:
    """Which examples share the machine, longest first so the last to start are the shortest, and which run alone after
    them: one with no recorded time, and one whose time beside `jobs` - 1 others could near the limit."""
    shared, alone = [], []
    for eid in ids:
        t = seconds.get(eid)
        fits = isinstance(t, (int, float)) and not isinstance(t, bool) and 0 <= t and t * jobs <= timeout * SHARE_OF_LIMIT
        (shared if fits else alone).append(eid)
    shared.sort(key=lambda eid: (-seconds[eid], eid))
    return shared, alone


def side_by_side(ids: list[str], run, jobs: int, seconds: dict[str, float], timeout: float) -> list:
    """`run` for each example, `jobs` at a time where plan_side_by_side lets them share, the rest one at a time after,
    in `ids`' order either way. Each run is a process of its own, in a scratch folder of its own, so only the time it
    takes can change with what runs beside it. One job runs every example in turn, as before."""
    if jobs <= 1 or len(ids) < 2:
        return [run(eid) for eid in ids]
    from concurrent.futures import ThreadPoolExecutor
    shared, alone = plan_side_by_side(ids, seconds, jobs, timeout)
    done = {}
    if shared:
        with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="re-example") as pool:
            for eid, result in zip(shared, pool.map(run, shared)):
                done[eid] = result
    for eid in alone:
        done[eid] = run(eid)
    return [done[eid] for eid in ids]


def recorded_seconds(report: dict | None) -> dict[str, float]:
    """Each example's time from a run's report: a --report file, or an edition's examples.json, whose examples that
    didn't run keep the time of the run that did."""
    out = {}
    for e in (report or {}).get("examples") or []:
        if isinstance(e, dict) and isinstance(e.get("example_id"), str) and isinstance(e.get("seconds"), (int, float)) \
                and not isinstance(e.get("seconds"), bool) and e["seconds"] > 0:
            out[e["example_id"]] = float(e["seconds"])
    return out
