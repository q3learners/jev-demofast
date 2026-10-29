"""--login: once the public site is mapped, ask for a demo account, sign in off camera, map the logged-in app, and
record it signed in. The answer lives only in a Login object for the run; every session it makes is a new isolated
browser context (the persistent profile never holds the founder's session) with the logged-in hazards on."""
from ..drive.session import Session, origin
from .ask import asker, question
from .forms import sign_in_forms
from .sign_in import sign_in

WHY = "Part of this site is behind a login. Which sign-in should the demo use?"
LOGGED_IN_MAP = "site-map-logged-in.json"  # in the run's work folder only: it holds the account's own data


class Login:
    def __init__(self, origin_, form, values, own_email, session_cls, log):
        self._origin, self._form, self._values = origin_, form, values
        self._own_email, self._session_cls, self._log = own_email, session_cls, log

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
            return cls(site, form, values, email, session, log)
        finally:
            s.close()

    def session(self, url, fresh=False, isolated=True):
        """A new isolated session, signed in, with the logged-in hazards on. Raises if the sign-in fails: a demo is
        never recorded logged out while claiming to be logged in."""
        s = self._session_cls(url, isolated=True)
        if self._values is None or sign_in(s, self._origin, self._form, self._values, log=self._log) != "signed in":
            s.close()
            raise RuntimeError("login: couldn't sign in for the recording")
        s.hazards, s.own_email = True, self._own_email
        return s

    def forget(self):
        self._values = self._own_email = None


def prepare(cf, a, index, log):
    from ..index import load as load_index
    return Login.prepare(cf, a.url, load_index(index), asker(a.login_via), log=log)


def explore(url, out, cf, session):
    from ..explore import explore as explore_site
    return explore_site(url, out=out, cf=cf, session=session)


def with_login(a, cf, log=print):
    """Sign in and map the logged-in app; point the run at that map and those sessions. The Login, or None."""
    import os
    login = prepare(cf, a, a.index, log)
    if login is None:
        return None
    os.makedirs(a.work, exist_ok=True)
    out = os.path.join(a.work, LOGGED_IN_MAP)
    explore(a.url, out=out, cf=cf, session=login.session)
    a.index, a.session = out, login.session
    return login
