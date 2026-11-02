import json
import shutil
import subprocess
import sys

from re_standards.examples import HARNESS


def test_examples_can_import_shared_modules_from_their_folder(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("")
    (tmp_path / "lib" / "shared.py").write_text("ANSWER = 42\n")
    (tmp_path / "uses-lib.py").write_text("from lib.shared import ANSWER\nprint('answer:', ANSWER)\n")
    shutil.copy(HARNESS, tmp_path / ".re_harness.py")
    report = tmp_path / "report.json"
    r = subprocess.run([sys.executable, "-I", ".re_harness.py", "uses-lib.py"], cwd=tmp_path, capture_output=True, text=True,
                       env={"RE_EXAMPLE_REPORT": str(report)})
    assert r.returncode == 0, r.stderr
    assert r.stdout == "answer: 42\n"
    assert json.loads(report.read_text())["exit"] == 0


def test_libraries_reached_through_local_modules_are_reported(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "__init__.py").write_text("")
    (tmp_path / "lib" / "render.py").write_text("import markdown_it\n\ndef html(text):\n    return markdown_it.MarkdownIt().render(text)\n")
    (tmp_path / "uses-lib.py").write_text("from lib.render import html\nprint(html('*hi*').strip())\n")
    shutil.copy(HARNESS, tmp_path / ".re_harness.py")
    report = tmp_path / "report.json"
    r = subprocess.run([sys.executable, "-I", ".re_harness.py", "uses-lib.py"], cwd=tmp_path, capture_output=True, text=True,
                       env={"RE_EXAMPLE_REPORT": str(report)})
    assert r.returncode == 0, r.stderr
    assert "markdown-it-py" in json.loads(report.read_text())["direct"]


def test_an_example_can_serve_and_call_loopback_with_the_network_blocked(tmp_path):
    from re_standards.examples import can_block_network
    if not can_block_network():
        import pytest
        pytest.skip("unshare -rn isn't allowed here")
    (tmp_path / "loop.py").write_text(
        "import socket, urllib.request\n"
        "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen()\n"
        "socket.create_connection(s.getsockname(), timeout=2).close()\n"
        "print('loopback: ok')\n"
        "try:\n"
        "    urllib.request.urlopen('https://pypi.org', timeout=3)\n"
        "    print('outside: reachable')\n"
        "except OSError:\n"
        "    print('outside: blocked')\n")
    shutil.copy(HARNESS, tmp_path / ".re_harness.py")
    report = tmp_path / "report.json"
    r = subprocess.run(["unshare", "-rn", sys.executable, "-I", ".re_harness.py", "loop.py"], cwd=tmp_path,
                       capture_output=True, text=True, env={"RE_EXAMPLE_REPORT": str(report)})
    assert r.returncode == 0, r.stderr
    assert r.stdout == "loopback: ok\noutside: blocked\n"
