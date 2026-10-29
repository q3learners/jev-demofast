"""A K-12-shaped app behind the Session interface, for the behaviour map's tests. It subclasses the real Session, so
every press goes through Session.act and its safety checks (hazard labels, the money judge, the own-email rule).

Set up: tabs Home, Kids, Subjects, Settings on every screen. Kids lists kids with "Add a kid" and "Delete"; the add
form (First name, Age, Add, Continue) asks "Add <name> first?" (Skip / Add) when Continue is pressed with a name typed;
adding starts a wizard: "<name>'s login" → "Subjects for <name>" → "All set". Subjects has 40 items. Settings has a
switch and "Log out". Home has "Upgrade" (a card form). Partway: the setup step "Your kids", then the card check.
With flutter=True a dialog hides everything else, as K-12's did live ("Skip Add")."""
from jev_demofast.browser.cdp import StalePage
from jev_demofast.behaviour import screens
from jev_demofast.drive.session import Session

ORIGIN = "https://k12.test"


class _Browser:
    def __init__(self, app):
        self.app = app

    def evaluate(self, js, **k):
        if js == screens.DIALOG_JS:
            return self.app.dialog["title"] if self.app.dialog else None
        return None

    def call(self, method, **p):
        if method == "Page.navigate":
            self.app.goto(p["url"])
        elif method == "Input.dispatchKeyEvent" and p.get("key") == "Escape" and p.get("type") == "keyDown":
            self.app.dialog = None
        return {"data": ""}

    def act(self, action, page, text=None):
        self.app.do(action["node"], text)


class FakeApp(Session):
    def __init__(self, state="set up", flutter=False, sections=("Home", "Kids", "Subjects", "Settings"),
                 strand_after=None, subjects=40):
        self.state, self.flutter, self.tabs = state, flutter, list(sections)
        self.strand_after, self.stranded, self.subjects = strand_after, False, subjects
        self.kids, self.form, self.dialog, self.new_kid = ["Ava", "Leo"], {}, None, None
        self.pressed, self.typed = [], []
        self.browser, self.hazards, self.own_email, self.money_step = _Browser(self), True, "parent@demo.test", None
        self.is_flutter, self.host, self.start_url = flutter, "k12.test", ORIGIN + "/"
        self.path = "/setup/kids" if state == "partway" else "/home"
        self.observe()

    # --- what the screen shows ----------------------------------------------------------------------------------
    def _screen(self):
        """(texts, [(role, label, kind)]) for the current path."""
        p, tabs = self.path, [("tab", t, "click") for t in self.tabs]
        if self.stranded:
            return ["Something went wrong"], []
        if p == "/home":
            return ["Welcome back", "Your family at a glance"], tabs + [("button", "Upgrade", "click")]
        if p == "/kids":
            return ["Your kids", *self.kids], tabs + [("link", k, "click") for k in self.kids] + \
                [("button", "Add a kid", "click"), ("button", "Delete", "click")]
        if p.startswith("/kids/") and p.count("/") == 2 and p != "/kids/new":
            return [f"{p.split('/')[2].title()}, 14", "Their subjects"], tabs
        if p in ("/kids/new", "/setup/kids"):
            head = ["Your kids, current step", "Verify you are the parent, next"] if p == "/setup/kids" else []
            return head + ["Who are we setting up?", *(self.kids if p == "/setup/kids" else [])], \
                (tabs if p == "/kids/new" else []) + [("textbox", "First name", "fill"), ("textbox", "Age", "fill"),
                                                      ("button", "Add", "click"), ("button", "Continue", "click")]
        if p == "/kids/setup/login":
            return [f"{self.new_kid}'s login"], [("textbox", "Login ID", "fill"), ("button", "Next", "click")]
        if p == "/kids/setup/subjects":
            return [f"Subjects for {self.new_kid}"], [("textbox", "Grade", "fill"), ("button", "Next", "click")]
        if p == "/kids/setup/done":
            return ["All set", f"{self.new_kid} is ready"], tabs + [("button", "Done", "click")]
        if p == "/subjects":
            return ["Subjects"], tabs + [("link", f"Subject {i}", "click") for i in range(1, self.subjects + 1)]
        if p.startswith("/subjects/"):
            return [f"Subject {p.split('/')[2]}", "Lessons"], tabs
        if p == "/settings":
            return ["Settings"], tabs + [("switch", "Email me weekly", "click"), ("button", "Log out", "click")]
        if p == "/upgrade":
            return ["Start your Pro plan", "Card number"], tabs + [("textbox", "Card number", "fill"),
                                                                   ("button", "Continue", "click")]
        if p == "/setup/verify":
            return ["Prove you're the parent.", "Verify you are the parent, current step"], \
                [("button", "Verify with a card", "click")]
        return [p.strip("/").title()], tabs

    def _controls(self):
        if self.dialog:
            return [("button", b, "click") for b in self.dialog["buttons"]]
        return self._screen()[1]

    def observe(self):
        texts, _ = self._screen()
        controls = self._controls()
        if self.dialog and self.flutter:
            text = " ".join(label for _, label, _ in controls)
        else:
            text = "\n".join(([self.dialog["title"]] if self.dialog else []) + texts +
                             [label for _, label, _ in controls])
        self.page = {"url": ORIGIN + self.path, "title": "TutorQ K-12", "text": text}
        return self.page

    def elements(self):
        return [{"node": i, "role": role, "label": label, "actions": {kind: {"node": i}}}
                for i, (role, label, kind) in enumerate(self._controls())]

    def refind(self, element):
        e = next((e for e in self.elements() if e["node"] == element["node"] and e["label"] == element["label"]), None)
        if e is None:
            raise StalePage(f"{element['label']!r} is gone")
        return e

    def arm(self): pass
    def wait_for_page(self, *a, **k): return "settled"
    def wait_loaded(self, *a, **k): pass
    def next_frame(self): pass
    def close(self): pass

    def restart(self, url=None):
        """A new session: back on the first screen, no longer stranded."""
        self.stranded, self.dialog = False, None
        self.path = "/setup/kids" if self.state == "partway" else "/home"
        self.observe()
        return self

    # --- what pressing does -------------------------------------------------------------------------------------
    def goto(self, url):
        if not self.stranded:
            self.path, self.dialog = url.removeprefix(ORIGIN) or "/home", None
        self.observe()

    def _add(self):
        name = self.form.get("First name")
        if name:
            self.kids.append(name)
            self.new_kid, self.form = name, {}
            if self.path == "/kids/new":
                self.path = "/kids/setup/login"

    def do(self, node, text):
        role, label, kind = self._controls()[node]
        if kind == "fill":
            self.form[label] = text
            self.typed.append(text)
            self.observe()
            return
        self.pressed.append(label)
        if self.dialog:
            self.dialog = None
            if label == "Add":
                self._add()
            elif self.path == "/kids/new":
                self.path, self.form = "/kids", {}
        elif label in self.tabs:
            self.path = "/" + label.lower()
        elif label == "Add a kid":
            self.path = "/kids/new"
        elif label == "Add":
            self._add()
        elif label == "Continue" and self.path in ("/kids/new", "/setup/kids"):
            if self.form.get("First name"):
                self.dialog = {"title": f"Add {self.form['First name']} first?", "buttons": ["Skip", "Add"]}
            else:
                self.path = "/setup/verify" if self.path == "/setup/kids" else "/kids"
        elif label == "Next":
            self.path = {"/kids/setup/login": "/kids/setup/subjects", "/kids/setup/subjects": "/kids/setup/done"}[
                self.path]
            self.form = {}
        elif label == "Done":
            self.path = "/kids"
        elif label == "Upgrade":
            self.path = "/upgrade"
        elif label in self.kids:
            self.path = f"/kids/{label.lower()}"
        elif label.startswith("Subject "):
            self.path = f"/subjects/{label.split()[1]}"
        if self.strand_after == label:
            self.stranded = True
        self.observe()
