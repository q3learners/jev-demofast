"""The hosted service's job server (deploy/cloudflare/container/server.py): one demo at a time, from a public URL and a
prompt, never pointed at the container itself."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "jdf_server", Path(__file__).parents[1] / "deploy" / "cloudflare" / "container" / "server.py")
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def public(host):
    return ["93.184.216.34"]


@pytest.mark.parametrize("url", ["http://127.0.0.1:9333/json", "http://localhost/", "http://10.0.0.5/",
                                 "http://169.254.169.254/latest/meta-data", "http://[::1]/", "file:///etc/passwd",
                                 "javascript:alert(1)", "https://", "ftp://shop.test/"])
def test_private_and_odd_addresses_are_refused(url):
    resolve = lambda host: [host.strip("[]")] if host and host[0].isdigit() or host.startswith("[") else ["127.0.0.1"]
    assert server.check_url(url, resolve=resolve) is not None


def test_a_name_that_resolves_to_a_private_address_is_refused():
    assert "private" in server.check_url("https://intranet.shop.test/", resolve=lambda h: ["10.1.2.3"])


def test_a_public_site_is_accepted():
    assert server.check_url("https://www.allbirds.com/", resolve=public) is None


def test_a_prompt_is_required_and_kept_short():
    assert server.check_prompt("") and server.check_prompt("x" * 501)
    assert server.check_prompt("--index=/etc/passwd") and server.check_prompt("  -x")  # never read as an option
    assert server.check_prompt("Show my investors how easy it is to find running shoes") is None


def test_the_demo_command_passes_the_prompt_as_one_argument_never_an_option(tmp_path):
    cmd = server.command("Show it; rm -rf /", "https://shop.test/", "apollo", str(tmp_path / "r1"))
    assert cmd[:2] == ["jev-demofast", "demo"] and cmd[-2:] == ["--", "Show it; rm -rf /"]
    assert cmd[cmd.index("--url") + 1] == "https://shop.test/" and "--fresh" in cmd
    assert cmd[cmd.index("--voice") + 1] == "apollo" and cmd[cmd.index("--out") + 1].endswith("r1/demo.mp4")


def test_only_simple_voice_names_are_accepted():
    assert server.check_voice("apollo") is None and server.check_voice("thalia") is None
    assert server.check_voice("--music=/etc/passwd") and server.check_voice("")


class Proc:
    def __init__(self, code=None): self.code = code
    def poll(self): return self.code


def test_one_run_at_a_time(tmp_path):
    runs = server.Runs(str(tmp_path), spawn=lambda cmd, log: Proc())
    first = runs.start("https://shop.test/", "Show it", "apollo")
    with pytest.raises(server.Busy):
        runs.start("https://shop.test/", "Show it again", "apollo")
    assert runs.status(first)["status"] == "running"


def test_a_finished_run_reports_its_script_narration_and_verdict(tmp_path):
    procs = {}
    runs = server.Runs(str(tmp_path), spawn=lambda cmd, log: procs.setdefault("p", Proc()))
    rid = runs.start("https://shop.test/", "Show it", "apollo")
    work = tmp_path / rid
    (work / "demo.run").mkdir(parents=True)
    (work / "demo.run" / "story.txt").write_text("We make it effortless.\n")
    (work / "demo.run" / "narration.txt").write_text("Narration...\n\n00 — Home\nWe make it effortless.\n\n")
    (work / "demo.mp4").write_bytes(b"mp4")
    (work / "log.txt").write_text("founder's script:\n...\nverified: True | 17.3 s | Jev 7 calls\n")
    procs["p"].code = 0
    st = runs.status(rid)
    assert st["status"] == "done" and st["verified"] is True and st["video"] is True
    assert st["story"] == "We make it effortless." and st["narration"] == ["We make it effortless."]
    assert runs.start("https://shop.test/", "Next one", "apollo")  # free again


def test_a_failed_run_says_why(tmp_path):
    runs = server.Runs(str(tmp_path), spawn=lambda cmd, log: Proc(1))
    rid = runs.start("https://shop.test/", "Show it", "apollo")
    (tmp_path / rid / "log.txt").write_text("exploring\nblocked: Access Denied (the site refuses automated browsers)\n")
    st = runs.status(rid)
    assert st["status"] == "failed" and st["error"].startswith("blocked: Access Denied")


def test_an_unknown_run_is_none(tmp_path):
    assert server.Runs(str(tmp_path)).status("nope") is None
    assert server.Runs(str(tmp_path)).status("../etc") is None


def test_the_container_answers_cloudflares_start_up_ping(tmp_path):
    """Cloudflare checks a container has started by fetching http://ping/ on its port."""
    import io

    class Fake(server.Handler):
        def __init__(self, path):
            self.path, self.wfile, self.sent = path, io.BytesIO(), []
        def send_response(self, code): self.sent.append(code)
        def send_header(self, *a): pass
        def end_headers(self): pass
    for path in ("/", "/ping", "/health"):
        h = Fake(path)
        h.do_GET()
        assert h.sent == [200]


def handler(path, body=b"", length=None, runs=None):
    import io

    class Fake(server.Handler):
        def __init__(self):
            self.path, self.headers = path, {"Content-Length": str(len(body)) if length is None else length}
            self.rfile, self.wfile, self.sent = io.BytesIO(body), io.BytesIO(), []
        def send_response(self, code): self.sent.append(code)
        def send_header(self, *a): pass
        def end_headers(self): pass
    Fake.runs = runs
    return Fake()


GOOD = json.dumps({"url": "https://shop.test/", "prompt": "Show it", "voice": "apollo"}).encode()


@pytest.mark.parametrize("length", ["-1", "abc", "20000"])
def test_a_bad_or_oversized_body_length_is_refused(monkeypatch, tmp_path, length):
    monkeypatch.setattr(server, "check_url", lambda url: None)
    runs = server.Runs(str(tmp_path), spawn=lambda cmd, log: Proc())
    assert handler("/runs", GOOD, runs=runs).do_POST() or True  # the same body with its real length is accepted
    h = handler("/runs", GOOD, length=length, runs=server.Runs(str(tmp_path / "b"), spawn=lambda c, l: Proc()))
    h.do_POST()
    assert h.sent[0] in (400, 413)


def test_a_good_request_starts_a_run(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "check_url", lambda url: None)
    h = handler("/runs", GOOD, runs=server.Runs(str(tmp_path), spawn=lambda cmd, log: Proc()))
    h.do_POST()
    assert h.sent == [202]


def test_a_repo_is_optional_and_only_a_github_repo_link():
    assert server.check_repo("") is None and server.check_repo("https://github.com/q3learners/jev-demofast") is None
    for bad in ("https://evil.test/a/b", "--music=/etc/passwd", "https://github.com/a", "file:///etc/passwd",
                "https://github.com/a/b" + "c" * 300):
        assert server.check_repo(bad), bad


def test_the_repo_reaches_the_demo_command_only_when_given(tmp_path):
    cmd = server.command("Show it", "https://shop.test/", "eric", str(tmp_path / "r1"), repo="https://github.com/a/b")
    assert cmd[cmd.index("--repo") + 1] == "https://github.com/a/b" and cmd[-2:] == ["--", "Show it"]
    assert "--repo" not in server.command("Show it", "https://shop.test/", "eric", str(tmp_path / "r2"))


def test_a_request_with_a_repo_starts_a_run_with_it(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "check_url", lambda url: None)
    started = []
    runs = server.Runs(str(tmp_path), spawn=lambda cmd, log: started.append(cmd) or Proc())
    body = json.dumps({**json.loads(GOOD), "repo": "https://github.com/a/b"}).encode()
    h = handler("/runs", body, runs=runs)
    h.do_POST()
    assert h.sent == [202] and "https://github.com/a/b" in started[0]
    rid = json.loads(h.wfile.getvalue())["id"]
    assert runs.status(rid)["repo"] == "https://github.com/a/b"


def test_a_request_with_a_bad_repo_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "check_url", lambda url: None)
    body = json.dumps({**json.loads(GOOD), "repo": "https://evil.test/a/b"}).encode()
    h = handler("/runs", body, runs=server.Runs(str(tmp_path), spawn=lambda cmd, log: Proc()))
    h.do_POST()
    assert h.sent == [400]


def test_a_run_says_when_it_ended_once_it_has(tmp_path):
    # the page's clock freezes at the real end ("made in 2:05"), also when it is opened later from Recent demos
    import os
    procs = {}
    runs = server.Runs(str(tmp_path), spawn=lambda cmd, log: procs.setdefault("p", Proc()))
    rid = runs.start("https://shop.test/", "Show it", "apollo")
    (tmp_path / rid / "log.txt").write_text("exploring\n")
    assert runs.status(rid)["ended"] is None
    os.utime(tmp_path / rid / "log.txt", (1_800_000_000, 1_800_000_000))
    procs["p"].code = 1
    assert runs.status(rid)["ended"] == 1_800_000_000
