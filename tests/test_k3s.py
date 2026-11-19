"""The k3s backend (k3s.py) with a fake machine: what it installs and checks by SHA-256, the fixed flags, the fence, the
clean snapshot restored per chapter, the images exported by digest; then a chapter of the sampler run end to end through
the runner, with a fake kubectl, so the first real cluster is the pull request's job on GitHub. And the selection of
chapters a change affects (commands.select_chapters)."""
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from re_standards import bookfmt, cli, commands, examples, k3s, stack

SAMPLER = Path(__file__).parent / "fixtures" / "k3s-sampler"

FAKE_KUBECTL = r"""#!/usr/bin/env bash
# A stand-in for kubectl: a cluster of one namespace and one deployment, kept in files beside the kubeconfig, so each
# chapter's fresh home is a fresh cluster.
state="$(dirname "$KUBECONFIG")/state"; mkdir -p "$state"
ns=""; args=()
while [ $# -gt 0 ]; do case "$1" in -n) ns="$2"; shift 2 ;; *) args+=("$1"); shift ;; esac; done
set -- "${args[@]}"
case "$*" in
  "create namespace shop") mkdir "$state/ns-shop" && echo "namespace/shop created" ;;
  "get namespace shop") [ -d "$state/ns-shop" ] || { echo 'Error from server (NotFound): namespaces "shop" not found' >&2; exit 1; }
                        printf 'NAME   STATUS   AGE\nshop   Active   %ss\n' "$RANDOM" ;;
  "apply -f manifests/web-deployment.yaml") [ -d "$state/ns-shop" ] || { echo 'namespaces "shop" not found' >&2; exit 1; }
                        echo 3 > "$state/web"; echo "deployment.apps/web created" ;;
  "get deployment web -o jsonpath={.status.availableReplicas}") [ -f "$state/web" ] || exit 1; printf '%s' "$(cat "$state/web")" ;;
  "get pods -l app=web") a=bcdfghjklmnpqrstvwxz2456789; printf 'NAME                   READY   STATUS    RESTARTS   AGE\n'
                        for i in $(seq "$(cat "$state/web")"); do s=""; for j in 1 2 3 4 5; do s="$s${a:RANDOM%27:1}"; done
                          printf 'web-7d9c5b8f6d-%s   1/1     Running   0          %ss\n' "$s" "$((RANDOM % 50 + 1))"; done ;;
  *) echo "the fake kubectl doesn't know: $*" >&2; exit 2 ;;
esac
"""


def helm_archive() -> bytes:
    """The same bytes every time: gzip's header holds a time, so it's 0 here, or two builds a second apart differ and the
    pins made with one don't match the other (a flake under load, Nov 19, 2026)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for platform in ("linux-amd64", "linux-arm64", "darwin-arm64"):
            data = f"#!/bin/sh\necho helm for {platform}\n".encode()
            info = tarfile.TarInfo(f"{platform}/helm")
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Files:
    """Every file the sampler's stack pins, fake, by URL; and a fetch for stack.pin that answers as each publisher does."""

    def __init__(self):
        self.by_name = {"k3s": b"fake k3s\n", "k3s-airgap-images-amd64.tar.zst": b"fake airgap images\n",
                        "kubectl": FAKE_KUBECTL.encode(), "helm": helm_archive()}
        self.urls: dict[str, bytes] = {}

    def body(self, url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        if name.startswith("k3d-"):
            return f"fake {name}\n".encode()
        if name.startswith("helm-"):
            return self.by_name["helm"]
        return self.by_name[name]

    def fetch(self, url: str, headers: dict) -> tuple[bytes, dict]:
        if url.endswith("sha256sum-amd64.txt"):
            return (f"{sha(self.by_name['k3s'])}  k3s\n{sha(self.by_name['k3s-airgap-images-amd64.tar.zst'])}  "
                    "k3s-airgap-images-amd64.tar.zst\n").encode(), {}
        if url.endswith("checksums.txt"):
            names = [f"k3d-{p}" for p in ("linux-amd64", "linux-arm64", "darwin-arm64")]
            return "".join(f"{sha(f'fake {n}'.encode() + b'\n')}  {n}\n" for n in names).encode(), {}
        if url.endswith((".sha256", ".sha256sum")):
            target = url.rsplit(".", 1)[0]
            return f"{sha(self.body(target))}  {target.rsplit('/', 1)[-1]}\n".encode(), {}
        if "/token?" in url:
            return b'{"token": "anonymous"}', {}
        if "/manifests/" in url:
            return b"", {"docker-content-digest": "sha256:" + sha(url.encode())}
        raise AssertionError(f"the fake fetch wasn't asked for {url}")


class FakeHost(k3s.Host):
    """The machine, recorded: what runs as root is kept, never run; files land under `root`, but a path already in the
    test's own folder; kubectl answers Ready once `ready_after` seconds have passed."""

    def __init__(self, files: Files, root: Path, keep: Path, ready_after: float = 0, memory: dict | None = None,
                 tools=("docker",)):
        self.files, self.root, self.keep = files, root, keep
        self.calls: list[tuple] = []
        self.fetched: list[str] = []
        self.clock = 0.0
        self.ready_after = ready_after
        self.memory = memory or {}
        self.tools = tools
        self.root_prefix = []
        self.ctr_images = ""                 # what `k3s ctr images list --quiet` answers: the images k3s has imported
        self.missing: set[str] = set()       # tools root's PATH lacks, as the tool check finds them
        self.absent: set[str] = set()        # paths `test` finds missing
        self.du: dict[str, int] = {}         # what `du -sb` counts, by path

    def where(self, path) -> Path:
        path = Path(path)
        return path if str(path).startswith(str(self.keep)) else self.root / str(path).lstrip("/")

    def run(self, argv, *, root=False, check=True, timeout=None, env=None):
        argv = [str(a) for a in argv]
        self.calls.append(("run", root, argv))
        rc, out = 0, b""
        if argv[0].endswith("kubectl") and argv[1:2] != ["kubectl"]:
            rc = 0 if self.clock >= self.ready_after else 1
        elif argv[0] == "cat":
            out = b"apiVersion: v1\nkind: Config\n"
        elif argv[1:3] == ["ctr", "--namespace"]:
            out = self.ctr_images.encode()
        elif argv[0] == "test":
            rc = 1 if argv[-1] in self.absent else 0
        elif argv[:2] == ["du", "-sb"]:
            rc, out = (0, f"{self.du[argv[2]]}\t{argv[2]}\n".encode()) if argv[2] in self.du else (1, b"")
        elif argv[:2] == ["docker", "save"]:
            Path(argv[3]).write_bytes(f"image archive of {argv[4]}\n".encode())
        elif argv[0] == "skopeo":
            Path(argv[-1].split(":")[1]).write_bytes(f"image archive of {argv[-2]}\n".encode())
        if check and rc:
            raise commands.CommandsError(f"{argv} failed")
        return subprocess.CompletedProcess(argv, rc, out, b"")

    def script(self, text, *, timeout=None, check=True):
        self.calls.append(("script", text))
        out = b""
        if text.startswith("for t in ") and "command -v" in text:          # the tool check: the missing ones, by name
            listed = text[len("for t in "):].split(";", 1)[0].split()
            out = "".join(f"{t}\n" for t in listed if t in self.missing).encode()
        return subprocess.CompletedProcess(["sh"], 0, out, b"")

    def fetch(self, url, dest):
        self.fetched.append(url)
        dest.write_bytes(self.files.body(url))

    def install(self, src, dest, mode=0o644):
        self.calls.append(("install", str(dest)))
        target = self.where(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        target.chmod(mode)

    def write(self, dest, text, mode=0o644):
        self.calls.append(("write", str(dest)))
        target = self.where(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def which(self, name):
        return f"/usr/bin/{name}" if name in self.tools else None

    def read(self, path):
        return self.memory.get(path)

    def sha256(self, path):
        target = self.where(path)
        return sha(target.read_bytes()) if target.is_file() else None

    def monotonic(self):
        return self.clock

    def pause(self, seconds):
        self.clock += seconds

    def scripts(self) -> list[str]:
        return [c[1] for c in self.calls if c[0] == "script"]

    def ran(self) -> list[list[str]]:
        return [c[2] for c in self.calls if c[0] == "run"]


@pytest.fixture
def book_root(tmp_path) -> Path:
    """The sampler, its stack pinned again against the fake files."""
    root = tmp_path / "book"
    shutil.copytree(SAMPLER, root)
    files = Files()
    (root / stack.STACK).write_text(stack.pin(root, bookfmt.load_book(root).manifest, fetch=files.fetch))
    return root


def setup(tmp_path, book_root, **kw):
    files = Files()
    keep = tmp_path
    host = FakeHost(files, tmp_path / "machine", keep, **{k: v for k, v in kw.items() if k in ("ready_after", "memory", "tools")})
    book = bookfmt.load_book(book_root)
    pinned = stack.read_pinned(book_root)
    images = tmp_path / "images"
    k3s.export_images(pinned, images, host=host)
    cfg = {"tools_dir": str(tmp_path / "tools"), "as_user": [], **kw.get("cfg", {})}
    backend = k3s.K3sBackend(book, block_network=kw.get("block_network", False), host=host, cfg=cfg, images=images,
                             cache=tmp_path / "cache")
    return book, host, backend


# ---------------------------------------------------------------- what k3s is given


def test_the_fixed_flags_are_the_same_everywhere():
    cfg = k3s.settings()
    text = k3s.config_yaml(cfg)
    for line in ('node-name: "lab"', 'cluster-cidr: "10.42.0.0/16"', 'service-cidr: "10.43.0.0/16"',
                 'cluster-dns: "10.43.0.10"', '  - "traefik"', '  - "servicelb"', "disable-default-registry-endpoint: true",
                 'write-kubeconfig-mode: "0644"'):
        assert line in text.splitlines()
    assert '"*":' in k3s.registries_yaml(cfg) and '"http://127.0.0.1:1"' in k3s.registries_yaml(cfg)
    unit = k3s.unit_text(cfg)
    assert "Type=notify" in unit and "Restart=no" in unit and "--config /etc/rancher/k3s/config.yaml" in unit


def test_the_fence_lets_the_steps_and_the_pods_reach_only_the_cluster():
    cfg = k3s.settings()
    text = k3s.fence_script(cfg)
    assert "iptables -I OUTPUT 1 -m owner --uid-owner reader -j RE-FENCE" in text
    assert "iptables -I FORWARD 1 -s 10.42.0.0/16 -j RE-FENCE" in text
    assert "iptables -A RE-FENCE -o lo -j RETURN" in text
    assert "iptables -A RE-FENCE -d 10.43.0.0/16 -j RETURN" in text
    assert text.index("iptables -A RE-FENCE -j REJECT") < text.index("iptables -I OUTPUT")
    assert "ip6tables -A RE-FENCE -j REJECT" in text                         # and no IPv6 beyond this machine
    removed = k3s.fence_script(cfg, remove=True)
    assert "-j REJECT" not in removed and "iptables -X RE-FENCE" in removed
    # stopping k3s cleans its own rules and flannel's, never the fence's
    killall = k3s.killall_script(cfg)
    assert "grep -v KUBE- | grep -v CNI- | grep -iv flannel" in killall and "RE-FENCE" not in killall


def test_a_restore_keeps_the_image_store_and_restores_everything_else():
    cfg = k3s.settings()
    restore = k3s.restore_script(cfg)
    assert "rsync -aHAX --numeric-ids --delete --exclude=/agent/containerd/io.containerd.content.v1.content/ " \
           "/var/lib/re-k3s/clean/ /var/lib/rancher/k3s/" in restore
    snap = k3s.snapshot_script(cfg)
    assert snap.index("agent/images") < snap.index("rsync -a")              # imported images leave the import folder first
    assert "rsync -aHAX --numeric-ids --delete " in snap


@pytest.mark.skipif(shutil.which("rsync") is None, reason="needs rsync")
def test_the_clean_copy_keeps_hard_links_extended_attributes_and_device_files(tmp_path):
    """The copy, as the backend runs it, on real files: a layer's hard links stay one file, and the extended attribute
    overlayfs marks an opaque folder with survives (trusted.* is root's alone, so here a user.* one stands for it; the
    flags that copy one copy the other). Plain -a dropped both."""
    src, dst = tmp_path / "data", tmp_path / "clean"
    (src / "layer" / "opaque").mkdir(parents=True)
    (src / "layer" / "perl").write_text("#!perl\n")
    os.link(src / "layer" / "perl", src / "layer" / "perl5.38")
    try:
        os.setxattr(src / "layer" / "opaque", "user.overlay.opaque", b"y")
    except OSError:
        pytest.skip("this filesystem keeps no extended attributes")
    cfg = {**k3s.settings(), "snapshot_keep": ["content/"]}
    subprocess.run(["sh", "-c", f"mkdir -p {dst} && {k3s._mirror(cfg, str(src), str(dst))}"], check=True)
    assert os.stat(dst / "layer" / "perl").st_ino == os.stat(dst / "layer" / "perl5.38").st_ino
    assert os.getxattr(dst / "layer" / "opaque", "user.overlay.opaque") == b"y"
    (dst / "layer" / "perl").write_text("changed in a chapter\n")                 # and a restore puts it back
    subprocess.run(["sh", "-c", k3s._mirror(cfg, str(src), str(dst))], check=True)
    assert (dst / "layer" / "perl5.38").read_text() == "#!perl\n"


# ---------------------------------------------------------------- installing, checked by SHA-256


def test_install_fetches_each_pinned_file_once_checked_by_its_sha256(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root)
    backend.install()
    machine = tmp_path / "machine"
    assert (machine / "usr/local/bin/k3s").read_bytes() == b"fake k3s\n"
    assert (machine / "var/lib/rancher/k3s/agent/images/k3s-airgap-images-amd64.tar.zst").exists()
    assert (tmp_path / "tools" / "kubectl").read_text().startswith("#!/usr/bin/env bash")
    assert (tmp_path / "tools" / "helm").read_text() == "#!/bin/sh\necho helm for linux-amd64\n"
    assert (machine / "var/lib/rancher/k3s/agent/images/stack-000.tar").read_text().startswith("image archive of")
    assert (machine / "etc/rancher/k3s/config.yaml").read_text() == k3s.config_yaml(backend.cfg)
    assert (machine / "etc/systemd/system/re-k3s.service").exists()
    assert ["systemctl", "daemon-reload"] in host.ran()
    first = len(host.fetched)
    assert first == 4                                         # k3s, its airgap images, kubectl, helm: linux-amd64 alone
    backend.install()
    assert len(host.fetched) == first                         # the cache holds them now


def test_a_file_that_isnt_the_pinned_one_is_refused(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root)
    host.files.by_name["k3s"] = b"something else\n"
    with pytest.raises(commands.CommandsError, match="isn't the file the stack pins"):
        backend.install()
    assert not list((tmp_path / "cache" / "files").glob("*.part"))
    assert not (tmp_path / "machine" / "usr/local/bin/k3s").exists()


def test_a_stack_without_k3s_pinned_has_no_k3s_backend(tmp_path, book_root):
    (book_root / stack.STACK).unlink()
    book = bookfmt.load_book(book_root)
    with pytest.raises(commands.CommandsError, match="need k3s pinned"):
        commands.backend_for(book)
    with pytest.raises(commands.CommandsError, match="the k3s backend runs a stack of k3s"):
        commands.backend_for(bookfmt.load_book(Path(__file__).parent / "fixtures" / "terminal-sampler"), "k3s")
    with pytest.raises(commands.CommandsError, match="the compose backend runs a stack of compose"):
        commands.backend_for(book, "compose")                                  # built since TL13, for compose stacks
    with pytest.raises(commands.CommandsError, match="isn't built yet"):
        commands.backend_for(book, "nomad")


def test_the_books_stack_picks_its_backend(tmp_path, book_root, monkeypatch):
    monkeypatch.setenv("RE_STACK_CACHE", str(tmp_path / "cache"))
    backend = commands.backend_for(bookfmt.load_book(book_root))
    assert isinstance(backend, k3s.K3sBackend) and backend.images == tmp_path / "cache" / f"images-{backend.pinned.digest()}"
    plain = commands.backend_for(bookfmt.load_book(Path(__file__).parent / "fixtures" / "terminal-sampler"),
                                 block_network=False)
    assert isinstance(plain, commands.LocalBackend)


# ---------------------------------------------------------------- the stack's images


def test_images_are_exported_by_digest_under_their_tag(tmp_path, book_root):
    host = FakeHost(Files(), tmp_path / "machine", tmp_path)
    pinned = stack.read_pinned(book_root)
    out = tmp_path / "images"
    listed = k3s.export_images(pinned, out, host=host)
    image = pinned.images[0]
    assert ["docker", "pull", "--quiet", "--platform", "linux/amd64", f"docker.io/library/nginx@{image['digest']}"] in host.ran()
    assert ["docker", "tag", f"docker.io/library/nginx@{image['digest']}", "docker.io/library/nginx:1.27.3"] in host.ran()
    assert listed == json.loads((out / "images.json").read_text())
    assert k3s.image_archives(pinned, out) == [out / listed[0]["file"]]
    pulls = len(host.ran())
    k3s.export_images(pinned, out, host=host)
    assert len(host.ran()) == pulls                            # already exported for its digest


def test_skopeo_exports_without_a_daemon(tmp_path, book_root):
    host = FakeHost(Files(), tmp_path / "machine", tmp_path, tools=("skopeo", "docker"))
    pinned = stack.read_pinned(book_root)
    k3s.export_images(pinned, tmp_path / "images", host=host)
    copy = next(a for a in host.ran() if a[0] == "skopeo")
    assert copy[-2] == f"docker://docker.io/library/nginx@{pinned.images[0]['digest']}"
    assert copy[-1].endswith(":docker.io/library/nginx:1.27.3") and copy[-1].startswith("docker-archive:")


def test_images_missing_or_at_another_digest_are_said_before_anything_changes(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root)
    index = tmp_path / "images" / "images.json"
    listed = json.loads(index.read_text())
    listed[0]["digest"] = "sha256:" + "0" * 64
    index.write_text(json.dumps(listed))
    with pytest.raises(commands.CommandsError, match="at the pinned digest"):
        backend.install()
    assert host.scripts() == []
    index.unlink()
    with pytest.raises(commands.CommandsError, match="re-check stack --book . --images"):
        backend.install()


# ---------------------------------------------------------------- the clean cluster, per chapter


def test_each_chapter_starts_from_the_clean_snapshot(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root)
    ws = backend.start(book, "first-deployment")
    scripts = host.scripts()
    assert scripts[0] == k3s.tools_script(backend.tools())                    # the machine's tools, before anything
    wipe = next(i for i, s in enumerate(scripts) if s == k3s.wipe_script(backend.cfg))
    snap = scripts.index(k3s.snapshot_script(backend.cfg))
    assert wipe < snap                                        # installed fresh, Ready once and kept
    # the data dir is the clean copy as it is: the first chapter starts from it with no restore
    assert scripts[snap + 1:] == [k3s.killall_script(backend.cfg)] and k3s.restore_script(backend.cfg) not in scripts
    assert ws.env["PATH"].startswith(str(tmp_path / "tools") + ":")
    assert Path(ws.env["KUBECONFIG"]).read_text().startswith("apiVersion: v1")
    assert (ws.cwd / "manifests" / "web-deployment.yaml").exists() and not list(ws.cwd.glob("*.sh"))
    backend.stop(ws)
    assert not ws.root.exists()
    n = len(host.scripts())
    ws = backend.start(book, "scale-and-serve")
    later = host.scripts()[n:]
    assert later[:2] == [k3s.killall_script(backend.cfg), k3s.restore_script(backend.cfg)]
    assert k3s.wipe_script(backend.cfg) not in later and k3s.snapshot_script(backend.cfg) not in later
    backend.stop(ws)
    assert set(backend.describe()["ready_seconds"]) == {"first start", "first-deployment", "scale-and-serve"}


def test_a_cluster_that_isnt_ready_in_time_says_so_with_k3s_s_own_lines(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root, ready_after=10_000)
    with pytest.raises(commands.CommandsError, match=r"wasn't Ready within 180 s; kubectl get --raw=/readyz"):
        backend.start(book, "first-deployment")
    assert any(a[:3] == ["journalctl", "-u", "re-k3s"] for a in host.ran())


def test_the_steps_run_as_their_own_user_behind_the_fence(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root, block_network=True, cfg={"as_user": ["sudo", "-n", "-E", "-u", "{user}", "--"]})
    ws = backend.start(book, "first-deployment")
    assert k3s.fence_script(backend.cfg) in host.scripts() and k3s.user_script(backend.cfg) in host.scripts()
    assert ["chown", "-R", "reader:", str(ws.home), str(ws.cwd)] in host.ran()
    assert ws.wrap(["bash", "--login"]) == ["sudo", "-n", "-E", "-u", "reader", "--", "env", f"PATH={ws.env['PATH']}",
                                            "bash", "--login"]
    backend.stop(ws)
    assert ["pkill", "-9", "-u", "reader"] in host.ran()
    backend.close()
    assert host.scripts()[-1] == k3s.fence_script(backend.cfg, remove=True)
    assert backend.describe()["network"] == "blocked"


def test_without_a_user_of_their_own_the_network_cant_be_fenced(tmp_path, book_root, monkeypatch):
    book, host, backend = setup(tmp_path, book_root, block_network=True)
    monkeypatch.delenv("RE_COMMANDS_ALLOW_NETWORK", raising=False)
    with pytest.raises(commands.CommandsError, match="can't be fenced"):
        backend.prepare()
    monkeypatch.setenv("RE_COMMANDS_ALLOW_NETWORK", "1")
    backend.prepare()
    assert backend.describe()["network"] == "open"


def test_each_chapters_peak_memory_is_reported(tmp_path, book_root):
    paths = [p.format(unit="re-k3s") for p in k3s.MEMORY]
    book, host, backend = setup(tmp_path, book_root, memory={paths[0]: str(300 * 2**20), paths[1]: str(1700 * 2**20)})
    backend.stop(backend.start(book, "first-deployment"))
    assert backend.describe()["peak_memory_mib"] == {"first-deployment": 2000}


# ---------------------------------------------------------------- a machine image of the stack (bake)


def test_a_bake_leaves_out_only_the_first_start_s_logs_and_keeps_the_cluster():
    cfg = k3s.settings()
    text = k3s.image_logs_script(cfg)
    assert "rm -rf /var/log/pods /var/log/containers" in text
    assert "rm -f /var/lib/rancher/k3s/agent/containerd/containerd.log" in text
    for kept in ("/var/lib/rancher/k3s/server", "/etc/rancher/node", "/var/lib/kubelet", "/var/lib/re-k3s/clean"):
        assert kept not in text, kept                          # the datastore, TLS, tokens, node password, the copy


def test_a_bake_imports_the_stack_until_every_image_is_there_then_keeps_the_cluster_and_its_clean_copy(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root, block_network=True, cfg={"as_user": ["sudo", "-n", "--"]})
    host.ctr_images = "docker.io/rancher/mirrored-pause:3.6\ndocker.io/library/nginx:1.27.3\n"
    host.du = {"/var/lib/rancher/k3s": 6_300_000_000, "/var/lib/re-k3s/clean": 3_900_000_000}
    made = backend.bake()
    assert made == {"stack": backend.pinned.digest(), "k3s": "v1.31.4+k3s1", "ready_seconds": 0.0, "images": 1,
                    "data_bytes": 6_300_000_000, "clean_bytes": 3_900_000_000}
    scripts = host.scripts()
    cfg = backend.cfg
    assert scripts[0] == k3s.tools_script(backend.tools()) and "sudo" in backend.tools()
    assert scripts.index(k3s.wipe_script(cfg)) < scripts.index(k3s.fence_script(cfg))       # installed as prepare does
    assert scripts[-4:] == [k3s.killall_script(cfg), k3s.image_logs_script(cfg), k3s.snapshot_script(cfg),
                            k3s.fence_script(cfg, remove=True)]                 # the clean copy, in the image
    assert (tmp_path / "machine" / "var/lib/rancher/k3s/agent/images/stack-000.tar").exists()   # imported as k3s starts
    assert ["systemctl", "start", "re-k3s"] in host.ran()


def test_a_machine_without_a_tool_the_backend_runs_says_which_before_anything_changes(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root)
    host.missing = {"rsync", "iptables-save"}
    for go in (backend.prepare, backend.bake, lambda: backend.start(book, "first-deployment")):
        with pytest.raises(commands.CommandsError, match=r"this machine lacks rsync, iptables-save, which the k3s "
                                                         r"backend runs \(\[k3s\] host_tools\): install them first"):
            go()
    assert host.scripts() == [k3s.tools_script(backend.tools())] * 3 and not host.fetched
    assert backend.tools() == k3s.settings()["host_tools"]                     # no own user here: no sudo to check
    text = k3s.tools_script(["rsync", "ip"])
    assert text == 'for t in rsync ip; do command -v "$t" >/dev/null 2>&1 || echo "$t"; done\n'


def test_a_bake_that_s_ready_without_the_stack_s_images_fails(tmp_path, book_root):
    book, host, backend = setup(tmp_path, book_root, cfg={"ready_seconds": 5})
    with pytest.raises(commands.CommandsError, match="Ready without the stack's docker.io/library/nginx:1.27.3"):
        backend.bake()
    assert k3s.snapshot_script(backend.cfg) not in host.scripts()


def test_a_machine_from_the_stack_s_image_installs_nothing_and_starts_from_what_it_holds(tmp_path, book_root, monkeypatch):
    book, host, backend = setup(tmp_path, book_root)
    host.ctr_images = "docker.io/library/nginx:1.27.3"
    backend.bake()                                             # the image's disk, as the bake left it
    fetched = len(host.fetched)
    monkeypatch.setenv(k3s.BAKED, backend.pinned.digest())
    images = tmp_path / "no-images"                            # no archive and no cache: nothing to install from
    baked = k3s.K3sBackend(book, block_network=False, host=host, cfg=backend.cfg, images=images,
                           cache=tmp_path / "empty-cache")
    n = len(host.calls)
    ws = baked.start(book, "first-deployment")
    later = [c for c in host.calls[n:]]
    scripts = [c[1] for c in later if c[0] == "script"]
    assert k3s.wipe_script(baked.cfg) not in scripts and not [c for c in later if c[0] in ("install", "write")]
    runs = [c[2] for c in later if c[0] == "run"]
    for held in (["test", "-d", "/var/lib/rancher/k3s/agent/containerd"], ["test", "-d", "/var/lib/re-k3s/clean/server"],
                 ["test", "-f", "/etc/rancher/node/password"]):
        assert held in runs                                    # the store, the image's clean copy, the node's password
    # nothing copied at the start: the image's data dir is its clean copy, so k3s starts from it as it is
    assert k3s.snapshot_script(baked.cfg) not in scripts and k3s.restore_script(baked.cfg) not in scripts
    assert scripts == [k3s.tools_script(baked.tools()), k3s.killall_script(baked.cfg)]
    assert "first start" not in baked.describe()["ready_seconds"]
    assert len(host.fetched) == fetched and baked.describe()["from_image"] is True
    baked.stop(ws)
    n = len(host.scripts())
    baked.stop(baked.start(book, "scale-and-serve"))            # every later start restores, as before
    assert host.scripts()[n:n + 2] == [k3s.killall_script(baked.cfg), k3s.restore_script(baked.cfg)]
    # an image without the clean copy (made before the bake kept one) never starts as if it had it
    host.absent = {"/var/lib/re-k3s/clean/server"}
    with pytest.raises(commands.CommandsError, match=r"no clean copy of its cluster \(/var/lib/re-k3s/clean/server\)"):
        k3s.K3sBackend(book, block_network=False, host=host, cfg=backend.cfg, images=images).prepare()
    host.absent = set()
    # an image of another stack, or one whose k3s isn't the pinned file, never starts this book's cluster
    monkeypatch.setenv(k3s.BAKED, "0" * 64)
    other = k3s.K3sBackend(book, block_network=False, host=host, cfg=backend.cfg, images=images)
    with pytest.raises(commands.CommandsError, match="holds stack 0000000000000000, not this book's"):
        other.prepare()
    monkeypatch.setenv(k3s.BAKED, backend.pinned.digest())
    (tmp_path / "machine" / "usr/local/bin/k3s").write_bytes(b"another k3s\n")
    with pytest.raises(commands.CommandsError, match="no k3s at its pinned SHA-256"):
        k3s.K3sBackend(book, block_network=False, host=host, cfg=backend.cfg, images=images).prepare()
    with pytest.raises(commands.CommandsError, match="bake from the OS's own"):
        k3s.K3sBackend(book, block_network=False, host=host, cfg=backend.cfg, images=images).bake()


# ---------------------------------------------------------------- a chapter, end to end through the runner


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_a_chapter_runs_on_the_k3s_backend_and_records_the_same_twice(tmp_path, book_root, monkeypatch):
    """The runner and the backend together, with the fake kubectl the backend installs from the pins: the checks fail
    before their sections and pass after, the pods' suffixes and ages are masked, and --record writes outputs only once
    both runs printed the same after their masks."""
    if not examples.can_block_network():
        monkeypatch.setenv("RE_COMMANDS_ALLOW_NETWORK", "1")
    book, host, backend = setup(tmp_path, book_root)
    runs, problems, differences = commands.run_book(book, backend, ["first-deployment"], runs=2)
    assert problems == [], problems
    first = runs[0]
    assert [(r.step_id, r.phase, r.verdict) for r in first.results if r.kind == "check"] == [
        ("shop-namespace-exists", "before", "not-yet"), ("shop-namespace-exists", "chapter", "passed"),
        ("web-has-three-replicas", "before", "not-yet"), ("web-has-three-replicas", "chapter", "passed")]
    found = commands.recordable(book, runs)
    assert found["create-shop-namespace"] == "namespace/shop created\n"
    assert found["list-web-pods"].count("Running") == 3
    for sid, text in found.items():
        (book_root / "examples" / f"{sid}.out").write_text(text)
    book = bookfmt.load_book(book_root)
    again, problems, differences = commands.run_book(book, backend, ["first-deployment"])
    assert problems == [] and differences == [], differences
    assert [r.verdict for r in again[0].results if r.phase == "chapter" and r.kind == "step"] == ["same", "same", "same"]


# ---------------------------------------------------------------- which chapters run


def chapter_record(book) -> dict:
    return commands.record(book)


def test_every_chapter_runs_when_theres_nothing_to_compare_or_the_stack_or_runner_changed(book_root):
    book = bookfmt.load_book(book_root)
    assert commands.select_chapters(book, None).everything
    base = commands.record(book)
    assert commands.select_chapters(book, base).chapters == {}
    assert "pins changed" in commands.select_chapters(book, dict(base, stack_digest="other")).why
    assert "code that runs the steps" in commands.select_chapters(book, dict(base, runner="other")).why
    s = commands.select_chapters(book, base, changed=["examples/manifests/other.yaml"])
    assert s.everything and "any step may read it" in s.why
    assert not commands.select_chapters(book, base, changed=["lab/start.sh", "chapters/01-first-deployment.md"]).everything


def test_a_chapter_runs_when_its_steps_setup_or_outputs_change(book_root):
    before = commands.record(bookfmt.load_book(book_root))
    path = book_root / "examples" / "scale-web.sh"
    path.write_text(path.read_text().replace("--replicas=5", "--replicas=5 "))
    book = bookfmt.load_book(book_root)
    s = commands.select_chapters(book, before)
    assert s.chapters == {"scale-and-serve": ["its steps, checks, setup or files changed"]}
    # a setup step's change runs the chapters it brings to their start, as well as its own
    path = book_root / "examples" / "apply-web.sh"
    path.write_text(path.read_text() + "\n")
    s = commands.select_chapters(bookfmt.load_book(book_root), before)
    assert set(s.chapters) == {"first-deployment", "scale-and-serve"}
    s = commands.select_chapters(book, commands.record(book), changed=["examples/list-web-pods.out"])
    assert s.chapters == {"first-deployment": ["a recorded output changed (examples/list-web-pods.out)"]}


def test_a_chapter_whose_last_pass_is_old_runs_again_the_freshness_floor(book_root):
    book = bookfmt.load_book(book_root)
    now = datetime(2026, 11, 18, tzinfo=timezone.utc)
    rec = commands.record(book)
    rec["chapters"]["first-deployment"].update(passed=True, verified_at=(now - timedelta(days=8)).isoformat())
    rec["chapters"]["scale-and-serve"].update(passed=True, verified_at=(now - timedelta(days=2)).isoformat())
    s = commands.select_chapters(book, rec, now=now, floor_days=7)
    assert list(s.chapters) == ["first-deployment"] and s.floor == ["first-deployment"]
    assert "more than 7 days old" in s.chapters["first-deployment"][0]
    rec["chapters"]["scale-and-serve"]["passed"] = False
    assert set(commands.select_chapters(book, rec, now=now, floor_days=7).chapters) == {"first-deployment", "scale-and-serve"}


def test_the_cli_selects_against_a_recorded_run(tmp_path, book_root, capsys):
    book = bookfmt.load_book(book_root)
    report = tmp_path / "report.json"
    report.write_text(json.dumps(commands.results_json([], "passed", {}, book)))
    assert cli.main(["commands", "--book", str(book_root), "--affected", "--recorded", str(report), "--list"]) == 0
    assert "0 of 2 chapter(s) run" in capsys.readouterr().out
    assert cli.main(["commands", "--book", str(book_root), "--affected", "--recorded", str(report)]) == 0
    assert "no chapter can be affected by this change" in capsys.readouterr().out
    assert cli.main(["commands", "--book", str(book_root), "--list"]) == 1


def test_the_cli_selects_against_the_pull_requests_base(tmp_path, book_root, capsys):
    git = lambda *a: subprocess.run(["git", "-C", str(book_root), "-c", "user.name=t",            # noqa: E731
                                     "-c", "user.email=t@example.invalid", *a], check=True, capture_output=True)
    git("init", "-q")                                  # CI's runner has no git identity: every commit names one
    git("add", "-A")
    git("commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(book_root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    path = book_root / "examples" / "expose-web.sh"
    path.write_text(path.read_text().replace("--port=80", "--port=80 --name=web"))
    git("commit", "-qam", "change")
    assert cli.main(["commands", "--book", str(book_root), "--affected", "--base-ref", base, "--list"]) == 0
    out = capsys.readouterr().out
    assert "1 of 2 chapter(s) run" in out and "scale-and-serve: its steps, checks, setup or files changed" in out


def test_the_stack_digest_is_what_the_job_caches_by(book_root, capsys):
    assert cli.main(["stack", "--book", str(book_root), "--digest"]) == 0
    assert capsys.readouterr().out.strip() == stack.read_pinned(book_root).digest()
    assert cli.main(["stack", "--book", str(Path(__file__).parent / "fixtures" / "primer-chapter"), "--digest"]) == 0
    assert capsys.readouterr().out.strip() == "none"


def test_the_sampler_pins_are_real_and_complete():
    """The fixture the sampler repository is made from: its stack.toml is re-check stack --pin's, in step with
    stack.in.toml, every licence allowed."""
    book = bookfmt.load_book(SAMPLER)
    assert book.problems == []
    problems, pinned = stack.check(SAMPLER, book.manifest)
    assert problems == [] and pinned.tools["k3s"]["version"] == "v1.31.4+k3s1"


def test_a_machine_with_no_way_out_reads_the_pinned_files_from_the_urls_it_was_given(tmp_path, book_root, monkeypatch):
    """The Lab's keyless machine, and the cloud runner that records for an agent, get signed URLs for the pinned files
    (RE_STACK_FILES, by SHA-256): each is still checked by its SHA-256."""
    pinned = stack.read_pinned(book_root)
    k3s_sha = pinned.tools["k3s"]["platforms"]["linux-amd64"]["sha256"]
    monkeypatch.setenv("RE_STACK_FILES", json.dumps({k3s_sha: "https://storage.example/signed/k3s?sig=1"}))
    book, host, backend = setup(tmp_path, book_root)
    files = host.files
    real = files.body
    files.body = lambda url: real(pinned.tools["k3s"]["platforms"]["linux-amd64"]["url"]) if "signed" in url else real(url)
    backend.install()
    assert "https://storage.example/signed/k3s?sig=1" in host.fetched
    assert pinned.tools["k3s"]["platforms"]["linux-amd64"]["url"] not in host.fetched


@pytest.mark.skipif(not Path("/proc/self/exe").exists(), reason="the shims are told by /proc/{pid}/exe")
def test_killall_finds_the_shims_by_their_executable_and_never_itself(tmp_path):
    """GitHub's first real run: matched by command line, the script (run as `sh -c` with its own text) killed itself."""
    cfg = k3s.settings()
    line = next(x for x in k3s.killall_script(cfg).splitlines() if x.startswith("pids()"))
    shim = tmp_path / "k3s" / "data" / "abc123" / "bin" / "containerd-shim-runc-v2"
    shim.parent.mkdir(parents=True)
    # A copy of this Python, as the shim: a renamed coreutils binary may not run, since it picks its program by name
    import sys
    import time
    shutil.copy(sys.executable, shim)
    running = subprocess.Popen([str(shim), "-I", "-S", "-c", "import time; time.sleep(30)"], stderr=subprocess.DEVNULL)
    time.sleep(0.3)
    if running.poll() is not None:
        pytest.skip("a copy of this Python doesn't run here")
    try:
        # the pattern itself on this shell's command line, as on the real run's
        out = subprocess.run(["sh", "-c", f"{line}\n# */k3s/data/*/bin/containerd-shim*\npids; echo self $$"],
                             capture_output=True, text=True, check=True).stdout.split()
    finally:
        running.kill()
        running.wait()
    me = out[out.index("self") + 1]
    found = out[:out.index("self")]
    assert str(running.pid) in found
    assert me not in found
