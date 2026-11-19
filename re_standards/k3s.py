"""A k3s stack's backend for the runner (commands.py): each chapter on a fresh cluster, from examples/stack.toml.

    re-check stack --images      the stack's images, each by its digest, into the cache (needs the internet)
    re-check commands            each chapter on a cluster of its own, as K3sBackend starts it

Once on a machine, before the first chapter:

- **Install** from examples/stack.toml: k3s for linux-amd64 and its airgap images, and the stack's kubectl and helm. Each
  file is fetched once into the cache ([k3s] cache, or RE_STACK_CACHE) and checked by its SHA-256 before it's used: from
  its publisher, or on a machine with no way out, from the URL RE_STACK_FILES gives for its SHA-256. The stack's images,
  exported by digest (`re-check stack --images`), or one archive of them (RE_STACK_IMAGES), go beside the airgap images,
  where k3s imports them as it starts.
- **Fixed flags** ([k3s]): the node's name, the cluster's and services' CIDRs and DNS address, traefik and servicelb off,
  no default registry endpoint, and every registry mirrored to a closed port. An image the stack doesn't pin fails at
  once with ImagePullBackOff, as it would in a reader's Lab.
- **The fence**, with the network blocked (the default): the steps run as a user of their own ([k3s] steps_user), and
  iptables lets that user's processes, and the pods, reach only this machine and the cluster's own addresses.
- **Ready** within [k3s] ready_seconds: the API, the node and kube-system's deployments. Then k3s stops, the images it
  imported leave its import folder, and the clean data dir is kept ([k3s] snapshot_dir).

Then for each chapter:

1. k3s stops, and everything it ran is killed.
2. The clean data dir is restored. The image store's blobs, which never change, stay in place.
3. k3s starts and is Ready again.
4. The chapter gets a workspace with the book's files, an admin kubeconfig, and the stack's tools first on its PATH.

So every chapter starts from the same cluster, its certificates, UIDs and system pods included. Chapters can run in any
order, or on different machines. Each chapter's peak memory, k3s and its pods together, is sampled while it runs and
reported, so chapters can be written to the Lab's machine.

Everything that changes the machine goes through a Host. The real one runs as root through sudo. Tests give a fake, so
nothing here needs Docker, k3s or root to be tested. The first real run is the pull request's job on GitHub's
ubuntu-24.04, or the release's on Cloud Batch.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from . import commands, stack as stack_pins, steps as step_format
from .bookfmt import Book

AGENT = "re-standards (k3s)"
IMAGES_INDEX = "images.json"
ARCHIVES = (".tar", ".tar.zst", ".tar.gz", ".tar.lz4", ".tar.bz2")      # what k3s imports from its images folder
# The cgroups whose memory a chapter uses: k3s itself, under its unit, and the pods, under kubepods
MEMORY = ("/sys/fs/cgroup/system.slice/{unit}.service/memory.current", "/sys/fs/cgroup/kubepods/memory.current",
          "/sys/fs/cgroup/kubepods.slice/memory.current")


def settings() -> dict:
    return step_format.settings()["k3s"]


def cache_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or settings()
    return Path(os.environ.get("RE_STACK_CACHE") or cfg["cache"]).expanduser()


def images_dir(pinned: stack_pins.Pinned, cfg: dict | None = None) -> Path:
    """Where `re-check stack --images` keeps a stack's images: by the stack's digest, so a cache keyed by it holds them."""
    return cache_dir(cfg) / f"images-{pinned.digest()}"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- the machine


class Host:
    """The machine, as K3sBackend changes it: commands as root through sudo (or directly, when this runs as root), files
    fetched over HTTPS, and files written where only root may write. Tests pass a fake with the same methods."""

    def __init__(self, sudo: tuple[str, ...] = ("sudo", "-n")):
        self.root_prefix = [] if os.geteuid() == 0 else list(sudo)

    def run(self, argv: list[str], *, root: bool = False, check: bool = True, timeout: float | None = None,
            env: dict | None = None) -> subprocess.CompletedProcess:
        cmd = (self.root_prefix if root else []) + list(argv)
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise commands.CommandsError(f"{shlex.join(argv)[:200]} ran past {timeout:g} s") from None
        except FileNotFoundError:
            raise commands.CommandsError(f"{cmd[0]} isn't installed here") from None
        if check and r.returncode != 0:
            said = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()[-1500:]
            raise commands.CommandsError(f"{shlex.join(argv)[:200]} ended with exit code {r.returncode}" +
                                         (f":\n{said}" if said else ""))
        return r

    def script(self, text: str, *, timeout: float | None = None, check: bool = True) -> subprocess.CompletedProcess:
        """A shell script, as root."""
        return self.run(["sh", "-c", text], root=True, timeout=timeout, check=check)

    def fetch(self, url: str, dest: Path) -> None:
        """GET a public file: no credential is ever sent."""
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)

    def install(self, src: Path, dest: Path, mode: int = 0o644) -> None:
        """A file copied where only root may write, with its folders."""
        self.run(["install", "-D", "-m", f"{mode:o}", str(src), str(dest)], root=True)

    def write(self, dest: Path, text: str, mode: int = 0o644) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as t:
            t.write(text)
        try:
            self.install(Path(t.name), dest, mode)
        finally:
            os.unlink(t.name)

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def read(self, path: str) -> str | None:
        try:
            return Path(path).read_text()
        except OSError:
            return None

    def monotonic(self) -> float:
        return time.monotonic()

    def pause(self, seconds: float) -> None:
        time.sleep(seconds)          # the backend's own polling; a book's steps never sleep


# ---------------------------------------------------------------- what k3s is given


def _q(text: str) -> str:
    return json.dumps(text)


def config_yaml(cfg: dict) -> str:
    """k3s's config.yaml: the fixed flags, the same on every machine."""
    lines = ["# Written by re-check commands (k3s.py) from the standards' data/commands.toml [k3s]. Don't edit by hand.",
             f"node-name: {_q(cfg['node_name'])}",
             f"data-dir: {_q(cfg['data_dir'])}",
             f"cluster-cidr: {_q(cfg['cluster_cidr'])}",
             f"service-cidr: {_q(cfg['service_cidr'])}",
             f"cluster-dns: {_q(cfg['cluster_dns'])}",
             "disable:", *[f"  - {_q(x)}" for x in cfg["disable"]],
             "disable-default-registry-endpoint: true",
             f"write-kubeconfig: {_q(cfg['kubeconfig'])}",
             'write-kubeconfig-mode: "0644"']
    return "\n".join(lines) + "\n"


def registries_yaml(cfg: dict) -> str:
    """Every registry mirrored to a closed port on this machine: with the default endpoint off, nothing is ever pulled."""
    return ("# Written by re-check commands (k3s.py): no registry. Every image the steps run is imported from the stack's\n"
            "# pins, and anything else fails at once with ImagePullBackOff.\n"
            f'mirrors:\n  "*":\n    endpoint:\n      - {_q(cfg["mirror"])}\n')


def unit_text(cfg: dict) -> str:
    """k3s's systemd unit, as k3s's own installer writes one, but never restarted: a crash fails the chapter."""
    return (f"[Unit]\nDescription=k3s for a terminal book's steps (re-check commands)\n"
            "Wants=network-online.target\nAfter=network-online.target\n\n"
            "[Service]\nType=notify\n"
            f"ExecStart={cfg['bin_dir']}/k3s server --config {cfg['config_dir']}/config.yaml\n"
            "KillMode=process\nDelegate=yes\nLimitNOFILE=1048576\nLimitNPROC=infinity\nLimitCORE=infinity\n"
            f"TasksMax=infinity\nTimeoutStartSec={int(cfg['ready_seconds'])}\nRestart=no\n")


def killall_script(cfg: dict) -> str:
    """k3s stopped and everything it started killed, as k3s's own k3s-killall.sh does: the unit, every container's shim
    and what it runs, the mounts under k3s's and the kubelet's folders, the pods' network namespaces and links, and the
    iptables rules k3s and flannel wrote. The fence's own rules stay."""
    data = cfg["data_dir"]
    return f"""set +e
systemctl stop {cfg['unit']} 2>/dev/null
pids() {{ ps -e -o pid= -o args= | while read -r pid args; do case "$args" in *k3s/data/*/bin/containerd-shim*) echo "$pid" ;; esac; done; }}
tree() {{ for p in "$@"; do echo "$p"; tree $(ps -e -o pid= -o ppid= | while read -r c pp; do [ "$pp" = "$p" ] && echo "$c"; done); done; }}
victims=$(tree $(pids))
[ -z "$victims" ] || kill -9 $victims 2>/dev/null
unmount() {{ while read -r _ path _; do case "$path" in "$1"*) echo "$path" ;; esac; done < /proc/self/mounts | sort -r | while read -r m; do umount -f "$m" && rm -rf "$m"; done; }}
unmount /run/k3s
unmount {data}/
unmount /var/lib/kubelet/pods
unmount /var/lib/kubelet/plugins
unmount /run/netns/cni-
ip netns show 2>/dev/null | grep cni- | while read -r ns _; do ip netns delete "$ns"; done
ip link show 2>/dev/null | grep 'master cni0' | while read -r _ iface _; do iface=${{iface%%@*}}; iface=${{iface%:}}; [ -z "$iface" ] || ip link delete "$iface"; done
for link in cni0 flannel.1 flannel-v6.1 kube-ipvs0 flannel-wg flannel-wg-v6; do ip link delete "$link" 2>/dev/null; done
rm -rf /var/lib/cni/ /var/lib/kubelet/pods /var/lib/kubelet/plugins
for t in iptables ip6tables; do command -v "$t-save" >/dev/null && "$t-save" | grep -v KUBE- | grep -v CNI- | grep -iv flannel | "$t-restore"; done
exit 0
"""


def _mirror(cfg: dict, src: str, dst: str) -> str:
    """dst made a copy of src, leaving [k3s] snapshot_keep alone on both sides."""
    keep = " ".join(f"--exclude={shlex.quote('/' + k.strip('/') + '/')}" for k in cfg["snapshot_keep"])
    return f"rsync -a --delete {keep} {shlex.quote(src.rstrip('/') + '/')} {shlex.quote(dst.rstrip('/') + '/')}"


def wipe_script(cfg: dict) -> str:
    """Nothing left of an earlier cluster on this machine: its data dir, its snapshot and the kubelet's state."""
    paths = " ".join(shlex.quote(p) for p in (cfg["data_dir"], cfg["snapshot_dir"], "/var/lib/kubelet", "/var/lib/cni",
                                               "/etc/rancher/node"))
    return f"set -e\nrm -rf {paths}\n"


def snapshot_script(cfg: dict) -> str:
    """The clean data dir kept, once k3s is Ready and stopped, without the images it has imported, which would be
    imported again at every start."""
    data, snap = cfg["data_dir"], cfg["snapshot_dir"]
    return (f"set -e\ncommand -v rsync >/dev/null || {{ echo 'rsync is needed to keep the clean cluster' >&2; exit 1; }}\n"
            f"find {shlex.quote(data + '/agent/images')} -mindepth 1 -delete 2>/dev/null || true\n"
            f"mkdir -p {shlex.quote(snap)}\n{_mirror(cfg, data, snap)}\n")


def restore_script(cfg: dict) -> str:
    """The clean data dir back in place, k3s stopped: what a chapter starts from."""
    return f"set -e\n{_mirror(cfg, cfg['snapshot_dir'], cfg['data_dir'])}\n"


def user_script(cfg: dict) -> str:
    user = shlex.quote(cfg["steps_user"])
    return f"id -u {user} >/dev/null 2>&1 || useradd --system --no-create-home --shell /bin/bash {user}\n"


def fence_script(cfg: dict, remove: bool = False) -> str:
    """The network fence: the steps' own processes (by their user) and the pods (by their network) reach this machine
    and the cluster's addresses, and nothing else. `remove` takes it down again."""
    chain, user = cfg["fence_chain"], shlex.quote(cfg["steps_user"])
    jumps = {"iptables": [f"OUTPUT -m owner --uid-owner {user} -j {chain}", f"FORWARD -s {cfg['cluster_cidr']} -j {chain}"],
             "ip6tables": [f"OUTPUT -m owner --uid-owner {user} -j {chain}"]}
    allowed = {"iptables": [cfg["cluster_cidr"], cfg["service_cidr"]], "ip6tables": []}
    lines = ["set -e"]
    for ipt in ("iptables", "ip6tables"):
        for jump in jumps[ipt]:
            lines.append(f"while {ipt} -D {jump} 2>/dev/null; do :; done")
        lines.append(f"{ipt} -F {chain} 2>/dev/null || true")
        lines.append(f"{ipt} -X {chain} 2>/dev/null || true")
        if remove:
            continue
        lines += [f"{ipt} -N {chain}", f"{ipt} -A {chain} -o lo -j RETURN"]
        lines += [f"{ipt} -A {chain} -d {cidr} -j RETURN" for cidr in allowed[ipt]]
        lines += [f"{ipt} -A {chain} -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN",
                  f"{ipt} -A {chain} -j REJECT"]
        lines += [f"{ipt} -I {jump.split(' ', 1)[0]} 1 {jump.split(' ', 1)[1]}" for jump in jumps[ipt]]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- the stack's images, by digest


full_ref = stack_pins.full_ref


def _archive_name(n: int, ref: str) -> str:
    return f"{n:03d}-" + re.sub(r"[^a-z0-9.-]+", "-", ref.lower()).strip("-")[:80] + ".tar"


def export_images(pinned: stack_pins.Pinned, out: Path, host: Host | None = None, tool: str | None = None) -> list[dict]:
    """Each image the stack pins, pulled by its digest for linux-amd64 and saved under its tag as an archive of its own in
    `out`, with images.json listing them: what K3sBackend imports. The first of [k3s] images_tools found does it
    (skopeo, then docker). Needs the internet; an image already exported for its digest is kept."""
    host = host or Host()
    cfg = settings()
    tool = tool or next((t for t in cfg["images_tools"] if host.which(t)), None)
    if tool not in cfg["images_tools"]:
        raise commands.CommandsError(f"exporting the stack's images needs one of {', '.join(cfg['images_tools'])}")
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / IMAGES_INDEX
    old = {(e["ref"], e["digest"]): e for e in (json.loads(index_path.read_text()) if index_path.exists() else [])}
    listed = []
    for n, image in enumerate(pinned.images):
        ref, digest = image["ref"], image["digest"]
        registry, repo, _ = stack_pins._registry(ref)
        name, file = full_ref(ref), out / _archive_name(n, ref)
        kept = old.get((ref, digest))
        if kept and file.exists() and file_sha256(file) == kept["sha256"]:
            listed.append(kept)
            continue
        file.unlink(missing_ok=True)
        source = f"{registry}/{repo}@{digest}"
        if tool == "skopeo":
            host.run(["skopeo", "copy", "--quiet", "--override-os", "linux", "--override-arch", "amd64",
                      f"docker://{source}", f"docker-archive:{file}:{name}"], timeout=1800)
        else:
            host.run(["docker", "pull", "--quiet", "--platform", "linux/amd64", source], timeout=1800)
            host.run(["docker", "tag", source, name])
            host.run(["docker", "save", "-o", str(file), name], timeout=1800)
        listed.append({"ref": ref, "digest": digest, "name": name, "file": file.name, "sha256": file_sha256(file)})
    index_path.write_text(json.dumps(listed, indent=1) + "\n")
    for stale in out.iterdir():                         # an image the stack no longer pins
        if stale.name != IMAGES_INDEX and stale.name not in {e["file"] for e in listed}:
            stale.unlink()
    return listed


def image_archives(pinned: stack_pins.Pinned, given: Path) -> list[Path]:
    """The archives that hold the stack's images: one file (such as the Lab's images.tar.zst), or a folder that
    `re-check stack --images` wrote, whose images.json must list every pinned image at its digest."""
    if not pinned.images:
        return []
    if given.is_file() and given.name.endswith(ARCHIVES):
        return [given]
    index = given / IMAGES_INDEX
    if not index.is_file():
        raise commands.CommandsError(f"the stack's images aren't exported to {given}: run re-check stack --book . --images "
                                     "(it needs the internet), or set RE_STACK_IMAGES to their archive")
    listed = {(e["ref"], e["digest"]): e for e in json.loads(index.read_text())}
    missing = [i["ref"] for i in pinned.images if (i["ref"], i["digest"]) not in listed]
    if missing:
        raise commands.CommandsError(f"{given} doesn't hold {', '.join(missing)} at the pinned digest: run re-check stack "
                                     "--book . --images again")
    out = []
    for i in pinned.images:
        e = listed[(i["ref"], i["digest"])]
        path = given / e["file"]
        if not path.is_file() or file_sha256(path) != e["sha256"]:
            raise commands.CommandsError(f"{path} isn't the archive images.json lists: run re-check stack --book . --images "
                                         "again")
        out.append(path)
    return out


# ---------------------------------------------------------------- the backend


class MemorySampler:
    """The highest memory k3s and its pods use while a chapter runs, read from their cgroups every second."""

    def __init__(self, host: Host, paths: list[str], every: float = 1.0):
        self.host, self.paths, self.every = host, paths, every
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def sample(self) -> None:
        total = 0
        for p in self.paths:
            text = self.host.read(p)
            if text and text.strip().isdigit():
                total += int(text.strip())
        self.peak = max(self.peak, total)

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            self.sample()

    def start(self) -> "MemorySampler":
        self.sample()
        self._thread.start()
        return self

    def stop(self) -> int | None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        self.sample()
        return round(self.peak / 2**20) if self.peak else None


class K3sBackend(commands.Backend):
    """Each chapter on a fresh k3s cluster, from the stack's pins (module docstring)."""
    name = "k3s"
    stacks = ("k3s",)

    def __init__(self, book: Book, block_network: bool = True, host: Host | None = None, cfg: dict | None = None,
                 images: Path | None = None, cache: Path | None = None):
        pinned = stack_pins.read_pinned(book.root)
        if pinned is None or "k3s" not in pinned.tools:
            raise commands.CommandsError(f"a k3s stack's steps need k3s pinned in {stack_pins.STACK}: write "
                                         f"{stack_pins.STACK_IN}'s [tools], then run re-check stack --pin")
        problems = [p for p in stack_pins.pinned_problems(pinned, "k3s", stack_pins.read_source(book.root)[1])
                    if "out of date" not in p]
        if problems:
            raise commands.CommandsError("the stack's pins aren't complete:\n" + "\n".join(f"  {p}" for p in problems))
        self.book, self.pinned = book, pinned
        self.cfg = dict(settings(), **(cfg or {}))
        self.host = host or Host()
        self.block_network = block_network
        self.cache = Path(cache) if cache else cache_dir(self.cfg)
        env_images = os.environ.get("RE_STACK_IMAGES")
        self.images = Path(images) if images else Path(env_images) if env_images else images_dir(pinned, self.cfg)
        # Where to read each pinned file instead of its publisher's address, by its SHA-256: a machine with no way out to
        # the internet, such as the Lab's keyless one, is given signed URLs for them (RE_STACK_FILES, JSON)
        self.mirror: dict[str, str] = json.loads(os.environ.get("RE_STACK_FILES") or "{}")
        self.platform = step_format.settings()["stack"]["lab_platform"]
        self.prepared = False
        self.fenced = False
        self.ready: dict[str, float] = {}             # chapter -> seconds from starting k3s to Ready
        self.memory: dict[str, int | None] = {}       # chapter -> peak MiB, k3s and its pods
        self._sampler: MemorySampler | None = None

    # -- files

    def cached(self, url: str, sha256: str) -> Path:
        """A pinned file from the cache, fetched first if it isn't there, and checked by its SHA-256 either way."""
        path = self.cache / "files" / sha256
        if path.is_file() and file_sha256(path) == sha256:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(sha256 + ".part")
        try:
            self.host.fetch(self.mirror.get(sha256, url), part)
        except OSError as e:
            part.unlink(missing_ok=True)
            raise commands.CommandsError(f"couldn't fetch {url}: {e}") from None
        got = file_sha256(part)
        if got != sha256:
            part.unlink(missing_ok=True)
            raise commands.CommandsError(f"{url} isn't the file the stack pins: its SHA-256 is {got}, not {sha256}")
        part.replace(path)
        return path

    def _tool_file(self, name: str) -> Path:
        entry = self.pinned.tools[name]["platforms"][self.platform]
        return self.cached(entry["url"], entry["sha256"])

    def _install_tool(self, name: str) -> None:
        got = self._tool_file(name)
        dest = Path(self.cfg["tools_dir"]) / name
        if not self.pinned.tools[name]["platforms"][self.platform]["url"].endswith(".tar.gz"):
            self.host.install(got, dest, 0o755)
            return
        member = f"{self.platform}/{name}"                   # helm's archive: linux-amd64/helm
        with tarfile.open(got) as tar, tempfile.TemporaryDirectory() as tmp:
            try:
                info = tar.getmember(member)
            except KeyError:
                raise commands.CommandsError(f"{name}'s archive has no {member}") from None
            if not info.isfile():
                raise commands.CommandsError(f"{name}'s archive's {member} isn't a file")
            src = Path(tmp) / name
            with tar.extractfile(info) as f, open(src, "wb") as out:
                shutil.copyfileobj(f, out)
            self.host.install(src, dest, 0o755)

    @property
    def kubectl(self) -> list[str]:
        if "kubectl" in self.pinned.tools:
            return [str(Path(self.cfg["tools_dir"]) / "kubectl")]
        return [f"{self.cfg['bin_dir']}/k3s", "kubectl"]

    # -- once on a machine

    def install(self) -> None:
        """k3s, its airgap images, the stack's tools and images, the fixed flags and the unit, from the pins."""
        cfg, data = self.cfg, Path(self.cfg["data_dir"])
        archives = image_archives(self.pinned, self.images)            # before anything changes: said at once
        self.host.script(killall_script(cfg))
        self.host.script(wipe_script(cfg))
        self.host.install(self._tool_file("k3s"), Path(cfg["bin_dir"]) / "k3s", 0o755)
        airgap = self.pinned.tools["k3s"]["airgap"]
        name = step_format.settings()["stack"]["tools"]["k3s"]["airgap_name"]
        self.host.install(self.cached(airgap["url"], airgap["sha256"]), data / "agent" / "images" / name)
        for tool in ("kubectl", "helm"):
            if tool in self.pinned.tools:
                self._install_tool(tool)
        for n, archive in enumerate(archives):
            suffix = next(s for s in ARCHIVES if archive.name.endswith(s))
            self.host.install(archive, data / "agent" / "images" / f"stack-{n:03d}{suffix}")
        self.host.write(Path(cfg["config_dir"]) / "config.yaml", config_yaml(cfg))
        self.host.write(Path(cfg["config_dir"]) / "registries.yaml", registries_yaml(cfg))
        self.host.write(Path("/etc/systemd/system") / f"{cfg['unit']}.service", unit_text(cfg))
        self.host.run(["systemctl", "daemon-reload"], root=True)
        if self.uses_user:
            self.host.script(user_script(cfg))

    @property
    def uses_user(self) -> bool:
        return bool(self.cfg["as_user"])

    def fence(self) -> None:
        if not self.uses_user:
            raise commands.CommandsError("the network fence holds the steps' own user: [k3s] as_user can't be empty "
                                         "while the network is blocked")
        self.host.script(fence_script(self.cfg))
        self.fenced = True

    def prepare(self) -> None:
        """Install, fence, start k3s once, and keep its clean data dir."""
        self.install()
        if self.block_network:
            try:
                self.fence()
            except commands.CommandsError as e:
                if os.environ.get("RE_COMMANDS_ALLOW_NETWORK") != "1":
                    raise commands.CommandsError(f"the network can't be fenced here: {e}. Set RE_COMMANDS_ALLOW_NETWORK=1 "
                                                 "to run the steps with the network open, for local use only") from None
                self.block_network = False
        self.ready["first start"] = self.start_k3s()
        self.host.script(killall_script(self.cfg))
        self.host.script(snapshot_script(self.cfg))
        self.prepared = True

    # -- a cluster

    def start_k3s(self) -> float:
        """k3s started and Ready: the API, the node, kube-system's deployments and the default service account. The
        seconds it took."""
        t0 = self.host.monotonic()
        timeout = float(self.cfg["ready_seconds"])
        self.host.run(["systemctl", "start", self.cfg["unit"]], root=True, timeout=timeout + 30)
        env = dict(os.environ, KUBECONFIG=self.cfg["kubeconfig"])
        wanted = [["get", "--raw=/readyz"],
                  ["wait", "--for=condition=Ready", f"node/{self.cfg['node_name']}", "--timeout=5s"],
                  *[["-n", "kube-system", "wait", "--for=condition=Available", f"deployment/{d}", "--timeout=5s"]
                    for d in self.cfg["ready_deployments"]],
                  ["-n", "default", "get", "serviceaccount", "default"]]
        last = ""
        for check in wanted:
            while True:
                r = self.host.run([*self.kubectl, *check], env=env, check=False, timeout=30)
                if r.returncode == 0:
                    break
                last = f"kubectl {' '.join(check)}: " + (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()[-400:]
                if self.host.monotonic() - t0 > timeout:
                    journal = self.host.run(["journalctl", "-u", self.cfg["unit"], "-n", "40", "--no-pager"], root=True,
                                            check=False).stdout.decode("utf-8", "replace")
                    raise commands.CommandsError(f"the cluster wasn't Ready within {timeout:g} s; {last}\n"
                                                 f"k3s's last lines:\n{journal[-3000:]}")
                self.host.pause(1)
        return round(self.host.monotonic() - t0, 1)

    def start(self, book: Book, chapter_id: str) -> commands.Workspace:
        if not self.prepared:
            self.prepare()
        self.host.script(killall_script(self.cfg))
        self.host.script(restore_script(self.cfg))
        self.ready[chapter_id] = self.start_k3s()
        root = Path(tempfile.mkdtemp(prefix=f"re-k3s-{chapter_id}-"))
        home, work = root / "home", root / "work"
        (home / ".kube").mkdir(parents=True)
        commands.book_files(book, work)
        (home / ".bash_profile").write_text(commands.PROFILE)          # the Tab's own, written before the home is given away
        kubeconfig = home / ".kube" / "config"
        kubeconfig.write_bytes(self.host.run(["cat", self.cfg["kubeconfig"]], root=True).stdout)
        path = f"{self.cfg['tools_dir']}:{commands.settings()['env']['PATH']}"
        env = {"HOME": str(home), "KUBECONFIG": str(kubeconfig), "PATH": path}
        prefix = [x.format(user=self.cfg["steps_user"]) for x in self.cfg["as_user"]]
        if prefix:
            root.chmod(0o755)
            self.host.run(["chown", "-R", f"{self.cfg['steps_user']}:", str(home), str(work)], root=True)

        def wrap(argv: list[str]) -> list[str]:
            return [*prefix, "env", f"PATH={path}", *argv] if prefix else argv

        paths = [p.format(unit=self.cfg["unit"]) for p in MEMORY]
        self._sampler = MemorySampler(self.host, paths).start()
        return commands.Workspace(root, home, work, env, wrap, extra={"chapter": chapter_id})

    def stop(self, ws: commands.Workspace) -> None:
        chapter = ws.extra.get("chapter", "?")
        if self._sampler is not None:
            self.memory[chapter] = self._sampler.stop()
            self._sampler = None
        if self.uses_user:
            self.host.run(["pkill", "-9", "-u", self.cfg["steps_user"]], root=True, check=False)
            self.host.run(["rm", "-rf", str(ws.root)], root=True, check=False)
        shutil.rmtree(ws.root, ignore_errors=True)
        self.host.script(killall_script(self.cfg))

    def close(self) -> None:
        """k3s stopped and the fence taken down: the machine as it was, but for k3s's files."""
        if self.prepared:
            self.host.script(killall_script(self.cfg), check=False)
        if self.fenced:
            self.host.script(fence_script(self.cfg, remove=True), check=False)
            self.fenced = False

    def describe(self) -> dict:
        out = {"backend": self.name, "k3s": self.pinned.tools["k3s"]["version"], "stack": self.pinned.digest()[:16],
               "network": "blocked" if self.block_network else "open"}
        if self.ready:
            out["ready_seconds"] = dict(self.ready)
        if any(v is not None for v in self.memory.values()):
            out["peak_memory_mib"] = dict(self.memory)
        return out
