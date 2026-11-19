"""The writing standards' section 15, command chapters, where a check holds a rule: the step format refuses what prints
differently every run (W-70), what reaches beyond the machine and the cluster (W-74) and what bash 3.2 can't run (W-76);
the stack refuses an image its manifests name that it doesn't pin (W-74); and the local lab runs steps with a newer bash
where there is one."""
import shutil
import subprocess
from pathlib import Path

import pytest

from re_standards import bookfmt, labscripts, stack, steps

FIXTURES = Path(__file__).parent / "fixtures"


def problems(text: str) -> list[str]:
    return steps.parse_step(text, "a-step", "examples/a-step.sh")[1]


@pytest.mark.parametrize("text", ["echo $RANDOM\n", "name=web-${RANDOM}\n", "uuidgen\n", "head -c 8 /dev/urandom | od\n"])
def test_what_prints_differently_every_run_is_refused(text):
    assert any("W-70" in p for p in problems(text)), text


def test_the_time_and_a_jobs_pid_need_their_masks():
    assert any("W-70: date prints the time" in p for p in problems('echo "at $(date +%F)"\n'))
    assert problems('#| mask: time\necho "at $(date +%F)"\n') == []
    assert any("W-70: a job started with &" in p for p in problems("tail -f project/events.log &\n"))
    assert problems("#| mask: job\ntail -f project/events.log &\n") == []
    assert problems("#| tab: log\n#| background\ntail -f project/events.log\n") == []
    assert problems("#| compare: none\n( touch ready ) &\n") == []                 # nothing it prints is compared
    assert problems("make build && make test\nls > out 2>&1\n") == []
    assert steps.mask("[1] 48213\n[2]+ 48290\n", ("job",)) == "[1] <pid>\n[2]+ <pid>\n"


@pytest.mark.parametrize("text", [
    "helm repo add strimzi https://strimzi.io/charts/\n", "kubectl apply -f https://example.com/deploy.yaml\n",
    "curl -fsS https://example.com/data.csv -o data.csv\n", "git clone https://github.com/example/repo\n",
    "pip install requests\n", "docker pull nginx:1.27.3\n", "helm install kafka oci://registry.example/charts/kafka\n"])
def test_what_reaches_beyond_the_cluster_is_refused(text):
    assert any("W-74" in p for p in problems(text)), text


@pytest.mark.parametrize("text", [
    "curl -fsS http://127.0.0.1:8080/\n", "curl -fsS http://localhost:9090/metrics\n",
    "kubectl run probe --image=docker.io/library/busybox:1.37 --rm -i --restart=Never -- wget -qO- http://web.shop.svc.cluster.local\n",
    "curl -s http://10.43.0.10:53\n", "helm install strimzi charts/strimzi-kafka-operator-0.45.0.tgz\n"])
def test_the_machine_and_the_cluster_are_in_reach(text):
    assert [p for p in problems(text) if "W-74" in p] == [], text


def test_a_wait_that_reaches_beyond_the_cluster_is_refused():
    found = problems("#| wait: curl -fsS https://example.com/ready\nkubectl apply -f manifests/web.yaml\n")
    assert found == ["examples/a-step.sh: #| wait: curl -fsS https://example.com/ready: W-74: example.com is beyond this "
                     "machine and the cluster, which nothing in a Lab can reach"]


@pytest.mark.parametrize("text", [
    "declare -A seen\n", "local -n ref=items\n", "mapfile -t lines < project/items\n", "echo ${name,,}\n",
    "echo ${name^^}\n", "echo ${name@Q}\n", "echo ${items[-1]}\n", "make &>> build.log\n", "make |& tee log\n",
    "coproc server { nc -l 8080; }\n", "wait -n\n", "shopt -s globstar\n", "for i in {01..10}; do echo $i; done\n",
    "for i in {1..10..2}; do echo $i; done\n", "echo $EPOCHSECONDS\n"])
def test_what_bash_3_2_cant_run_is_refused(text):
    assert any("W-76" in p for p in problems(text)), text


@pytest.mark.parametrize("text", [
    'echo "${name:-default}"\n', "echo ${#items[@]}\n", "local -a items\n", "for i in {1..10}; do echo $i; done\n",
    "echo ${name%,*}\n", "case $x in a) echo a ;; esac\n", "declare -r pinned=1\n"])
def test_what_bash_3_2_runs_passes(text):
    assert [p for p in problems(text) if "W-76" in p] == [], text


def test_comment_lines_are_never_read_as_commands():
    assert problems("# helm repo add strimzi https://strimzi.io/charts/ is how you'd do it elsewhere\nkubectl get ns\n") == []


def test_the_samplers_keep_every_rule():
    for name in ("terminal-sampler", "k3s-sampler"):
        assert bookfmt.load_book(FIXTURES / name).problems == [], name
    assert labscripts.check(bookfmt.load_book(FIXTURES / "k3s-sampler")) == ([], [])     # its local lab, as generated


# ---------------------------------------------------------------- the stack's images, as the manifests name them


@pytest.fixture
def sampler(tmp_path) -> Path:
    root = tmp_path / "k3s-sampler"
    shutil.copytree(FIXTURES / "k3s-sampler", root)
    return root


def test_every_image_a_manifest_names_is_pinned_by_its_tag(sampler):
    book = bookfmt.load_book(sampler)
    assert stack.check(sampler, book.manifest)[0] == []
    manifest = sampler / "examples" / "manifests" / "web-deployment.yaml"
    text = manifest.read_text()
    digest = stack.read_pinned(sampler).images[0]["digest"]
    for image, want in (("docker.io/library/nginx:1.27.4", "isn't an image examples/stack.toml pins"),
                        (f"docker.io/library/nginx@{digest}", "names an image by digest"),
                        ("docker.io/library/nginx:latest", "has no version of its own"),
                        ("nginx", "has no version of its own")):
        manifest.write_text(text.replace("docker.io/library/nginx:1.27.3", image))
        found = stack.check(sampler, book.manifest)[0]
        assert len(found) == 1 and want in found[0] and found[0].startswith("examples/manifests/web-deployment.yaml:18: "), found
    manifest.write_text(text.replace("docker.io/library/nginx:1.27.3", "nginx:1.27.3"))      # Docker Hub's short name
    assert stack.check(sampler, book.manifest)[0] == []
    manifest.write_text(text.replace("IfNotPresent", "Always"))
    assert any("imagePullPolicy: Always pulls every time" in p for p in stack.check(sampler, book.manifest)[0])


def test_the_latest_tag_is_never_pinned(sampler):
    path = sampler / "examples" / "stack.in.toml"
    path.write_text(path.read_text().replace("nginx:1.27.3", "nginx:latest"))
    assert any("the latest tag" in p for p in stack.check(sampler, bookfmt.load_book(sampler).manifest)[0])


# ---------------------------------------------------------------- the local lab's bash


def test_the_local_lab_runs_steps_with_a_newer_bash_where_there_is_one(sampler):
    scripts = labscripts.scripts(bookfmt.load_book(sampler))
    for name in ("lab/chapter.sh", "lab/check.sh"):
        text = scripts[name]
        assert "steps_bash() {" in text and 'bash_bin=$(steps_bash)' in text and '"$bash_bin" ' in text
        assert " bash \"$book_dir" not in text and " bash -c " not in text
        assert subprocess.run(["sh", "-n"], input=text, text=True).returncode == 0


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_steps_bash_prefers_a_bash_of_4_or_later_and_takes_3_2_when_its_all_there_is(tmp_path):
    fn = "fail() { printf '%s\\n' \"$*\" >&2; exit 1; }\n" + "\n".join(labscripts._bash())
    old = tmp_path / "old"
    old.mkdir()
    (old / "bash").write_text('#!/bin/sh\ncase "$2" in *BASH_VERSINFO*) exit 1 ;; esac\nexec /bin/sh "$@"\n')
    (old / "bash").chmod(0o755)
    found = subprocess.run(["sh", "-c", fn + '\nprintf "%s" "$bash_bin"'], capture_output=True, text=True,
                           env={"PATH": f"{old}:/usr/bin:/bin", "HOME": str(tmp_path)})
    assert found.returncode == 0
    newer = [b for b in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash") if Path(b).exists()]
    assert found.stdout == (newer[0] if newer else str(old / "bash"))
    real = subprocess.run(["sh", "-c", fn + '\nprintf "%s" "$bash_bin"'], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert real.stdout == shutil.which("bash", path="/usr/bin:/bin")
