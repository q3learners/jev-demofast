"""The login question: in a terminal (secrets read with getpass), or one JSON line each way for a host process (the
hosted app). No answer, a late answer or a garbled one is a skip. Values are never echoed."""
import io
import json

import pytest

from jev_demofast.login import ask
from jev_demofast.login.ask import ask_stdin, ask_terminal, question, secret_field

FORMS = [{"id": "f1", "title": "Welcome back.", "page": "/setup/account?mode=signin",
          "fields": [{"name": "email", "label": "Email", "secret": False},
                     {"name": "password", "label": "Password", "secret": True}]},
         {"id": "f2", "title": "Sign in to your subjects", "page": "/setup/kid",
          "fields": [{"name": "your-login-id", "label": "Your login ID", "secret": False},
                     {"name": "passcode", "label": "Passcode", "secret": True}]}]
Q = question(FORMS, "Part of this site is behind a login. Which sign-in should the demo use?")


@pytest.mark.parametrize("label,kind,want", [("Password", "", True), ("Passcode", "", True), ("PIN", "", True),
                                             ("Secret word", "password", True), ("Email", "", False),
                                             ("Your login ID", "", False)])
def test_secret_fields(label, kind, want):
    assert secret_field(label, kind) is want


def test_question_shape():
    assert set(Q) == {"id", "why", "forms", "retry"} and Q["retry"] is None
    assert Q["forms"][0]["fields"][1] == {"name": "password", "label": "Password", "secret": True}


def test_terminal_reads_secrets_with_getpass():
    asked_plain, asked_secret = [], []
    answers = iter(["1", "parent@demo.test"])
    got = ask_terminal(Q, input=lambda p: asked_plain.append(p) or next(answers),
                       getpass=lambda p: asked_secret.append(p) or "pw", out=lambda *a: None)
    assert got == {"id": "q1", "form": "f1", "values": {"email": "parent@demo.test", "password": "pw"}}
    assert len(asked_secret) == 1 and "Password" in asked_secret[0]


def test_terminal_skip():
    assert ask_terminal(Q, input=lambda p: "s", getpass=lambda p: "", out=lambda *a: None) is None


def test_terminal_one_form_needs_no_choice():
    one = question(FORMS[:1], "why")
    got = ask_terminal(one, input=lambda p: "parent@demo.test", getpass=lambda p: "pw", out=lambda *a: None)
    assert got["form"] == "f1"


def stdin_with(text):
    return io.StringIO(text)


def test_stdin_answer(monkeypatch):
    monkeypatch.setattr(ask, "_ready", lambda stream, timeout: True)
    said = []
    line = json.dumps({"id": "q1", "form": "f2", "values": {"your-login-id": "sky-fox-73", "passcode": "1234"}})
    got = ask_stdin(Q, stream=stdin_with(line + "\n"), log=said.append)
    assert got["form"] == "f2" and got["values"]["passcode"] == "1234"
    assert len(said) == 1 and said[0].startswith("ask: ") and json.loads(said[0][5:]) == Q


@pytest.mark.parametrize("text", ["", "not json\n", json.dumps({"id": "q1", "skip": True}) + "\n",
                                  json.dumps({"id": "q1", "form": "f9", "values": {}}) + "\n"])
def test_stdin_timeout_and_garbage_are_skips(monkeypatch, text):
    monkeypatch.setattr(ask, "_ready", lambda stream, timeout: bool(text))
    assert ask_stdin(Q, stream=stdin_with(text), log=lambda m: None) is None


def test_an_answer_for_another_question_id_is_ignored(monkeypatch):
    monkeypatch.setattr(ask, "_ready", lambda stream, timeout: True)
    late = json.dumps({"id": "q0", "form": "f1", "values": {"email": "a", "password": "b"}})
    assert ask_stdin(Q, stream=stdin_with(late + "\n"), log=lambda m: None) is None


def test_the_log_line_never_contains_values(monkeypatch):
    monkeypatch.setattr(ask, "_ready", lambda stream, timeout: True)
    said = []
    line = json.dumps({"id": "q1", "form": "f1", "values": {"email": "parent@demo.test", "password": "pw-Zq81"}})
    ask_stdin(Q, stream=stdin_with(line + "\n"), log=said.append)
    assert not any("pw-Zq81" in m or "parent@demo.test" in m for m in said)


def test_the_ask_line_is_flushed_for_a_host(monkeypatch):
    """Review: under a pipe stdout is block-buffered; an unflushed ask: line never reaches the host."""
    flushed = []
    monkeypatch.setattr(ask.sys, "stdout", type("O", (), {"flush": lambda self: flushed.append(1), "write": lambda self, t: None})())
    monkeypatch.setattr(ask, "_ready", lambda stream, timeout: False)
    ask_stdin(Q, stream=stdin_with(""), log=lambda m: None)
    assert flushed
