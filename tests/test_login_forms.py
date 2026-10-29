"""The sign-in forms the founder chooses from: reopened live (the map holds no password fields), told from sign-up
forms by Clef (K-12: sign-in 0.90-0.97, sign-up 0.01), titled by their own text, and offered once each."""
from jev_demofast.login import forms
from jev_demofast.login.forms import sign_in_forms

ORIGIN = "https://k12.test"
# page → (text lines, non-secret field labels, password labels, Clef's sign-in score as measured on 29 October)
PAGES = {
    "/setup/account?mode=signin": (["TutorQ K-12", "Welcome back. Sign in to get to your family.", "Welcome back."],
                                   ["Email"], ["Password"], 0.95),
    "/setup/account?as=student&mode=signin": (["TutorQ K-12", "Welcome back. Sign in to get to your family.",
                                               "Welcome back."], ["Email"], ["Password"], 0.97),
    "/setup/kid": (["TutorQ K-12", "Use the login and passcode your parent gave you.", "Sign in to your subjects"],
                   ["Your login ID"], ["Passcode"], 0.90),
    "/setup/account": (["TutorQ K-12", "Your account, current step"], ["Email"], ["Password"], 0.01),
    "/setup/account?mode=new": (["TutorQ K-12", "Your account, current step"], ["Email"], ["Password"], 0.01),
    "/setup/account?as=student": (["TutorQ K-12", "Your account, current step"], ["Email"], ["Password"], 0.01),
}
INDEX = {"_site": {}, "/setup/who": {"sign_in": False, "examples": ["/setup/who"]},
         **{p: {"sign_in": True, "examples": [p]} for p in PAGES}}


class Clef:
    s = type("S", (), {"check_model": "@cf/cloudflare/clef"})()

    def yes(self, q, state, true="", false="", model=None, images=None):
        assert q == forms.QUESTION and true == forms.TRUE and false == forms.FALSE and images
        return PAGES[state["url"].removeprefix(ORIGIN)][3]


class FakeSession:
    def __init__(self):
        self.path = "/setup/who"
        outer = self

        class B:
            def call(self, method, **p):
                if method == "Page.navigate":
                    outer.path = p["url"].removeprefix(ORIGIN)
                if method == "Page.captureScreenshot":
                    return {"data": ""}
                return {}

            def evaluate(self, js, **k):
                if js == forms.PASSWORD_LABELS_JS:
                    return PAGES[outer.path][2]
                return None
        self.browser = B()

    def wait_loaded(self): pass

    def observe(self):
        text = PAGES[self.path][0] if self.path in PAGES else ["TutorQ K-12", "Who is this?"]
        self.page = {"url": ORIGIN + self.path, "text": "\n".join(text)}
        return self.page

    def elements(self):
        fields = PAGES[self.path][1] if self.path in PAGES else []
        return [{"node": i, "role": "textbox", "label": l, "actions": {"fill": {}}} for i, l in enumerate(fields)] + \
            [{"node": 9, "role": "button", "label": "Back", "actions": {"click": {}}}]


def offered(cf=None):
    return sign_in_forms(FakeSession(), ORIGIN, INDEX, cf or Clef(), log=lambda m: None)


def test_k12_gives_two_forms():
    assert [f["title"] for f in offered()] == ["Welcome back.", "Sign in to your subjects"]


def test_titles_skip_text_shared_by_every_page():
    assert all(f["title"] != "TutorQ K-12" for f in offered())


def test_sign_up_forms_are_dropped():
    assert not any(f["page"] in ("/setup/account", "/setup/account?mode=new") for f in offered())


def test_duplicates_are_offered_once():
    assert sum(f["title"] == "Welcome back." for f in offered()) == 1


def test_no_check_model_offers_nothing():
    said = []
    assert sign_in_forms(FakeSession(), ORIGIN, INDEX, None, log=said.append) == []
    assert any("check model" in m for m in said)


def test_password_fields_are_secret():
    by_title = {f["title"]: f for f in offered()}
    assert by_title["Welcome back."]["fields"] == [{"name": "email", "label": "Email", "secret": False},
                                                   {"name": "password", "label": "Password", "secret": True}]
    assert by_title["Sign in to your subjects"]["fields"] == [
        {"name": "your-login-id", "label": "Your login ID", "secret": False},
        {"name": "passcode", "label": "Passcode", "secret": True}]
    assert [f["id"] for f in offered()] == ["f1", "f2"]


def test_only_password_inputs_are_secret():
    """Security review: a plain input labelled like a secret ("PIN", "Zip code") is a plain field; only a password
    input is secret, so a secret only ever goes where a password input has focus."""
    PAGES["/setup/pin"] = (["TutorQ K-12", "Enter your PIN please"], ["PIN"], ["Password"], 0.95)
    INDEX["/setup/pin"] = {"sign_in": True, "examples": ["/setup/pin"]}
    try:
        pin = next(f for f in offered() if f["page"] == "/setup/pin")
        assert pin["fields"][0] == {"name": "pin", "label": "PIN", "secret": False}
    finally:
        del PAGES["/setup/pin"], INDEX["/setup/pin"]
