"""The one runner for a terminal book's steps and checks: the pull request's, the release's and the Lab's host's.

Each chapter runs alone, from a fresh start: a backend makes a workspace that holds the book's files (and, for a
stack, its cluster), then the chapter's `setup` brings it to the chapter's starting point, then its steps run in
reading order. A step runs as a reader runs it: in a bash login shell in a terminal (a PTY) of [run] columns and rows,
with NO_COLOR, UTC and C.UTF-8, pasted whole. The shell's prompt marks each command's start and end with OSC 133, so
the runner reads exactly what each printed and how it ended, never the prompt or the echo, and its folder with OSC 7.
A check runs out of band, beside the terminal, never in it, and passes on its expected exit code.

After a step, each `#| wait:` command is polled until it exits 0, within the step's limit: waits, never sleep. Then its
output, cleaned of terminal codes, is compared with examples/{id}.out as its directives say (steps.compare). Its
verdict is one of:

    same        the same output as the book
    different   different from the book
    ran         nothing is compared, and it ended as expected
    error       it stopped with an error: an exit code other than the expected one
    timeout     it ran past its time limit, its waits included
    not-run     an earlier step's failure stopped the chapter

and a check's is `passed` or `not-yet`. A check must also not pass before its section's steps run ([run]
check_before), so it checks something. With `runs` above 1, each chapter runs that many times, each from a fresh
start, and a step whose output differs between runs after its masks fails: what's recorded must print the same every
time. `record` writes the outputs only then.

Backends make the fresh start. `local` runs plain shell steps (a book whose [lab] stack is none) in a scratch folder
on this machine, with the network blocked by `unshare -rn` as the examples' venv is. `compose` brings a compose stack's
services up beside the steps from the workspace's compose.yaml, every image pinned and none pulled. A stack's backend, such as k3s,
gives the same interface: `start` a fresh workspace for a chapter, `stop` it, and the environment and wrapper every
process of the chapter runs with.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from . import data_path, examples, stack, steps as step_format
from .bookfmt import Book

MARKER = re.compile(rb"\x1b\]133;([ABCD])(?:;([^\x07\x1b]*))?(?:\x07|\x1b\\)|\x1b\]7;([^\x07\x1b]*)(?:\x07|\x1b\\)")
PASTE = (b"\x1b[200~", b"\x1b[201~")
OK = ("same", "ran", "passed")
# The shell's profile: no history, no hints for missing commands, no aliases or prompt hooks the system's profile set, a
# paste taken whole, and the markers (OSC 133 for a prompt, a command's start and its end with its exit code; OSC 7 for
# the folder). PS0 carries the exit code of the command before, so a paste of several commands reports each one's. A
# background job's notices ([1]+ Done) come after a command's end marker, so they're never in its output.
PROFILE = r"""# Written by the runner: the prompt marks each command's start and end, and the folder it's in.
unset HISTFILE PROMPT_COMMAND PS0
set +o history
unset -f command_not_found_handle 2>/dev/null
unalias -a
bind 'set enable-bracketed-paste on' 2>/dev/null
bind 'set enable-active-region off' 2>/dev/null
__re_prompt() { local s=$?; printf '\033]133;D;%s\007\033]7;file://%s\007\033]133;A\007' "$s" "$PWD"; return $s; }
PROMPT_COMMAND=__re_prompt
PS0='\033]133;C;prev=$?\007'
PS1='\[\033]133;B\007\]$ '
PS2=''
"""


class CommandsError(RuntimeError):
    """The steps can't run here: no backend for the book's stack, or the network can't be blocked."""


def settings() -> dict:
    return step_format.settings()["run"]


# ---------------------------------------------------------------- terminal output as text


ESCAPES = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[()][0-9A-Za-z]|\x1b[@-Z\\-_=>]")


def screen_text(raw: bytes) -> str:
    """What a terminal shows of `raw`, as plain text: escape codes gone, a carriage return writing over its line and a
    backspace stepping back, as a terminal does, then steps.normalize's newlines and trailing spaces."""
    text = ESCAPES.sub("", raw.decode("utf-8", "replace")).replace("\r\n", "\n")
    lines = []
    for line in text.split("\n"):
        cells: list[str] = []
        col = 0
        for ch in line:
            if ch == "\r":
                col = 0
            elif ch == "\b":
                col = max(0, col - 1)
            elif ch == "\t" or ch >= " ":
                if col < len(cells):
                    cells[col] = ch
                else:
                    cells.append(ch)
                col += 1
        lines.append("".join(cells))
    return step_format.normalize("\n".join(lines))


# ---------------------------------------------------------------- backends


@dataclass
class Workspace:
    """A fresh start for one chapter's run: where the shell starts, its home, and what every process sees."""
    root: Path
    home: Path
    cwd: Path
    env: dict[str, str]
    wrap: Callable[[list[str]], list[str]] = lambda argv: argv
    extra: dict = field(default_factory=dict)          # what the backend keeps for stop


class Backend:
    name = "base"
    stacks: tuple[str, ...] = ()

    def start(self, book: Book, chapter_id: str) -> Workspace:
        raise NotImplementedError

    def stop(self, ws: Workspace) -> None:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"backend": self.name}

    def close(self) -> None:
        """Once every chapter has run: anything the backend set up on the machine for them, taken down."""


def book_files(book: Book, into: Path) -> None:
    """The book's examples/ folder as a reader's workspace holds it: its files and data, without the steps' own files
    and their recorded outputs, which are the book's, not the reader's."""
    src = book.root / "examples"
    if src.is_dir():
        shutil.copytree(src, into, ignore=lambda folder, names: [
            n for n in names if (Path(folder) == src and n.endswith(".sh")) or n.endswith(".out")])
    else:
        into.mkdir(parents=True)


class LocalBackend(Backend):
    """Plain shell steps on this machine: each chapter in a new scratch folder, removed after it, with the network
    blocked by `unshare -rn` for every process it starts, as the examples' venv backend blocks it."""
    name = "local"
    stacks = ("none",)

    def __init__(self, block_network: bool = True):
        allow = os.environ.get("RE_COMMANDS_ALLOW_NETWORK") == "1"
        self.block_network = block_network and not (allow and not examples.can_block_network())
        if self.block_network and not examples.can_block_network():
            raise CommandsError("the network can't be blocked here: `unshare -rn` isn't allowed. Set "
                                "RE_COMMANDS_ALLOW_NETWORK=1 to run the steps with the network open, for local use only")

    def start(self, book: Book, chapter_id: str) -> Workspace:
        root = Path(tempfile.mkdtemp(prefix=f"re-commands-{chapter_id}-"))
        home, work = root / "home", root / "work"
        home.mkdir()
        book_files(book, work)
        wrap = (lambda argv: ["unshare", "-rn", *argv]) if self.block_network else (lambda argv: argv)
        return Workspace(root, home, work, {"HOME": str(home)}, wrap)

    def stop(self, ws: Workspace) -> None:
        shutil.rmtree(ws.root, ignore_errors=True)

    def describe(self) -> dict:
        return {"backend": self.name, "network": "blocked" if self.block_network else "open"}


class ComposeBackend(Backend):
    """A compose stack's services beside the steps (TL13): each chapter in a new scratch folder with the book's files,
    its services brought up from the workspace's compose.yaml, every image the stack pins and none pulled from a
    registry (`--pull never`), and taken down with their volumes after it. The steps run on this machine, with the
    services on loopback; Docker (or a compose-compatible engine) runs them. The Lab's VM and CI's run it the same way
    (services/labs/terminal/vmstack.py)."""
    name = "compose"
    stacks = ("compose",)

    def __init__(self, docker: str = "docker", run=subprocess.run, wait_seconds: int = 300):
        self.docker, self.run, self.wait_seconds = docker, run, wait_seconds
        if not shutil.which(docker) and run is subprocess.run:
            raise CommandsError(f"a compose stack's services run in Docker: install it, so `{docker} compose` runs")

    def compose(self, ws: "Workspace", *args: str, seconds: float = 120) -> subprocess.CompletedProcess:
        return self.run([self.docker, "compose", "--project-name", ws.extra["project"], "--file",
                         str(ws.cwd / "compose.yaml"), *args], cwd=ws.cwd, capture_output=True, text=True,
                        timeout=seconds)

    def start(self, book: Book, chapter_id: str) -> Workspace:
        root = Path(tempfile.mkdtemp(prefix=f"re-commands-{chapter_id}-"))
        home, work = root / "home", root / "work"
        home.mkdir()
        book_files(book, work)
        ws = Workspace(root, home, work, {"HOME": str(home)}, extra={"project": f"re-{book.slug}-{chapter_id}"[:60]})
        got = self.compose(ws, "up", "--detach", "--wait", "--pull", "never",
                           f"--wait-timeout={self.wait_seconds}", seconds=self.wait_seconds + 30)
        if got.returncode:
            self.stop(ws)
            raise CommandsError(f"the chapter's services didn't come up: {(got.stderr or got.stdout).strip()[-600:]}")
        return ws

    def stop(self, ws: Workspace) -> None:
        try:
            self.compose(ws, "down", "--volumes", "--remove-orphans", "--timeout", "10", seconds=120)
        except (subprocess.TimeoutExpired, OSError):
            pass
        shutil.rmtree(ws.root, ignore_errors=True)

    def describe(self) -> dict:
        return {"backend": self.name}


def _k3s(book: Book, block_network: bool) -> Backend:
    from .k3s import K3sBackend                      # imported here: k3s.py builds on this module
    return K3sBackend(book, block_network=block_network)


# Each backend by name, with the stacks it runs: `local` plain shell steps (a stack of none), `k3s` a cluster from the
# stack's pins (k3s.py), `compose` a compose stack's services in Docker (ComposeBackend).
BACKENDS: dict[str, tuple[tuple[str, ...], Callable[[Book, bool], Backend]]] = {
    "local": (LocalBackend.stacks, lambda book, block: LocalBackend(block_network=block)),
    "k3s": (("k3s",), _k3s),
    "compose": (ComposeBackend.stacks, lambda book, block: ComposeBackend(
        wait_seconds=int(stack.settings()["stack"].get("compose_wait_seconds", 300)))),
}


def backend_for(book: Book, name: str | None = None, block_network: bool = True) -> Backend:
    """The backend for a book's stack, or the one named, which must run that stack."""
    wanted = stack.lab(book.manifest)["stack"]
    name = name or next((n for n, (stacks, _) in BACKENDS.items() if wanted in stacks), wanted)
    if name not in BACKENDS:
        raise CommandsError(f"this book's stack is {wanted}, so its steps need the {name} backend, which isn't built yet: "
                            f"the backends are {', '.join(f'{n} (a stack of {s[0]})' for n, (s, _) in BACKENDS.items())}")
    stacks, make = BACKENDS[name]
    if wanted not in stacks:
        raise CommandsError(f"the {name} backend runs a stack of {', '.join(stacks)}; this book's stack is {wanted}, so its "
                            f"steps need the {next((n for n, (s, _) in BACKENDS.items() if wanted in s), wanted)} backend")
    return make(book, block_network)


# ---------------------------------------------------------------- a terminal tab


class TabError(RuntimeError):
    pass


class Tab:
    """One terminal tab: a login shell in a PTY, read through its markers."""

    def __init__(self, ws: Workspace, name: str, cfg: dict | None = None):
        self.cfg, self.name, self.ws = cfg or settings(), name, ws
        profile = ws.home / ".bash_profile"
        if not profile.exists():
            profile.write_text(PROFILE)
        self.master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", int(self.cfg["rows"]), int(self.cfg["columns"]), 0, 0))
        env = {**self.cfg["env"], "TERM": self.cfg["term"], **ws.env}
        try:
            self.proc = subprocess.Popen(ws.wrap(list(self.cfg["shell"])), stdin=slave, stdout=slave, stderr=slave,
                                         cwd=ws.cwd, env=env, start_new_session=True, close_fds=True,
                                         preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
        finally:
            os.close(slave)
        os.set_blocking(self.master, False)
        self.buf = b""
        self.cwd = ws.cwd
        self.busy = False                            # a background step is running in it
        self.alive = True
        try:
            ready = self._until(lambda: self._marker(b"B"), time.monotonic() + float(self.cfg["start_seconds"]))
        except TabError:
            ready = False
        if not ready:
            seen = screen_text(self.buf)[-500:]
            self.close()
            raise TabError(f"the shell showed no prompt within {self.cfg['start_seconds']} s" +
                           (f"; it printed:\n{seen}" if seen.strip() else ""))
        self.buf = b""

    # -- reading

    def _read(self, until: float) -> bool:
        """Read what's there, waiting until `until` at most: False once the shell has gone."""
        wait = max(0.0, until - time.monotonic())
        ready, _, _ = select.select([self.master], [], [], wait)
        if not ready:
            return True
        try:
            data = os.read(self.master, 65536)
        except (BlockingIOError, InterruptedError):
            return True
        except OSError:
            data = b""
        if not data:
            self.alive = False
            return False
        self.buf += data
        return True

    def _until(self, done: Callable[[], bool], until: float) -> bool:
        while not done():
            if time.monotonic() >= until:
                return False
            if not self._read(until) and not done():
                raise TabError("the shell ended")
        return True

    def _marker(self, kind: bytes) -> bool:
        return any(m.group(1) == kind for m in MARKER.finditer(self.buf))

    def _write(self, data: bytes, until: float) -> None:
        """Write all of `data`, reading the shell's echo as it comes, so neither side fills the terminal and waits."""
        while data:
            if time.monotonic() >= until:
                raise TabError("the shell stopped reading")
            _, writable, _ = select.select([], [self.master], [], 0.05)
            if writable:
                try:
                    n = os.write(self.master, data[:4096])
                    data = data[n:]
                except BlockingIOError:
                    pass
            self._read(time.monotonic() + 0.01)

    # -- running

    def paste(self, command: str, until: float) -> None:
        self.buf = b""
        self._write(PASTE[0] + command.rstrip("\n").encode() + PASTE[1] + b"\r", until)

    def finish(self, until: float, limit: int) -> tuple[list[int], bytes, bool]:
        """After a paste: (each command's exit code, what they printed, whether it ended in time). Reads to the end
        marker, then to the next prompt."""
        self._until(lambda: self._marker(b"D") or len(self.buf) > limit * 2, until)
        ended = self._marker(b"D")                       # not a flood past the limit, which is cut short
        if ended:
            self._until(lambda: self._prompt_after_end(), until)
        statuses, out, started = [], b"", False
        pos = 0
        for m in MARKER.finditer(self.buf):
            if started:
                out += self.buf[pos:m.start()]
            kind, arg = m.group(1), (m.group(2) or b"").decode()
            if kind == b"C":
                if started and arg.startswith("prev="):
                    statuses.append(int(arg[5:] or 0))
                started = True
            elif kind == b"D":
                statuses.append(int(arg or 0))
                break
            elif m.group(3) is not None:
                self.cwd = Path(urllib.parse.unquote(urllib.parse.urlparse(m.group(3).decode()).path))
            pos = m.end()
        else:
            if started:                                  # no end yet: what it printed so far
                out += self.buf[pos:]
        for m in MARKER.finditer(self.buf):             # the folder, from the prompt after the end
            if m.group(3) is not None:
                self.cwd = Path(urllib.parse.unquote(urllib.parse.urlparse(m.group(3).decode()).path))
        if not started and ended:
            statuses = statuses or [0]
        return statuses, out[:limit], ended and len(out) <= limit

    def _prompt_after_end(self) -> bool:
        seen_end = False
        for m in MARKER.finditer(self.buf):
            if m.group(1) == b"D":
                seen_end = True
            elif seen_end and m.group(1) == b"B":
                return True
        return False

    def started(self, until: float) -> bool:
        return self._until(lambda: self._marker(b"C"), until)

    def interrupt(self, seconds: float) -> bool:
        """Ctrl+C, as a reader presses it: True when the shell is back at its prompt within `seconds`."""
        try:
            os.write(self.master, b"\x03")
        except OSError:
            return False
        try:
            return self._until(lambda: self._prompt_after_end(), time.monotonic() + seconds)
        except TabError:
            return False

    def close(self) -> None:
        """The tab and everything started in it: hang up, as closing a terminal does, then kill what's left."""
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        kill_session(self.proc.pid)
        try:
            os.close(self.master)
        except OSError:
            pass
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.alive = False


def kill_session(sid: int) -> None:
    """Kill every process left in a tab's session, such as a job its shell started in its own process group."""
    proc = Path("/proc")
    if not proc.is_dir():
        return
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[3]) == sid:
                os.kill(int(entry.name), signal.SIGKILL)
        except (OSError, IndexError, ValueError):
            continue


# ---------------------------------------------------------------- out of band: checks and waits


def out_of_band(ws: Workspace, cwd: Path, command: str, seconds: float, cfg: dict | None = None) -> tuple[int | None, str]:
    """A command beside the terminal, never in it, in the chapter's environment and the main tab's folder: (its exit
    code, or None past `seconds`, and its output)."""
    cfg = cfg or settings()
    env = {**cfg["env"], "TERM": "dumb", **ws.env}
    p = subprocess.Popen(ws.wrap(["bash", "--noprofile", "--norc", "-c", command]), cwd=cwd if cwd.is_dir() else ws.cwd,
                         env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=max(0.1, seconds))
    except subprocess.TimeoutExpired:
        kill_session(p.pid)                          # the command and anything it started, which may hold its output
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
        return None, screen_text(out or b"")
    return p.returncode, screen_text(out)


def poll(ws: Workspace, cwd: Path, command: str, until: float, cfg: dict | None = None) -> bool:
    """`#| wait:`: the command, again every [run] poll_seconds, until it exits 0 or `until` passes."""
    cfg = cfg or settings()
    while True:
        left = until - time.monotonic()
        if left <= 0:
            return False
        code, _ = out_of_band(ws, cwd, command, left, cfg)
        if code == 0:
            return True
        pause = min(float(cfg["poll_seconds"]), until - time.monotonic())
        if pause > 0:
            select.select([], [], [], pause)


# ---------------------------------------------------------------- a chapter's run


@dataclass
class StepResult:
    step_id: str
    kind: str                       # step or check
    verdict: str
    exit_codes: list[int] = field(default_factory=list)
    output: str = ""
    expected: str | None = None
    diff: str = ""
    seconds: float = 0.0
    phase: str = "chapter"          # setup, chapter, or before: a check's run before its section's steps
    why: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict in OK


@dataclass
class ChapterRun:
    chapter_id: str
    results: list[StepResult]
    problems: list[str]                 # what fails the chapter, whatever is recorded
    seconds: float
    backend: dict = field(default_factory=dict)
    differences: list[str] = field(default_factory=list)   # outputs other than the recorded ones, which --record writes

    def as_json(self) -> dict:
        return {"chapter": self.chapter_id, "seconds": round(self.seconds, 3),
                "problems": self.problems + self.differences, "results": [asdict(r) for r in self.results]}


class ChapterRunner:
    """One run of one chapter, from a fresh start."""

    def __init__(self, book: Book, chapter_id: str, backend: Backend, check_before: bool | None = None,
                 cfg: dict | None = None):
        self.book, self.chapter = book, book.chapter(chapter_id)
        self.backend, self.cfg = backend, cfg or settings()
        self.check_before = bool(self.cfg["check_before"]) if check_before is None else check_before
        self.tabs: dict[str, Tab] = {}
        self.ws: Workspace | None = None

    def tab(self, name: str) -> Tab:
        if name not in self.tabs or not self.tabs[name].alive:
            self.tabs[name] = Tab(self.ws, name, self.cfg)
        return self.tabs[name]

    @property
    def cwd(self) -> Path:
        main = self.tabs.get(step_format.settings()["defaults"]["tab"])
        return main.cwd if main else self.ws.cwd

    def run(self) -> ChapterRun:
        t0 = time.monotonic()
        results: list[StepResult] = []
        problems: list[str] = []
        differences: list[str] = []
        self.ws = self.backend.start(self.book, self.chapter.chapter_id)
        try:
            self.tab(step_format.settings()["defaults"]["tab"])
            stopped = None
            for sid in self.chapter.setup:
                r = self.step(self.book.steps[sid], phase="setup")
                results.append(r)
                if not r.ok:
                    problems.append(f"setup step {sid} ended {r.verdict}, so the chapter couldn't start"
                                    + (f": {r.why}" if r.why else ""))
                    stopped = sid
                    break
            probed: set[str | None] = set()
            for e in self.chapter.step_embeds:
                if e.kind == "file":
                    continue
                part = self.book.steps[e.example_id]
                if stopped:
                    results.append(StepResult(part.step_id, part.kind, "not-run", why=f"{stopped} stopped the chapter"))
                    continue
                if self.check_before and e.section_id not in probed:
                    probed.add(e.section_id)
                    for c in self.chapter.step_embeds:
                        if c.kind == "check" and c.section_id == e.section_id:
                            before = self.check(self.book.steps[c.example_id], phase="before")
                            results.append(before)
                            if before.ok:
                                problems.append(f"check {c.example_id} passes before its section's steps run, so it "
                                                "checks nothing they do")
                r = self.check(part) if part.kind == "check" else self.step(part)
                results.append(r)
                if r.verdict == "different" or (r.verdict == "not-yet" and r.diff):
                    differences.append(self.describe(r))
                elif not r.ok:
                    problems.append(self.describe(r))
                if r.verdict in ("timeout", "error") and part.kind == "step":
                    stopped = part.step_id
        finally:
            self.close()
        return ChapterRun(self.chapter.chapter_id, results, problems, time.monotonic() - t0, self.backend.describe(),
                          differences)

    def describe(self, r: StepResult) -> str:
        what = {"different": "prints something other than its recorded output",
                "error": "stopped with an error", "timeout": "ran past its time limit",
                "not-yet": "doesn't pass after its section's steps"}.get(r.verdict, r.verdict)
        detail = r.diff or r.why or (r.output[-2000:] if r.verdict == "error" else "")
        return f"{r.kind} {r.step_id} {what}" + ("".join(f"\n      {x}" for x in detail.splitlines()) if detail else "")

    def step(self, s: step_format.Step, phase: str = "chapter") -> StepResult:
        d = s.directives
        t0 = time.monotonic()
        until = t0 + d.timeout
        limit = int(self.cfg["output_max_bytes"])
        res = StepResult(s.step_id, "step", "ran", expected=s.expected, phase=phase)
        try:
            tab = self.tab(d.tab)
            if tab.busy:
                res.verdict, res.why = "error", f"tab {d.tab} is busy with a step that runs in the background"
                return res
            tab.paste(s.command, until)
            if d.background:
                if not tab.started(until):
                    res.verdict, res.why = "timeout", "it didn't start within its limit"
                    return res
                tab.busy = True
            else:
                codes, raw, in_time = tab.finish(until, limit)
                res.exit_codes, res.output = codes, screen_text(raw)
                if not in_time:
                    too_much = len(raw) >= limit
                    back = tab.interrupt(float(self.cfg["interrupt_seconds"]))
                    if not back:
                        tab.close()
                    res.verdict = "error" if too_much else "timeout"
                    res.why = f"its output passed {limit:,} bytes" if too_much else f"it ran past {d.timeout:g} s"
                    return res
                if not codes or any(c != 0 for c in codes[:-1]) or codes[-1] != d.expect_exit:
                    res.verdict = "error"
                    res.why = f"exit codes {', '.join(map(str, codes))}; expected {d.expect_exit} at the end" \
                        if len(codes) > 1 else f"exit code {codes[0] if codes else '?'}; expected {d.expect_exit}"
                    return res
            for w in d.wait:
                if not poll(self.ws, self.cwd, w, until, self.cfg):
                    res.verdict, res.why = "timeout", f"waited for `{w}` past {d.timeout:g} s"
                    return res
            if not d.background and d.compare != "none" and phase != "setup":     # compared in its own chapter
                same, res.diff = step_format.compare(s.expected, res.output, d.compare, d.mask)
                res.verdict = "same" if same else "different"
            return res
        except TabError as e:
            res.verdict, res.why = "error", str(e)
            return res
        finally:
            res.seconds = time.monotonic() - t0

    def check(self, s: step_format.Step, phase: str = "chapter") -> StepResult:
        d = s.directives
        t0 = time.monotonic()
        code, output = out_of_band(self.ws, self.cwd, s.command, d.timeout, self.cfg)
        res = StepResult(s.step_id, "check", "passed", [] if code is None else [code], output, s.expected, phase=phase,
                         seconds=time.monotonic() - t0)
        if code is None:
            res.verdict, res.why = "not-yet", f"it ran past {d.timeout:g} s"
        elif code != d.expect_exit:
            res.verdict, res.why = "not-yet", d.hint
        elif d.compare != "none":
            same, res.diff = step_format.compare(s.expected, output, d.compare, d.mask)
            res.verdict = "passed" if same else "not-yet"
        return res

    def close(self) -> None:
        for tab in self.tabs.values():
            if tab.alive and tab.busy:
                tab.interrupt(float(self.cfg["interrupt_seconds"]))
            tab.close()
        self.tabs = {}
        if self.ws is not None:
            self.backend.stop(self.ws)


def run_chapter(book: Book, chapter_id: str, backend: Backend, check_before: bool | None = None) -> ChapterRun:
    return ChapterRunner(book, chapter_id, backend, check_before).run()


# ---------------------------------------------------------------- a book's run, its determinism and its recording


def between_runs(first: ChapterRun, other: ChapterRun, book: Book) -> list[str]:
    """What printed differently in two runs of a chapter, after each step's masks."""
    problems = []
    theirs = {(r.step_id, r.phase): r for r in other.results}
    for r in first.results:
        o = theirs.get((r.step_id, r.phase))
        if o is None or r.phase == "before":
            continue
        part = book.steps[r.step_id]
        masks = part.directives.mask
        if r.verdict != o.verdict:
            problems.append(f"{r.kind} {r.step_id} ended {r.verdict} in one run and {o.verdict} in another")
        elif part.directives.compare != "none" and step_format.mask(r.output, masks) != step_format.mask(o.output, masks):
            _, diff = step_format.compare(r.output, o.output, "exact", masks)
            problems.append(f"{r.kind} {r.step_id} prints differently from run to run, after its masks: mask what "
                            "changes, or make it print the same\n" + "\n".join(f"      {x}" for x in diff.splitlines()))
    return problems


def run_book(book: Book, backend: Backend, chapters: list[str] | None = None, runs: int = 1,
             check_before: bool | None = None) -> tuple[list[ChapterRun], list[str], list[str]]:
    """Each chapter with a step, or those named, `runs` times from a fresh start: (the first run of each, problems,
    and the outputs other than their recorded ones)."""
    wanted = [c.chapter_id for c in book.chapters if c.step_embeds and (not chapters or c.chapter_id in chapters)]
    if chapters and (unknown := sorted(set(chapters) - {c.chapter_id for c in book.chapters})):
        raise CommandsError(f"there's no chapter {', '.join(map(repr, unknown))} in this book")
    out, problems, differences = [], [], []
    for cid in wanted:
        first = run_chapter(book, cid, backend, check_before)
        problems += [f"{cid}: {p}" for p in first.problems]
        differences += [f"{cid}: {p}" for p in first.differences]
        for _ in range(1, runs):
            problems += [f"{cid}: {p}" for p in between_runs(first, run_chapter(book, cid, backend, check_before), book)]
        out.append(first)
    return out, problems, differences


def recordable(book: Book, runs: list[ChapterRun]) -> dict[str, str]:
    """The outputs to record: each step or check that's compared and ended as expected, by ID, from its chapter's own
    run, never from a setup run."""
    out = {}
    for run in runs:
        for r in run.results:
            part = book.steps[r.step_id]
            if r.phase != "chapter" or part.directives.compare == "none":
                continue
            ended_well = r.verdict in ("same", "different") if r.kind == "step" else \
                bool(r.exit_codes) and r.exit_codes[-1] == part.directives.expect_exit
            if ended_well:
                out[r.step_id] = step_format.normalize(r.output)
    return out


def output_problems(book: Book) -> list[str]:
    """Each step or check that's compared and has no recorded output yet."""
    return [f"{s.file}: no recorded output; record it with re-check commands --record"
            for s in book.steps.values() if s.directives.compare != "none" and s.expected is None]


def results_json(runs: list[ChapterRun], outcome: str, backend: dict, book: Book | None = None,
                 at: str | None = None, selection: Selection | None = None, recorded: bool = False) -> dict:
    """A run's report: its outcome, each chapter's results, and, given the book, its record (record()), which a later
    run's selection compares with (`re-check commands --affected --recorded REPORT`)."""
    ran = [r for run in runs for r in run.results if r.phase == "chapter"]
    out = {"outcome": outcome, "backend": backend, "passing": sum(r.ok for r in ran), "total": len(ran),
           "chapters": [run.as_json() for run in runs]}
    if selection is not None:
        out["selection"] = {"everything": selection.everything, "why": selection.why, "chapters": selection.chapters,
                            "floor": selection.floor, "total": selection.total}
    if book is not None:
        out["record"] = record(book, runs, at, recorded)
    return out


def write_json(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- which chapters run: the record and the selection


RUNNER_FILES = ("commands.py", "steps.py", "k3s.py")


def runner_key() -> str:
    """A hash of the code that runs the steps and the settings every run starts with: a record that keeps it says which
    ran, so a later selection can tell when it changed."""
    h = hashlib.sha256()
    for path in [Path(__file__).with_name(n) for n in RUNNER_FILES] + [data_path("commands.toml")]:
        h.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def stack_digest(book: Book) -> str:
    """The stack's pins' digest (stack.Pinned.digest), or "" for a book with none."""
    try:
        pinned = stack.read_pinned(book.root)
    except (stack.StackError, OSError):
        return "unreadable"
    return pinned.digest() if pinned else ""


def record(book: Book, runs: list[ChapterRun] | None = None, at: str | None = None, recorded: bool = False) -> dict:
    """What a selection compares with: the stack's digest, the runner's key, and each chapter's inputs_sha256 (steps.py),
    with, for a chapter that ran here, whether it passed and when. `recorded`: the run wrote its outputs, so an output
    other than the one recorded before is the new one, not a failure."""
    views = step_format.steps_json(book)
    ran = {r.chapter_id: r for r in runs or []}
    chapters = {}
    for cid, view in views.items():
        entry = {"inputs_sha256": view["inputs_sha256"]}
        if cid in ran:
            entry["passed"] = not ran[cid].problems and (recorded or not ran[cid].differences)
            if at:
                entry["verified_at"] = at
        chapters[cid] = entry
    return {"stack_digest": stack_digest(book), "runner": runner_key(), "chapters": chapters}


@dataclass
class Selection:
    """The chapters a run takes, each with why, or every chapter, with why."""
    chapters: dict[str, list[str]]
    everything: bool
    total: int
    why: str = ""
    floor: list[str] = field(default_factory=list)     # chapters that run only because their last run is too old

    @property
    def ids(self) -> list[str]:
        return list(self.chapters)


def _parse_time(text: str):
    from datetime import datetime
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def select_chapters(book: Book, previous: dict | None, changed: list[str] | None = None, now=None,
           floor_days: float | None = None) -> Selection:
    """The chapters a change could affect, against `previous`: the base's record (record() of the pull request's base)
    or the last run's (a report's `record`, or an edition's).

    Every chapter runs when there's nothing to compare with, when the code that runs the steps changed, when the stack's
    pins changed, or when a file under examples/ changed that's neither a step's own nor a file a chapter embeds, since
    any step may read it. Otherwise a chapter runs when its steps, checks, setup or embedded files changed
    (inputs_sha256), when one of its steps' recorded outputs changed, when it's new, when its last run didn't pass, or,
    with `floor_days` and `now`, when its last passing run is older than that: the freshness floor."""
    views = step_format.steps_json(book)
    total = len(views)

    def everything(why: str) -> Selection:
        return Selection({cid: [why] for cid in views}, True, total, why)

    if previous is None:
        return everything("there's no earlier run to compare with")
    if previous.get("runner") and previous["runner"] != runner_key():
        return everything("the code that runs the steps changed since the run it's compared with")
    if previous.get("stack_digest", "") != stack_digest(book):
        return everything(f"the stack's pins changed ({stack.STACK})")
    embedded = {f.file for f in book.files.values()}
    own = {s.file for s in book.steps.values()} | {f"examples/{sid}.out" for sid in book.steps}
    for path in changed or []:
        if path.startswith("examples/") and path not in own and path not in embedded \
                and path not in (stack.STACK, stack.STACK_IN):
            return everything(f"{path} changed, and any step may read it")
    outs = {f"examples/{sid}.out": s.chapter_id for sid, s in book.steps.items()}
    before = previous.get("chapters") or {}
    chosen: dict[str, list[str]] = {}
    for cid, view in views.items():
        why = []
        last = before.get(cid)
        if last is None:
            why.append("it's new, or had no steps before")
        else:
            if last.get("inputs_sha256") != view["inputs_sha256"]:
                why.append("its steps, checks, setup or files changed")
            if last.get("passed") is False:
                why.append("its last run didn't pass")
        hit = sorted(p for p in changed or [] if outs.get(p) == cid)
        if hit:
            why.append(f"a recorded output changed ({', '.join(hit)})")
        if why:
            chosen[cid] = why
    floor = []
    if floor_days is not None and now is not None:
        from datetime import timedelta
        cutoff = now - timedelta(days=float(floor_days))
        for cid in views:
            at = (before.get(cid) or {}).get("verified_at")
            if cid not in chosen and at and _parse_time(at) < cutoff:
                chosen[cid] = [f"its last passing run, on {str(at)[:10]}, is more than {float(floor_days):g} days old"]
                floor.append(cid)
    return Selection({cid: chosen[cid] for cid in views if cid in chosen}, False, total, floor=floor)
