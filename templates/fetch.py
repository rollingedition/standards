"""Fetch the third-party texts the book repos, the organization's community files and this repository use, verbatim.

    python templates/fetch.py

Never edit the fetched files by hand; rerun this script to refresh them. Each source is a URL the
publisher of the text maintains.
"""
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = {
    "licenses/CC-BY-4.0.txt": "https://creativecommons.org/licenses/by/4.0/legalcode.txt",
    "licenses/MIT.txt": "https://raw.githubusercontent.com/spdx/license-list-data/main/text/MIT.txt",
    "community/contributor-covenant-2.1.md":
        "https://raw.githubusercontent.com/EthicalSource/contributor_covenant/release/content/version/2/1/code_of_conduct.md",
    # data/mark-outlines.json holds Literata's letter outlines, so the font's copyright and licence travel with them
    "licenses/OFL-Literata.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/literata/OFL.txt",
}

for name, url in SOURCES.items():
    request = urllib.request.Request(url, headers={"User-Agent": "rolling-edition-standards (+https://rollingedition.com)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        (HERE / name).write_bytes(response.read())
    print(f"fetched {name} from {url}")
