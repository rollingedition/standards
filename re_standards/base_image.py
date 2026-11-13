"""The base of every book's runtime image, pinned (data/runtime-base.toml): Docker's python:{version}-slim by digest, and
the Debian packages runtime/Dockerfile adds, by version. examples.ContainerBackend builds with them, and an image's tag
hashes the entry its build used.

    re-check base-image                       the pins, and whether every listed Python has one
    re-check base-image --refresh             each Python's digest from Docker Hub and each package's version from
                                              Debian's index, written back into the data file
    re-check base-image --refresh --python V  the same, adding Python V

Only reads: anonymous GETs of Docker Hub's registry and Debian's package index.
"""
from __future__ import annotations

import hashlib
import json
import lzma
import re
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from . import data_path

DATA = "runtime-base.toml"
REGISTRY = "https://registry-1.docker.io/v2/library/python"
TOKEN = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull"
INDEXES = ("application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json")
MANIFESTS = ("application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json")
DEBIAN = "https://deb.debian.org"
SUITES = ("debian/dists/{release}", "debian/dists/{release}-updates", "debian-security/dists/{release}-security")
AGENT = "rolling-edition-standards"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
PYTHON = re.compile(r"^3\.\d+\.\d+$")


class BaseImageError(RuntimeError):
    """A Python with no pinned base, or a data file that isn't whole."""


def path() -> Path:
    return data_path(DATA)


def load(source: Path | None = None) -> dict:
    return tomllib.loads((source or path()).read_text(encoding="utf-8"))


def entry(python: str, data: dict | None = None) -> dict:
    """What a runtime image for `python` is built from: {image, packages}, the image by digest and each package at its
    version, such as libgomp1=14.2.0-19."""
    data = data if data is not None else load()
    pinned = data.get("python", {}).get(python)
    if not pinned:
        raise BaseImageError(f"Python {python} has no pinned base image in the standards' data/{DATA}: run "
                             f"`re-check base-image --refresh --python {python}` in the standards and commit what it writes")
    versions = data.get("debian", {}).get(pinned["debian"], {})
    missing = [p for p in data["packages"] if p not in versions]
    if missing:
        raise BaseImageError(f"data/{DATA} pins no version of {', '.join(missing)} on Debian {pinned['debian']}: "
                             "run `re-check base-image --refresh`")
    return {"image": f"{data['image'].format(python=python)}@{pinned['digest']}",
            "packages": [f"{p}={versions[p]}" for p in data["packages"]]}


def problems(data: dict | None = None) -> list[str]:
    data = data if data is not None else load()
    out = []
    for python, pinned in sorted(data.get("python", {}).items()):
        if not PYTHON.match(python):
            out.append(f"{python!r} isn't an exact Python version such as 3.12.15")
        if not DIGEST.match(str(pinned.get("digest", ""))):
            out.append(f"Python {python}: its digest isn't sha256:<64 hex digits>")
        try:
            entry(python, data)
        except (BaseImageError, KeyError) as e:
            out.append(str(e))
    return out


# ---------------------------------------------------------------- refreshing


def _get(url: str, headers: dict | None = None) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read(), {k.lower(): v for k, v in r.headers.items()}


def hub_digest(tag: str, get=_get) -> str:
    """The tag's digest on Docker Hub: its multi-platform index, as a build resolves it."""
    token = json.loads(get(TOKEN)[0])["token"]
    body, headers = get(f"{REGISTRY}/manifests/{tag}", {"Authorization": f"Bearer {token}",
                                                        "Accept": ",".join(INDEXES + MANIFESTS)})
    return headers.get("docker-content-digest") or "sha256:" + hashlib.sha256(body).hexdigest()


def hub_debian(tag: str, get=_get) -> str:
    """The Debian release the tag is built on, from the amd64 image's first layer's history (debian.sh ... 'trixie')."""
    token = json.loads(get(TOKEN)[0])["token"]
    auth = {"Authorization": f"Bearer {token}"}
    index = json.loads(get(f"{REGISTRY}/manifests/{tag}", dict(auth, Accept=",".join(INDEXES)))[0])
    amd64 = next(m["digest"] for m in index["manifests"]
                 if m.get("platform", {}).get("os") == "linux" and m.get("platform", {}).get("architecture") == "amd64")
    manifest = json.loads(get(f"{REGISTRY}/manifests/{amd64}", dict(auth, Accept=",".join(MANIFESTS)))[0])
    config = json.loads(get(f"{REGISTRY}/blobs/{manifest['config']['digest']}", auth)[0])
    for step in config.get("history", []):
        found = re.search(r"debian\.sh .*?'([a-z]+)'", step.get("created_by", ""))
        if found:
            return found.group(1)
    raise BaseImageError(f"python:{tag}'s history names no Debian release")


def _order(c: str) -> int:
    """dpkg's order of a character in a version's non-digit part: ~ before the end, letters before everything else."""
    if not c or c.isdigit():
        return 0
    if c.isalpha():
        return ord(c)
    return -1 if c == "~" else ord(c) + 256


def _verrevcmp(a: str, b: str) -> int:
    """dpkg's verrevcmp: one upstream version or revision against another, a non-digit run then a number at a time."""
    def at(s: str, k: int) -> str:
        return s[k] if k < len(s) else ""
    i = j = 0
    while i < len(a) or j < len(b):
        while (at(a, i) and not at(a, i).isdigit()) or (at(b, j) and not at(b, j).isdigit()):
            ac, bc = _order(at(a, i)), _order(at(b, j))
            if ac != bc:
                return -1 if ac < bc else 1
            i, j = i + 1, j + 1
        while at(a, i) == "0":
            i += 1
        while at(b, j) == "0":
            j += 1
        first = 0
        while at(a, i).isdigit() and at(b, j).isdigit():
            first = first or ord(a[i]) - ord(b[j])
            i, j = i + 1, j + 1
        if at(a, i).isdigit():
            return 1
        if at(b, j).isdigit():
            return -1
        if first:
            return -1 if first < 0 else 1
    return 0


def compare_versions(a: str, b: str) -> int:
    """Debian's version order (epoch, upstream version, revision): -1, 0 or 1."""
    def split(v: str) -> tuple[int, str, str]:
        epoch, _, rest = v.partition(":") if ":" in v else ("0", "", v)
        upstream, dash, revision = rest.rpartition("-")
        return int(epoch or 0), (upstream if dash else rest), (revision if dash else "")
    ea, ua, ra = split(a)
    eb, ub, rb = split(b)
    if ea != eb:
        return -1 if ea < eb else 1
    return _verrevcmp(ua, ub) or _verrevcmp(ra, rb)


def debian_versions(release: str, packages: list[str], get=_get) -> dict[str, str]:
    """Each package's newest version on `release`, with its updates and security suites, for amd64: what apt installs."""
    best: dict[str, str] = {}
    for suite in SUITES:
        url = f"{DEBIAN}/{suite.format(release=release)}/main/binary-amd64/Packages.xz"
        try:
            text = lzma.decompress(get(url)[0]).decode("utf-8", errors="replace")
        except OSError:
            continue                                 # a release without an updates suite yet
        for stanza in text.split("\n\n"):
            name = re.search(r"^Package: (\S+)$", stanza, re.M)
            version = re.search(r"^Version: (\S+)$", stanza, re.M)
            if name and version and name.group(1) in packages:
                p, v = name.group(1), version.group(1)
                if p not in best or compare_versions(v, best[p]) > 0:
                    best[p] = v
    missing = [p for p in packages if p not in best]
    if missing:
        raise BaseImageError(f"Debian {release} has no {', '.join(missing)} for amd64")
    return best


def to_toml(data: dict, header: str) -> str:
    out = [header.rstrip("\n"), "", f'image = {json.dumps(data["image"])}',
           f"packages = {json.dumps(data['packages'])}", ""]
    for python in sorted(data["python"], key=lambda v: tuple(int(x) for x in v.split("."))):
        p = data["python"][python]
        out += [f'[python."{python}"]', f'digest = {json.dumps(p["digest"])}', f'debian = {json.dumps(p["debian"])}', ""]
    for release in sorted(data["debian"]):
        out.append(f"[debian.{release}]")
        out += [f"{name} = {json.dumps(v)}" for name, v in sorted(data["debian"][release].items())]
        out.append("")
    return "\n".join(out)


def header(text: str) -> str:
    """The data file's opening comments, kept as they are when it's rewritten."""
    lines = []
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            lines.append(line)
        else:
            break
    return "\n".join(lines)


def refresh(add: list[str] | None = None, source: Path | None = None, get=_get) -> tuple[dict, list[str]]:
    """Every listed Python's digest and Debian release from Docker Hub, `add`'s too, and every package's version on
    those releases from Debian. Returns the new data and what changed, in words; the caller writes it."""
    target = source or path()
    data = load(target)
    pythons = sorted(set(data.get("python", {})) | set(add or []))
    changed, new = [], {"image": data["image"], "packages": list(data["packages"]), "python": {}, "debian": {}}
    for python in pythons:
        if not PYTHON.match(python):
            raise BaseImageError(f"{python!r} isn't an exact Python version such as 3.12.15")
        image = data["image"].format(python=python)
        tag = image.split(":", 1)[1]
        try:
            digest, release = hub_digest(tag, get), hub_debian(tag, get)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise BaseImageError(f"Docker Hub has no {image} image, so Python {python} can't have a runtime image "
                                     "until it does") from None
            raise
        old = data.get("python", {}).get(python, {})
        if old.get("digest") != digest:
            changed.append(f"Python {python}: {old.get('digest', 'not pinned')} -> {digest}")
        new["python"][python] = {"digest": digest, "debian": release}
    for release in sorted({p["debian"] for p in new["python"].values()}):
        versions = debian_versions(release, new["packages"], get)
        for name, v in sorted(versions.items()):
            was = data.get("debian", {}).get(release, {}).get(name)
            if was != v:
                changed.append(f"{name} on Debian {release}: {was or 'not pinned'} -> {v}")
        new["debian"][release] = versions
    return new, changed
