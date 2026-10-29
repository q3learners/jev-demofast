"""--login end to end: ask at the login wall, map and record signed in, in isolated contexts, and keep nothing the
founder typed. Without --login nothing changes."""
import argparse
import os

import pytest

from jev_demofast import cli
from jev_demofast.login import Login
from jev_demofast.login import flow as flow_mod

from test_login_sign_in import FORM, GOOD, ORIGIN, Site

PASSWORD = GOOD["password"]


def args(tmp_path, **k):
    base = dict(prompt="Show parents how to add a student", url=ORIGIN + "/", out=str(tmp_path / "demo.mp4"),
                work=None, voice=None, index=None, login=False, login_via="terminal", use_my_browser=False,
                fresh=True, dry_run=False, no_blur=False, picker="jev", repo="", product="", gif=False, yes=False)
    return argparse.Namespace(**{**base, **k})


class Sessions:
    """A Session class whose instances are the fake site; it records how each was made."""
    def __init__(self, after="/home"):
        self.made, self.after = [], after

    def __call__(self, url, fresh=False, isolated=False):
        s = Site(after=self.after)
        s.isolated, s.hazards, s.own_email = isolated, False, None
        s.close = lambda: None
        self.made.append(s)
        return s


def prepared(sessions, ask=lambda q: {"id": q["id"], "form": "f1", "values": dict(GOOD)}, log=lambda m: None):
    return Login.prepare(cf=None, url=ORIGIN + "/", index={}, ask=ask, log=log, session=sessions,
                         find_forms=lambda s, origin, index, cf, log: [FORM])


def test_login_with_use_my_browser_is_refused():
    a = argparse.Namespace(login=True, use_my_browser=True, fresh=False, url=ORIGIN, yes=True)
    with pytest.raises(SystemExit, match="--login"):
        cli.choose_browser(a, type("S", (), {"cdp_url": "http://127.0.0.1:9333"})())


def common(monkeypatch, tmp_path, ran):
    monkeypatch.setattr(cli, "_cf", lambda a=None, require=True: object())
    monkeypatch.setattr(cli, "site_map", lambda a, cf: str(tmp_path / "public.json"))
    monkeypatch.setattr(cli, "MAPS", tmp_path / "maps")
    monkeypatch.setattr(cli, "cmd_run", lambda a, cf: ran.append(a) or {"verified": True})
    monkeypatch.setattr(cli, "cmd_render", lambda a: None)
    monkeypatch.setattr(cli, "_note_prompt", lambda work, prompt: None)


def test_without_login_nothing_changes(monkeypatch, tmp_path):
    ran = []
    common(monkeypatch, tmp_path, ran)
    monkeypatch.setattr(flow_mod, "with_login", lambda *a, **k: (_ for _ in ()).throw(AssertionError("login used")))
    cli.cmd_demo(args(tmp_path))
    assert ran[0].index == str(tmp_path / "public.json") and getattr(ran[0], "session", None) is None


def test_the_logged_in_map_is_not_cached(monkeypatch, tmp_path):
    ran, sessions = [], Sessions()
    common(monkeypatch, tmp_path, ran)
    monkeypatch.setattr(flow_mod, "prepare", lambda cf, a, index, log: prepared(sessions))
    monkeypatch.setattr(flow_mod, "explore", lambda url, out, cf, session: open(out, "w").write("{}") and {})
    cli.cmd_demo(args(tmp_path, login=True))
    work = tmp_path / "demo.run"
    assert ran[0].index == str(work / "site-map-logged-in.json") and os.path.exists(ran[0].index)
    assert not (tmp_path / "maps").exists()


def test_recording_uses_a_signed_in_isolated_session():
    sessions = Sessions()
    login = prepared(sessions)
    s = login.session(ORIGIN + "/", fresh=True)
    assert s.isolated and s.hazards and s.own_email == GOOD["email"] and s.path == "/home"


def test_a_failed_sign_in_at_recording_stops_the_run(monkeypatch, tmp_path):
    sessions = Sessions()
    login = prepared(sessions)
    sessions.after = "/signin"  # the account stopped working between mapping and recording
    GOOD_COPY = dict(GOOD)
    login._values["password"] = "expired"
    with pytest.raises(RuntimeError, match="login: couldn't sign in for the recording"):
        login.session(ORIGIN + "/")
    assert GOOD_COPY == GOOD
    ran = []
    common(monkeypatch, tmp_path, ran)
    monkeypatch.setattr(cli, "cmd_run", lambda a, cf: (_ for _ in ()).throw(RuntimeError("login: couldn't sign in for the recording")))
    with pytest.raises(SystemExit, match="couldn't sign in for the recording"):
        cli.cmd_demo(args(tmp_path))


def test_no_credential_in_any_written_file_or_log(monkeypatch, tmp_path, capsys):
    ran, sessions = [], Sessions()
    common(monkeypatch, tmp_path, ran)
    said = []
    monkeypatch.setattr(flow_mod, "prepare", lambda cf, a, index, log: prepared(sessions, log=said.append))

    def explore(url, out, cf, session):
        s = session(url)
        open(out, "w").write(repr(s.observe()))  # everything the explorer could have read
        return {}
    monkeypatch.setattr(flow_mod, "explore", explore)
    cli.cmd_demo(args(tmp_path, login=True))
    # and a sign-in that fails loudly, with the password in its exception
    monkeypatch.setattr(flow_mod, "sign_in", lambda *a, **k: (_ for _ in ()).throw(ValueError(f"boom {PASSWORD}")))
    assert Login.prepare(cf=None, url=ORIGIN + "/", index={}, ask=lambda q: {"id": q["id"], "form": "f1",
                         "values": dict(GOOD)}, log=said.append, session=Sessions(),
                         find_forms=lambda *a: [FORM]) is None
    out = capsys.readouterr()
    written = "".join(open(os.path.join(d, f), errors="ignore").read()
                      for d, _, fs in os.walk(tmp_path) for f in fs)
    assert PASSWORD not in out.out + out.err + written + "\n".join(said)


def test_a_skip_runs_as_today(monkeypatch, tmp_path):
    ran, sessions = [], Sessions()
    common(monkeypatch, tmp_path, ran)
    monkeypatch.setattr(flow_mod, "prepare", lambda cf, a, index, log: prepared(sessions, ask=lambda q: None))
    cli.cmd_demo(args(tmp_path, login=True))
    assert ran[0].index == str(tmp_path / "public.json") and getattr(ran[0], "session", None) is None


def test_a_code_asked_at_every_sign_in_is_asked_again():
    """Review: each session is a new context (a new device to the site), and the code step had no one to ask."""
    sessions = Sessions(after="/code")
    codes = []

    def ask(q):
        if q["forms"][0]["fields"][0]["label"] == "Code":
            codes.append(1)
            return {"id": q["id"], "form": q["forms"][0]["id"], "values": {"code": "424242"}}
        return {"id": q["id"], "form": "f1", "values": dict(GOOD)}
    login = prepared(sessions, ask=ask)
    s = login.session(ORIGIN + "/")
    assert s.path == "/home" and len(codes) == 2


def test_a_login_that_fails_while_mapping_stops_cleanly(monkeypatch, tmp_path):
    ran = []
    common(monkeypatch, tmp_path, ran)
    monkeypatch.setattr(flow_mod, "with_login", lambda a, cf: (_ for _ in ()).throw(
        RuntimeError("login: couldn't sign in for the recording")))
    with pytest.raises(SystemExit, match="couldn't sign in"):
        cli.cmd_demo(args(tmp_path, login=True))
