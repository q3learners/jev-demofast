"""--login: once the public site is mapped, ask for a demo account, sign in off camera, map the logged-in app, and
record it signed in. The answer lives only in a Login object for the run; every session it makes is a new isolated
browser context (the persistent profile never holds the founder's session) with the logged-in hazards on."""
from ..behaviour.crawl import crawl as blueprint
from ..behaviour.fit import ask_how, fits, summary
from ..behaviour.model import legacy_routes
from ..behaviour.store import load_map, save_map
from ..drive.money import judge
from ..drive.session import Session, origin
from .ask import asker, question
from .forms import sign_in_forms
from .sign_in import sign_in

WHY = "Part of this site is behind a login. Which sign-in should the demo use?"
LOGGED_IN_MAP = "site-map-logged-in.json"  # the run's copy; the blueprint is also kept in the store (local runs)


class Login:
    def __init__(self, origin_, form, values, own_email, session_cls, log, ask=None, money_step=None):
        self._origin, self._form, self._values = origin_, form, values
        self._own_email, self._session_cls, self._log, self._ask = own_email, session_cls, log, ask
        self._money_step = money_step

    @classmethod
    def prepare(cls, cf, url, index, ask, log=print, session=Session, find_forms=sign_in_forms):
        """Find the sign-in forms, ask, sign in once to check the account works. A Login, or None to stay logged out
        (no form, a skip, or a sign-in that failed). Nothing logged here carries a value."""
        site, s = origin(url), session(url, isolated=True)
        try:
            forms = find_forms(s, site, index, cf, log)
            if not forms:
                return None
            answer = ask(question(forms, WHY))
            if answer is None:
                log("login: skipped; the demo stays logged out")
                return None
            form = next(f for f in forms if f["id"] == answer["form"])
            values = dict(answer["values"])
            try:
                result = sign_in(s, site, form, values, ask=ask, log=log)
            except Exception as err:  # its message may echo what was typed: only its kind is logged
                log(f"login: sign-in failed ({type(err).__name__}); the demo stays logged out")
                return None
            if result != "signed in":
                log(f"login: {result}; the demo stays logged out")
                return None
            email = next((values[f["name"]] for f in form["fields"]
                          if not f["secret"] and "mail" in f["label"].lower()), None)
            return cls(site, form, values, email, session, log, ask=ask,
                       money_step=judge(cf) if cf is not None else None)
        finally:
            s.close()

    def session(self, url, fresh=False, isolated=True):
        """A new isolated session, signed in, with the logged-in hazards on. Raises if the sign-in fails: a demo is
        never recorded logged out while claiming to be logged in."""
        s = self._session_cls(url, isolated=True)
        # a new context is a new device to the site: one that sends a code at every sign-in asks the founder again
        if self._values is None or sign_in(s, self._origin, self._form, self._values, ask=self._ask,
                                           log=self._log) != "signed in":
            s.close()
            raise RuntimeError("login: couldn't sign in for the recording")
        s.hazards, s.own_email, s.money_step = True, self._own_email, self._money_step
        return s

    @property
    def account_id(self):
        """Who the blueprint belongs to: the account's email, else its first non-secret value (a kid's login ID)."""
        if self._own_email:
            return self._own_email
        return next((self._values[f["name"]] for f in self._form["fields"] if not f["secret"]), "") \
            if self._values else ""

    def forget(self):
        self._values = self._own_email = self._ask = None


def prepare(cf, a, index, log):
    from ..index import load as load_index
    return Login.prepare(cf, a.url, load_index(index), asker(a.login_via), log=log)


def with_login(a, cf, log=print):
    """Sign in and map the signed-in app's behaviour (its blueprint, learning from the saved one); point the run at
    that map and those sessions. Asks the founder how to go on when the account can't show the demo. The Login, or
    None."""
    import json
    import os
    from datetime import datetime, timezone
    from urllib.parse import urlparse
    login = prepare(cf, a, a.index, log)
    if login is None:
        return None
    site, host = origin(a.url), urlparse(a.url).hostname
    stored = a.login_via != "stdin"  # a host app gets per-user storage of its own (its own spec)
    saved = load_map(host, login.account_id) if stored and not getattr(a, "fresh_map", False) else None
    m = blueprint(login.session, cf, site, saved=saved, log=log)
    if stored:
        save_map(m, host, login.account_id)
    os.makedirs(a.work, exist_ok=True)
    out = os.path.join(a.work, LOGGED_IN_MAP)
    with open(out, "w") as f:
        json.dump({**legacy_routes(m, site), "_behaviour": m, "_site": {
            "start": a.url, "explored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "menus": [],
            "popups": [], "blocked": None, "behind_login": []}}, f, indent=1)
    log(summary(m))
    ok, needed = fits(cf, a.prompt, m)
    if not ok:
        how = ask_how(asker(a.login_via), needed, m["account"]["state"])
        if how == "stop":
            login.forget()
            raise RuntimeError("login: the demo account can't show this; stopped as asked")
        if how == "account":
            login.forget()
            return with_login(a, cf, log)
    a.index, a.session = out, login.session
    return login
