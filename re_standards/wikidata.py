"""Fill in Wikidata IDs for taxonomy terms from their English Wikipedia titles, and flag titles that don't exist.

Needs the internet. Wikidata IDs never change when an article is renamed, so the sites use them for
schema.org `sameAs` links. Standard library only.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "rolling-edition-catalog/1.0"


def lookup(titles: list[str]) -> dict[str, str | None]:
    """Title -> Wikidata ID, or None when the article or its item doesn't exist. Follows redirects."""
    out: dict[str, str | None] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        query = urllib.parse.urlencode({
            "action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "redirects": 1,
            "format": "json", "titles": "|".join(t.replace("_", " ") for t in batch),
        })
        req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)["query"]
        alias = {n["from"]: n["to"] for n in data.get("normalized", [])}
        alias.update({r["from"]: r["to"] for r in data.get("redirects", [])})
        found = {p["title"]: p.get("pageprops", {}).get("wikibase_item")
                 for p in data["pages"].values() if "missing" not in p}
        for t in batch:
            name = t.replace("_", " ")
            while name in alias:
                name = alias[name]
            out[t] = found.get(name)
    return out


def resolve(taxonomy_path: Path, write: bool) -> list[str]:
    """Returns one problem per term whose title has no article or item. Writes the IDs when asked."""
    tax = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    terms = [t for t in tax["areas"] + tax["skills"] if t.get("wikipedia")]
    ids = lookup([t["wikipedia"] for t in terms])
    problems = [f"no Wikipedia article or Wikidata item for {t['id']}: {t['wikipedia']}"
                for t in terms if not ids.get(t["wikipedia"])]
    changed = [t["id"] for t in terms if ids.get(t["wikipedia"]) and t.get("wikidata") != ids[t["wikipedia"]]]
    if write:
        for t in terms:
            if ids.get(t["wikipedia"]):
                t["wikidata"] = ids[t["wikipedia"]]
        taxonomy_path.write_text(json.dumps(tax, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        problems += [f"{i}: Wikidata ID differs from Wikipedia's current item" for i in changed]
    return problems
