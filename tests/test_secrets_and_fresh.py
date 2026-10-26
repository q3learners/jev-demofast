"""Secrets reach only the field they belong to; --fresh clears only the site being demoed."""
from jev_demofast.drive import jev_drive
from jev_demofast.drive.guards import password_secret
from jev_demofast.drive.session import origin, site_cookies
from jev_demofast.record.recorder import Recorder


def test_only_a_password_named_placeholder_goes_to_the_password_field():
    assert password_secret("Sign in as {{EMAIL}} with password {{PASSWORD}}") == "PASSWORD"
    assert password_secret("{{ADMIN_PIN}}") == "ADMIN_PIN"
    assert password_secret("log in with {{PW}}") == "PW"
    for name in ("PASSWD", "MYPASSWORD", "API_TOKEN", "CLIENT_SECRET", "OTP", "LICENSE_KEY", "ACCESS_CODE"):
        assert password_secret("{{" + name + "}}") == name   # when in doubt, a secret: never a visible field
    assert password_secret("Reset my password for {{EMAIL}}") is None
    assert password_secret("ship to {{SHIPPING_ADDRESS}}") is None  # "PIN" inside a word doesn't count
    assert password_secret(None) is None


def test_jev_drive_types_the_email_into_the_email_field_and_the_password_into_the_password_field(monkeypatch):
    monkeypatch.setenv("DEMO_EMAIL", "me@example.com")
    monkeypatch.setenv("DEMO_PASSWORD", "s3cret")
    email = {"node": 1, "role": "textbox", "label": "Email", "actions": {"fill": {}}, "current": "", "options": []}
    submit = {"node": 2, "role": "button", "label": "Sign in", "actions": {"click": {}}, "current": "Sign in",
              "options": []}

    class FakeSession:
        page = {"url": "https://app.test/login", "text": "Sign in"}
        typed, password = [], []
        class browser:
            evaluate = staticmethod(lambda js: None)
        def elements(self): return [email, submit]
        def act(self, e, kind, text=None): self.typed.append((e["label"], kind, text))
        def type_secret_into_password(self, text): self.password.append(text); return True
        def observe(self): return self.page
        def next_frame(self): pass
        def settle(self, before, max_s=6.0): return {"url": "https://app.test/dashboard", "text": "Welcome back"}

    class FakeCf:
        class s:
            read_model = "m"
        def chat_json(self, model, system, context): return {"values": {"Email": "{{EMAIL}}"}}
        def choose(self, instructions, options, state, allow_none=False): return "2", 0.9
        def yes(self, instructions, state, true="yes", false="no"): return 0.9

    s = FakeSession()
    goal = "Sign in as {{EMAIL}} with password {{PASSWORD}}"
    state = {"screen": {"url": "/login", "title": "Sign in", "visible_text": "Sign in"}}
    done = jev_drive._fill_and_submit(FakeCf(), s, Recorder(None, s), goal, [email], state, [], lambda m: None,
                                      lambda: 0)
    assert done
    assert ("Email", "fill", "me@example.com") in s.typed
    assert s.password == ["s3cret"]


def test_fresh_clears_storage_for_the_origin_including_its_port():
    assert origin("http://localhost:3000/sign-in") == "http://localhost:3000"
    assert origin("https://user:pw@staging.example.com/a?b=1") == "https://staging.example.com"


def test_fresh_deletes_only_this_sites_cookies():
    cookies = [{"name": n, "domain": d, "path": "/"} for n, d in [
        ("own", "staging.example.com"), ("parent", ".example.com"), ("sub", "api.staging.example.com"),
        ("sibling", "app.example.com"), ("other", "github.com"), ("lookalike", "notexample.com")]]
    assert [c["name"] for c in site_cookies(cookies, "staging.example.com")] == ["own", "parent", "sub"]
