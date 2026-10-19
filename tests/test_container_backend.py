"""The container backend's commands, with an optional registry as a cache. No container engine runs here: the
commands are recorded by a stand-in for subprocess.run."""
import subprocess

import pytest

from re_standards import examples

RT = examples.Runtime("3.12.15", "pandas==2.2.2\n")
REGISTRY = "registry.example/project/runtime"


class Engine:
    """Records each command and answers with the exit code given for its verb (pull, build, push)."""

    def __init__(self, **codes):
        self.codes, self.calls = codes, []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, self.codes.get(cmd[1], 0), "", f"{cmd[1]} said no")

    @property
    def verbs(self):
        return [c[1] for c in self.calls]


@pytest.fixture
def engine(monkeypatch):
    def install(**codes):
        fake = Engine(**codes)
        monkeypatch.setattr(examples.subprocess, "run", fake)
        return fake
    return install


def test_without_a_registry_it_builds_every_time_and_never_pushes(engine, monkeypatch):
    monkeypatch.delenv("RE_EXAMPLES_REGISTRY", raising=False)
    backend = examples.ContainerBackend()
    fake = engine()
    backend.prepare(RT)
    assert fake.verbs == ["build"]
    assert backend.image(RT) == backend.tag(RT) == f"re-examples:py3.12.15-{RT.key}-{examples.dockerfile_key()}"
    build = fake.calls[0]
    assert build[build.index("-t") + 1] == backend.image(RT) and f"PYTHON_VERSION={RT.python}" in build


def test_the_registry_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("RE_EXAMPLES_REGISTRY", REGISTRY + "/")
    backend = examples.backend_named("container")
    assert backend.registry == REGISTRY and backend.image(RT) == f"{REGISTRY}/{backend.tag(RT)}"
    assert examples.ContainerBackend(registry="").registry == ""          # an explicit empty one wins


def test_a_cached_image_is_pulled_and_not_built(engine):
    backend = examples.ContainerBackend(registry=REGISTRY)
    fake = engine(pull=0)
    backend.prepare(RT)
    assert fake.calls == [["docker", "pull", "--quiet", f"{REGISTRY}/{backend.tag(RT)}"]]


def test_a_missing_image_is_built_and_pushed(engine):
    backend = examples.ContainerBackend(registry=REGISTRY)
    fake = engine(pull=1)
    backend.prepare(RT)
    ref = f"{REGISTRY}/{backend.tag(RT)}"
    assert fake.verbs == ["pull", "build", "push"]
    assert fake.calls[1][fake.calls[1].index("-t") + 1] == ref and fake.calls[2] == ["docker", "push", "--quiet", ref]


def test_a_failed_push_warns_and_a_failed_build_fails(engine, capsys):
    backend = examples.ContainerBackend(registry=REGISTRY)
    engine(pull=1, push=1)
    backend.prepare(RT)                                           # the image is built, so the examples can run
    assert "could not push" in capsys.readouterr().err
    engine(pull=1, build=1)
    with pytest.raises(examples.ExamplesError, match="could not build"):
        backend.prepare(RT)


def test_runs_the_registry_image_offline_with_the_clean_environment(tmp_path):
    backend = examples.ContainerBackend(registry=REGISTRY)
    cmd, _ = backend.command(RT, tmp_path, "load-orders.py")
    assert cmd[:5] == ["docker", "run", "--rm", "--network", "none"] and backend.image(RT) in cmd
    env = {cmd[i + 1].split("=", 1)[0]: cmd[i + 1].split("=", 1)[1] for i, x in enumerate(cmd) if x == "-e"}
    assert env["PYTHONHASHSEED"] == "0" and env["TZ"] == "UTC" and env["HOME"] == "/work"
    assert env["RE_EXAMPLE_REPORT"] == "/work/.re_report.json" and "PATH" not in env
    assert "--user" in cmd


def test_the_description_names_the_image_without_its_registry():
    """What a release record keeps is the same image name locally and in CI."""
    with_registry = examples.ContainerBackend(registry=REGISTRY).describe(RT)
    assert with_registry["image"] == examples.ContainerBackend(registry="").describe(RT)["image"]
    assert REGISTRY not in str(with_registry) and with_registry["network"] == "none"
