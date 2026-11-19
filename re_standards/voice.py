"""voice.toml: an authored book's voice, beside book.toml. The lead author's to change; the drafting tools read it for
every task, and `re-check style` holds the book to its overrides.

    [profile]      how the book sounds: a summary, who speaks ("we" or "I"; the reader is always "you"), a few traits,
                   and the samples it was made from
    [glossary]     a term = what it means in this book
    [avoid]        words and phrases this book never uses, beside the writing standards' own
    [overrides]    a change to a rule the standards mark adjustable, within its bounds (data/writing.toml [adjustable])

Only lengths, who speaks and the narrative limits that set the tone can change. Examples that run, versions and
numbers, claims and their evidence, citations and accessibility stay as the standards say for every book, and an
override that names one is refused. Standard library only."""
from __future__ import annotations

import tomllib
from pathlib import Path

FILE = "voice.toml"
TABLES = ("profile", "glossary", "avoid", "overrides")
PROFILE = {"summary": 1200, "person": 8, "traits": 160, "samples": 200, "sentence_words": 0}


class VoiceError(Exception):
    pass


def load(root: Path) -> dict | None:
    """The book's voice.toml, or None when it has none; VoiceError when it doesn't parse."""
    path = Path(root) / FILE
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise VoiceError(f"{FILE} doesn't parse: {e}") from None


def adjustable(cfg: dict) -> dict:
    return cfg.get("adjustable") or {}


def _text(value, limit: int) -> bool:
    return isinstance(value, str) and len(value) <= limit


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def problems(data: dict, cfg: dict) -> list[str]:
    """Everything wrong with a voice.toml, against the standards' writing config: its tables and their shapes, who
    speaks, and each override a rule the standards mark adjustable, within its bounds."""
    out, adj = [], adjustable(cfg)
    if not isinstance(data, dict):
        return [f"{FILE} is a table"]
    for key in sorted(set(data) - set(TABLES)):
        out.append(f"{FILE}: [{key}] isn't one of {', '.join(TABLES)}")
    profile = data.get("profile", {})
    if not isinstance(profile, dict):
        out.append(f"{FILE}: [profile] is a table")
        profile = {}
    for key in sorted(set(profile) - set(PROFILE)):
        out.append(f"{FILE}: [profile] {key} isn't one of {', '.join(PROFILE)}")
    if "summary" in profile and not _text(profile["summary"], PROFILE["summary"]):
        out.append(f"{FILE}: [profile] summary is text, at most {PROFILE['summary']} characters")
    allowed = (adj.get("person") or {}).get("allowed") or ["we"]
    if "person" in profile and profile["person"] not in allowed:
        out.append(f"{FILE}: [profile] person is one of {', '.join(map(repr, allowed))} (W-34); the reader is always \"you\"")
    for key, n in (("traits", 8), ("samples", 20)):
        items = profile.get(key, [])
        if not isinstance(items, list) or len(items) > n or not all(_text(x, PROFILE[key]) for x in items):
            out.append(f"{FILE}: [profile] {key} lists at most {n} texts of at most {PROFILE[key]} characters")
    for sample in profile.get("samples", []) if isinstance(profile.get("samples"), list) else []:
        if isinstance(sample, str) and (not sample.startswith("plan/samples/") or ".." in sample):
            out.append(f"{FILE}: [profile] samples are files under plan/samples/, not {sample!r}")
    if "sentence_words" in profile and not (isinstance(profile["sentence_words"], int) and 5 <= profile["sentence_words"] <= 60):
        out.append(f"{FILE}: [profile] sentence_words is a whole number from 5 to 60")
    glossary = data.get("glossary", {})
    if not isinstance(glossary, dict) or len(glossary) > 200 or \
            not all(_text(k, 80) and _text(v, 400) for k, v in glossary.items()):
        out.append(f"{FILE}: [glossary] holds at most 200 terms, each = what it means, in at most 80 and 400 characters")
    avoid = data.get("avoid", {})
    if not isinstance(avoid, dict) or set(avoid) - {"words", "phrases"}:
        out.append(f"{FILE}: [avoid] holds words and phrases")
    else:
        for key, n in (("words", 60), ("phrases", 120)):
            items = avoid.get(key, [])
            if not isinstance(items, list) or len(items) > 100 or not all(isinstance(x, str) and 0 < len(x) <= n for x in items):
                out.append(f"{FILE}: [avoid] {key} lists at most 100, each at most {n} characters")
    out += override_problems(data.get("overrides", {}), cfg)
    return out


def bounds(cfg: dict) -> dict[str, list]:
    """Every limit an override may set, by name, with the widest it may go: [adjustable.length] and
    [adjustable.narrative]."""
    adj = adjustable(cfg)
    return {**(adj.get("length") or {}), **(adj.get("narrative") or {})}


def override_problems(overrides, cfg: dict) -> list[str]:
    """Each override a limit the standards mark adjustable, inside its bounds: a range as [lo, hi] within them, a single
    limit a number within them. Anything else, a fixed rule among them, is refused by name."""
    if not isinstance(overrides, dict):
        return [f"{FILE}: [overrides] is a table"]
    out, limits, fixed = [], bounds(cfg), adjustable(cfg).get("fixed") or []
    current = {**(cfg.get("length") or {}), **(cfg.get("narrative") or {})}
    for key, value in overrides.items():
        if key not in limits:
            out.append(f"{FILE}: [overrides] {key} isn't a limit the standards let a book change: only "
                       f"{', '.join(sorted(limits))}. Examples that run, versions, claims and their evidence, citations "
                       f"and accessibility ({', '.join(fixed)}) stay as the standards say")
            continue
        lo, hi = limits[key]
        if isinstance(current.get(key), list):
            if not (isinstance(value, list) and len(value) == 2 and all(_number(v) for v in value) and lo <= value[0] <= value[1] <= hi):
                out.append(f"{FILE}: [overrides] {key} is a range [low, high] within [{lo}, {hi}], not {value!r}")
        elif not (_number(value) and lo <= value <= hi):
            out.append(f"{FILE}: [overrides] {key} is a number from {lo} to {hi}, not {value!r}")
    return out


def apply(cfg: dict, data: dict | None) -> dict:
    """The writing config as this book keeps it: each override in place of the standards' limit, and its words to
    avoid added to the banned ones (W-35). A voice with problems changes nothing: `re-check manifest` names them."""
    if not data or problems(data, cfg):
        return cfg
    over = data.get("overrides") or {}
    avoid = data.get("avoid") or {}
    if not over and not avoid.get("words") and not avoid.get("phrases"):
        return cfg                                              # nothing to change: the standards as they are
    length = {k: over.get(k, v) for k, v in (cfg.get("length") or {}).items()}
    narrative = {k: over.get(k, v) for k, v in (cfg.get("narrative") or {}).items()}
    words = dict(cfg.get("words") or {})
    extra = [w for w in list(avoid.get("words") or []) + list(avoid.get("phrases") or []) if w not in words.get("banned", [])]
    if extra:
        words["banned"] = list(words.get("banned", [])) + extra
    return dict(cfg, length=length, narrative=narrative, words=words)


def profile_toml(profile: dict, before: str) -> str:
    """voice.toml with [profile] replaced and every other table kept as the author wrote it: what `/re voice` proposes.
    Text goes in as TOML basic strings, escaped, so nothing in it can end the string or start a table."""
    import json
    esc = lambda s: json.dumps(str(s), ensure_ascii=False)          # noqa: E731: JSON's escaping is TOML's
    lines = ["[profile]", f"summary = {esc(profile.get('summary', ''))}", f"person = {esc(profile.get('person', 'we'))}",
             "traits = [" + ", ".join(esc(t) for t in profile.get("traits") or []) + "]",
             "samples = [" + ", ".join(esc(s) for s in profile.get("samples") or []) + "]"]
    if isinstance(profile.get("sentence_words"), int):
        lines.append(f"sentence_words = {profile['sentence_words']}")
    out, skipping, placed = [], False, False
    for line in before.splitlines():
        header = line.strip().startswith("[") and line.strip().split("#", 1)[0].strip().endswith("]")
        if header:
            skipping = line.strip().split("#", 1)[0].strip() == "[profile]"
            if skipping and not placed:
                out += lines + [""]
                placed = True
                continue
        if not skipping:
            out.append(line)
    if not placed:
        out = lines + [""] + out
    text = "\n".join(out).rstrip("\n") + "\n"
    tomllib.loads(text)                                             # it parses, or this raises before anything is written
    return text
