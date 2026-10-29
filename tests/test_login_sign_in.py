"""Signing in with the founder's answer: fields by label, secrets typed straight into the focused password input
(never observed, never through act), one retry on a wrong password, the emailed-code step, and an honest "stuck"
when sign-in lands on a page whose every way on is a hazard (K-12's card check)."""
from jev_demofast.explore.buttons import SIGN_IN_FORM_JS
from jev_demofast.login import sign_in as sign_in_mod
from jev_demofast.login.sign_in import sign_in

ORIGIN = "https://k12.test"
FORM = {"id": "f1", "title": "Welcome back.", "page": "/signin",
        "fields": [{"name": "email", "label": "Email", "secret": False},
                   {"name": "password", "label": "Password", "secret": True}]}
GOOD = {"email": "parent@demo.test", "password": "pw-Zq81-unique"}


class Site:
    """after: where a correct sign-in lands ("/home", "/code" or "/setup/verify")."""
    def __init__(self, after="/home", code="424242"):
        self.after, self.code, self.path, self.error = after, code, "/", ""
        self.typed, self.secret_typed, self.acts = {}, [], []
        self.focus_ok = True
        outer = self

        class B:
            def call(self, method, **p):
                if method == "Page.navigate":
                    outer.path, outer.error, outer.typed = p["url"].removeprefix(ORIGIN), "", {}
                if method == "Input.insertText":
                    outer.secret_typed.append(p["text"])
                return {}

            def evaluate(self, js, **k):
                if js == SIGN_IN_FORM_JS:
                    return outer.path == "/signin"
                if js.startswith(sign_in_mod.FOCUS_SECRET_JS_START):
                    return outer.path == "/signin"
                if js == sign_in_mod.FOCUSED_IS_PASSWORD_JS:
                    return outer.path == "/signin" and outer.focus_ok
                return None
        self.browser = B()

    def wait_loaded(self): pass
    def wait_for_page(self): return "settled"

    def observe(self):
        text = {"/signin": "Welcome back.\nEmail\nPassword" + (f"\n{self.error}" if self.error else ""),
                "/code": "Check your email\nEnter the code we sent",
                "/home": "Your family\nAdd student",
                "/setup/verify": "Verify you are the parent\nCard number\nContinue"}[self.path.split("?")[0]]
        self.page = {"url": ORIGIN + self.path, "text": text}
        return self.page

    def elements(self):
        if self.path == "/signin":
            return [{"node": 1, "role": "textbox", "label": "Email\nyou@example.com", "actions": {"fill": {}}},
                    {"node": 2, "role": "button", "label": "Sign in", "actions": {"click": {}}}]
        if self.path == "/code":
            return [{"node": 3, "role": "textbox", "label": "Code", "actions": {"fill": {}}},
                    {"node": 4, "role": "button", "label": "Verify", "actions": {"click": {}}}]
        if self.path.split("?")[0] == "/setup/verify":
            return [{"node": 5, "role": "button", "label": "Continue", "actions": {"click": {}}}]
        return [{"node": 6, "role": "button", "label": "Add student", "actions": {"click": {}}}]

    def act(self, e, kind, text=None):
        self.acts.append((e["label"], kind, text))
        if kind == "fill":
            self.typed[e["label"].split("\n")[0]] = text
        elif self.path == "/signin" and e["label"] == "Sign in":
            if self.typed.get("Email") == GOOD["email"] and self.secret_typed[-1:] == [GOOD["password"]]:
                self.path = self.after
            else:
                self.error = "Incorrect email or password."
        elif self.path == "/code" and e["label"] == "Verify" and self.typed.get("Code") == self.code:
            self.path = "/home"
        self.observe()


def test_signs_in_and_leaves_the_form():
    s = Site()
    assert sign_in(s, ORIGIN, FORM, GOOD, log=lambda m: None) == "signed in" and s.path == "/home"


def test_secret_values_never_go_through_act():
    s = Site()
    sign_in(s, ORIGIN, FORM, GOOD, log=lambda m: None)
    assert all(text != GOOD["password"] for _, _, text in s.acts) and s.secret_typed == [GOOD["password"]]


def test_a_wrong_password_asks_once_more_then_fails():
    s, asked = Site(), []

    def ask(q):
        asked.append(q)
        return {"id": q["id"], "form": "f1", "values": {"email": GOOD["email"], "password": "still-wrong"}}
    result = sign_in(s, ORIGIN, FORM, {**GOOD, "password": "wrong"}, ask=ask, log=lambda m: None)
    assert len(asked) == 1 and asked[0]["retry"] == "Incorrect email or password."
    assert result.startswith("failed:") and "wrong" not in result


def test_a_wrong_password_then_the_right_one_signs_in():
    s = Site()
    ask = lambda q: {"id": q["id"], "form": "f1", "values": GOOD}
    assert sign_in(s, ORIGIN, FORM, {**GOOD, "password": "wrong"}, ask=ask, log=lambda m: None) == "signed in"


def test_a_code_step_asks_for_the_code():
    s, asked = Site(after="/code"), []

    def ask(q):
        asked.append(q)
        return {"id": q["id"], "form": q["forms"][0]["id"], "values": {"code": "424242"}}
    assert sign_in(s, ORIGIN, FORM, GOOD, ask=ask, log=lambda m: None) == "signed in"
    assert [f["label"] for f in asked[0]["forms"][0]["fields"]] == ["Code"] and s.path == "/home"


def test_landing_on_a_hazard_page_is_reported():
    s = Site(after="/setup/verify")
    assert sign_in(s, ORIGIN, FORM, GOOD, log=lambda m: None) == "stuck: /setup/verify"


def test_the_result_never_contains_a_value():
    said = []
    for after in ("/home", "/code", "/setup/verify"):
        result = sign_in(Site(after=after), ORIGIN, FORM, GOOD, ask=lambda q: None, log=said.append)
        assert GOOD["password"] not in result and GOOD["email"] not in result
    assert not any(GOOD["password"] in m or GOOD["email"] in m for m in said)


def test_a_corrected_answer_replaces_the_first_in_place():
    values = {**GOOD, "password": "wrong"}
    sign_in(Site(), ORIGIN, FORM, values, ask=lambda q: {"id": q["id"], "form": "f1", "values": dict(GOOD)},
            log=lambda m: None)
    assert values == GOOD


def test_a_secret_is_never_typed_unless_a_password_input_has_focus():
    """Security review: if the click left focus elsewhere, the password would be typed into whatever had it."""
    s = Site()
    s.focus_ok = False
    assert sign_in(s, ORIGIN, FORM, dict(GOOD), log=lambda m: None).startswith("failed:")
    assert s.secret_typed == []


def test_a_stuck_page_is_named_by_its_path_only():
    """Security review: the landing address may carry a token or the email in its query."""
    s = Site(after="/setup/verify?email=parent@demo.test&t=abc")
    result = sign_in(s, ORIGIN, FORM, dict(GOOD), log=lambda m: None)
    assert result == "stuck: /setup/verify"


def test_a_secret_never_goes_through_act_even_beside_a_plain_field_with_its_label():
    """Security review: a secret is typed only into a focused password input, never through observation or act."""
    s = Site()
    real = s.elements
    s.elements = lambda: real() + ([{"node": 7, "role": "textbox", "label": "Password", "actions": {"fill": {}}}]
                                   if s.path == "/signin" else [])
    sign_in(s, ORIGIN, FORM, dict(GOOD), log=lambda m: None)
    assert all(text != GOOD["password"] for _, _, text in s.acts) and s.secret_typed == [GOOD["password"]]


def test_a_plain_secret_field_is_filled_where_it_is_and_the_password_only_into_the_password_input():
    s = Site()
    form = {**FORM, "fields": FORM["fields"] + [{"name": "pin", "label": "PIN", "secret": True, "password_input": False}]}
    real = s.elements
    s.elements = lambda: real() + ([{"node": 8, "role": "textbox", "label": "PIN", "actions": {"fill": {}}}]
                                   if s.path == "/signin" else [])
    sign_in(s, ORIGIN, form, {**GOOD, "pin": "4321"}, log=lambda m: None)
    assert ("PIN", "fill", "4321") in s.acts and s.secret_typed == [GOOD["password"]]
