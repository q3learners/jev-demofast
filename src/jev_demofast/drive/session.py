"""A browser tab plus the small operations both drivers need."""
import time
from urllib.parse import urljoin, urlparse

from ..browser.cdp import Browser, StalePage, fingerprint
from ..browser.elements import observed

__all__ = ["Session", "StalePage", "fingerprint", "origin", "site_cookies"]

# After an action, instead of a fixed pause: a page that doesn't react within IDLE_S is taken as unchanged (what the
# old 0.4 s pause assumed); one that does is read once its DOM has been quiet for QUIET_S. MAX_S caps pages that never
# stop changing (tickers, animations). Polled from Python: Chrome throttles timers in background tabs.
IDLE_S, QUIET_S, MAX_S, POLL_S = 0.4, 0.12, 2.0, 0.03
ARM = """(() => { window.__jdfWatch?.obs.disconnect();
  const w = {start: performance.now(), last: null};
  w.obs = new MutationObserver(() => { w.last = performance.now(); });
  w.obs.observe(document.documentElement, {subtree: true, childList: true, attributes: true, characterData: true});
  window.__jdfWatch = w; return true; })()"""
WATCH_STATE = """(() => { const w = window.__jdfWatch; if (!w) return null; const now = performance.now();
  return {since_start: now - w.start, since_last: w.last === null ? null : now - w.last}; })()"""
NEXT_FRAME = """new Promise(done => { setTimeout(done, 100);
  requestAnimationFrame(() => requestAnimationFrame(done)); })"""
# Flutter draws on its own surface: k12.tutorq.ai had no text and no controls to read until its accessibility layer
# was on. Clicking the layer's placeholder from JavaScript turns it on (about 1.5 s there); a reload turns it off.
FLUTTER_JS = "!!document.querySelector('flutter-view, flt-glass-pane')"
ENABLE_FLUTTER_JS = "(() => { const p = document.querySelector('flt-semantics-placeholder'); p?.click(); return !!p; })()"
SEMANTICS_READY_JS = "document.querySelectorAll('flt-semantics').length > 0"
FLUTTER_WAIT_S, FLUTTER_POLL_S = 3.0, 0.1


def origin(url):
    """scheme://host[:port]: storage belongs to an origin, so the port matters (localhost:3000)."""
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc.rsplit('@', 1)[-1]}"


def site_cookies(cookies, host):
    """This site's cookies: its own and its subdomains' (the site, as the on-site guard counts it), plus a parent
    domain's that it receives (.example.com)."""
    def sent(c):
        d = c["domain"].lstrip(".")
        return host == d or host.endswith("." + d) or d.endswith("." + host)
    return [c for c in cookies if sent(c)]


class Session:
    def __init__(self, url, fresh=False, isolated=False):
        self.start_url = url
        self.host = urlparse(url).hostname
        self.browser = Browser(url, isolated=isolated)
        self.is_flutter = False
        self.flutter_ready()
        if fresh:  # start logged out: clear this site's cookies and storage (isolated profile only)
            self.clear_site(url)
            self.browser.call("Page.navigate", url=url)
            self.wait_loaded()
        self.page = self.observe()

    def clear_site(self, url):
        """Delete only the cookies this site can read, and its origin's storage; other sites stay logged in."""
        try:
            cookies = self.browser.call("Storage.getCookies")["cookies"]
        except RuntimeError:  # older Chrome: the page-level equivalent
            cookies = self.browser.call("Network.getAllCookies")["cookies"]
        for c in site_cookies(cookies, self.host):
            self.browser.call("Network.deleteCookies", name=c["name"], domain=c["domain"], path=c["path"])
        self.browser.call("Storage.clearDataForOrigin", origin=origin(url), storageTypes="all")

    def wait_loaded(self, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.browser.evaluate("document.readyState") == "complete":
                    self.flutter_ready()
                    return
            except StalePage:
                pass
            time.sleep(0.05)

    def flutter_ready(self, timeout=FLUTTER_WAIT_S):
        """On a Flutter page, turn its accessibility layer on and wait for it. True once it's on; False for any other
        page (one check, nothing else) or if the layer never appeared."""
        try:
            self.is_flutter = self.browser.evaluate(FLUTTER_JS) is True
            if not self.is_flutter:
                return False
            self.browser.evaluate(ENABLE_FLUTTER_JS)
        except (StalePage, RuntimeError):
            return False
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.browser.evaluate(SEMANTICS_READY_JS) is True:
                    return True
            except (StalePage, RuntimeError):
                pass
            time.sleep(FLUTTER_POLL_S)
        return False

    def observe(self):
        self.page = self.browser.observe(screenshot=False)
        return self.page

    def elements(self):
        return observed(self.page)

    def refind(self, element):
        """The same DOM node in a fresh observation (labels and positions may have changed)."""
        self.observe()
        return next((e for e in self.elements() if e["node"] == element["node"]), element)

    def act(self, element, kind, text=None):
        element = self.refind(element)
        self.arm()
        self.browser.act(element["actions"][kind], self.page, text=text)

    def hover(self, element):
        """Move the mouse over an element (menus that open on hover)."""
        r = self.browser.evaluate(f"(() => {{ const e=window.__jevFast?.nodes.get({element['node']}); if (!e?.isConnected) "
                                  "return null; const r=e.getBoundingClientRect(); "
                                  "return {x: r.x, y: r.y, w: r.width, h: r.height}; })()")
        if not r:
            raise StalePage("The element to hover is gone. Observe again.")
        self.browser.call("Input.dispatchMouseEvent", type="mouseMoved", x=r["x"] + r["w"] / 2, y=r["y"] + r["h"] / 2)

    def arm(self):
        """Start watching the page for changes, so wait_for_page() sees what the next action does."""
        try:
            self.browser.evaluate(ARM)
        except (StalePage, RuntimeError):  # mid-navigation: wait_for_page treats the new document as navigated
            pass

    def wait_for_page(self, idle_s=IDLE_S, quiet_s=QUIET_S, max_s=MAX_S):
        """Wait for the page to finish reacting to the last action. Returns "unchanged", "settled", "navigated"
        (a new document loaded and went quiet) or "busy" (still changing at max_s)."""
        deadline, navigated = time.monotonic() + max_s, False
        while True:
            try:
                w = self.browser.evaluate(WATCH_STATE)
            except (StalePage, RuntimeError):
                w = None
            if w is None and not navigated:  # the action loaded a new document: let it load, then watch it
                navigated = True
                self.wait_loaded()
                self.arm()
                idle_s = quiet_s
                continue
            if w is not None:
                if w["since_last"] is None and w["since_start"] >= idle_s * 1000:
                    return "navigated" if navigated else "unchanged"
                if w["since_last"] is not None and w["since_last"] >= quiet_s * 1000:
                    return "navigated" if navigated else "settled"
            if time.monotonic() >= deadline:
                return "busy"
            time.sleep(POLL_S)

    def next_frame(self):
        """Wait until the page has painted (two animation frames; at most 0.1 s), e.g. after a scroll or an outline."""
        try:
            self.browser.evaluate(NEXT_FRAME, await_promise=True)
        except (StalePage, RuntimeError):
            pass

    def href(self, node):
        href = self.browser.evaluate(f"(() => {{ const n=window.__jevFast?.nodes.get({node}); "
                                     "const a=n?.closest('a'); return a ? a.getAttribute('href') : null; })()")
        return urljoin(self.page["url"], href) if href else None

    def settle(self, before_text, max_s=6.0, quiet_polls=3):
        """After a submit: wait until the page text has changed and then stayed the same for ~1.2 s.
        (A transient "Sending…" often lasts a second; judging it as the result was a measured mistake.)"""
        last, stable, waited = before_text, 0, 0.0
        while waited < max_s:
            time.sleep(0.4)
            waited += 0.4
            now = self.observe().get("text") or ""
            stable = stable + 1 if (now == last and now != before_text) else 0
            last = now
            if stable >= quiet_polls:
                break
        return self.page

    def full_text(self):
        return self.browser.evaluate("document.body.innerText") or self.page.get("text") or ""

    def type_secret_into_password(self, text):
        """Password inputs are hidden from observation by design; focus the visible one and type directly."""
        ok = self.browser.evaluate("(() => { const f=[...document.querySelectorAll('input[type=password]')]"
                                   ".find(e => e.offsetParent !== null); if (!f) return false; f.focus(); return true; })()")
        if ok:
            self.browser.call("Input.insertText", text=text)
        return bool(ok)

    def close(self):
        self.browser.close()
