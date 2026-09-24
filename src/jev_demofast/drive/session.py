"""A browser tab plus the small operations both drivers need."""
import time
from urllib.parse import urljoin, urlparse

from ..browser.cdp import Browser, StalePage, fingerprint
from ..browser.elements import observed

__all__ = ["Session", "StalePage", "fingerprint"]


class Session:
    def __init__(self, url, fresh=False):
        self.start_url = url
        self.host = urlparse(url).hostname
        self.browser = Browser(url)
        if fresh:  # start logged out: clear this site's cookies and storage (isolated profile only)
            self.browser.call("Network.clearBrowserCookies")
            self.browser.call("Storage.clearDataForOrigin", origin=f"{urlparse(url).scheme}://{self.host}",
                              storageTypes="all")
            self.browser.call("Page.navigate", url=url)
            self.wait_loaded()
        self.page = self.observe()

    def wait_loaded(self, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.browser.evaluate("document.readyState") == "complete":
                    return
            except StalePage:
                pass
            time.sleep(0.05)

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
        self.browser.act(element["actions"][kind], self.page, text=text)

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
