"""Punched-tape encodings: the title tape, the edition code and its fingerprint, and the history tape.

The executable form of the cover-generation, edition-code and history-tape specs. Anyone can use it to
decode a tape or recompute an edition code. Standard library only.

    python -m re_standards.tape code SLUG EDITION COMMIT_SHA
    python -m re_standards.tape encode "Some Title"
"""
from __future__ import annotations

import hashlib
import sys
import unicodedata

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # 32 symbols, without I, L, O and U
MARKER = 31                                       # the fingerprint's marker column: all five holes
MAX_COLS = 27                                     # data columns per strip, word gaps included

# ---------------------------------------------------------------- title tape


def normalize_title(title: str) -> list[str]:
    """NFKD, drop combining marks, lowercase; every character outside a-z becomes a word break."""
    decomposed = unicodedata.normalize("NFKD", title)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return "".join(ch if "a" <= ch <= "z" else " " for ch in plain).split()


def letter_value(ch: str) -> int:
    """a = 1 ... z = 26, so no letter is a blank column."""
    return ord(ch) - ord("a") + 1


def bits5(value: int) -> list[int]:
    """Five bits, most significant first. Index 0 is the top hole."""
    if not 0 <= value <= 31:
        raise ValueError(f"value out of range: {value}")
    return [(value >> shift) & 1 for shift in (4, 3, 2, 1, 0)]


def title_strips(title: str) -> list[list[int]]:
    """Columns per strip, without the leader: 0 is a word gap, 1-26 are letters.

    Strips break between words, like lines of text, at MAX_COLS columns. A word longer than
    MAX_COLS is split hard.
    """
    strips: list[list[int]] = []
    current: list[int] = []
    for word in normalize_title(title):
        values = [letter_value(c) for c in word]
        while len(values) > MAX_COLS:
            if current:
                strips.append(current)
                current = []
            strips.append(values[:MAX_COLS])
            values = values[MAX_COLS:]
        if current and len(current) + 1 + len(values) > MAX_COLS:
            strips.append(current)
            current = []
        if current:
            current.append(0)
        current.extend(values)
    if current:
        strips.append(current)
    return strips


def decode_strips(strips: list[list[int]]) -> str:
    """The inverse of title_strips: the normalized title, words joined by single spaces."""
    words: list[str] = []
    for strip in strips:
        word = ""
        for v in strip:
            if v == 0:
                words.append(word)
                word = ""
            else:
                word += chr(v + ord("a") - 1)
        words.append(word)
    return " ".join(w for w in words if w)


# ---------------------------------------------------------------- edition code


def release_record_string(book_slug: str, edition: str, merge_commit: str, salt: int = 0) -> str:
    """`{book_slug}@{edition}:{merge_commit}`, lowercase SHA, with `#salt` only after a collision."""
    base = f"{book_slug}@{edition}:{merge_commit.lower()}"
    return base if salt == 0 else f"{base}#{salt}"


def edition_code(book_slug: str, edition: str, merge_commit: str, salt: int = 0) -> str:
    """First 40 bits of the SHA-256 of the release record string, as XXXX-XXXX in Crockford base 32."""
    record = release_record_string(book_slug, edition, merge_commit, salt).encode("utf-8")
    n = int.from_bytes(hashlib.sha256(record).digest()[:5], "big")
    symbols = "".join(CROCKFORD[(n >> (35 - 5 * i)) & 31] for i in range(8))
    return f"{symbols[:4]}-{symbols[4:]}"


def parse_code(text: str) -> str | None:
    """Normalize what a reader typed: XXXX-XXXX, or None when it can't be a code.

    Spaces and hyphens are removed, O reads as 0, I and L read as 1, and U is rejected.
    """
    s = "".join(text.split()).replace("-", "").upper()
    s = s.replace("O", "0").replace("I", "1").replace("L", "1")
    if len(s) != 8 or any(c not in CROCKFORD for c in s):
        return None
    return f"{s[:4]}-{s[4:]}"


def fingerprint_columns(code: str) -> list[int]:
    """The marker column, then one column per code symbol holding its value 0-31."""
    norm = parse_code(code)
    if norm is None:
        raise ValueError(f"not an edition code: {code!r}")
    return [MARKER] + [CROCKFORD.index(c) for c in norm.replace("-", "")]


# ---------------------------------------------------------------- history tape

HISTORY_ROWS = ["prose", "deps", "content", "expert_review", "breaking"]   # data rows, top to bottom
LABEL_TO_KIND = {
    "kind:prose": "prose",
    "kind:deps": "deps",
    "kind:content": "content",
    "review:expert": "expert_review",
    "breaking": "breaking",
}
KIND_LABELS = [label for label in LABEL_TO_KIND if label.startswith("kind:")]


def edition_kinds(pr_labels: list[list[str]]) -> dict[str, bool]:
    """The union of the kinds of change across every pull request merged into one edition."""
    kinds = {k: False for k in HISTORY_ROWS}
    for labels in pr_labels:
        for label in labels:
            if label in LABEL_TO_KIND:
                kinds[LABEL_TO_KIND[label]] = True
    return kinds


def history_column(kinds: dict[str, bool]) -> list[int]:
    return [1 if kinds[k] else 0 for k in HISTORY_ROWS]


def main(argv: list[str]) -> int:
    if len(argv) == 5 and argv[1] == "code":
        print(edition_code(argv[2], argv[3], argv[4]))
        return 0
    if len(argv) == 3 and argv[1] == "encode":
        for strip in title_strips(argv[2]):
            print(" ".join(f"{v:2d}" for v in strip))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
