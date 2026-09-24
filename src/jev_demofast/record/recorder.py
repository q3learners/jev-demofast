"""Records a run as frames.json: [{path, hold, segment, pending}] plus actions.json for narration.

Frames of a step are held back until the step is accepted, so undone attempts never reach the video.
Typed values are blurred on screen before any frame is taken (disable with blur_typed=False).
"""
import base64
import json
import os
import time


class Recorder:
    def __init__(self, out, session, page_maps=False, blur_typed=True):
        self.out = os.path.abspath(out) if out else None
        self.s = session
        self.page_maps = page_maps
        self.blur_typed = blur_typed
        self.frames, self.pending, self.actions = [], [], []
        if self.out:
            os.makedirs(os.path.join(self.out, "frames"), exist_ok=True)

    def snap(self, hold, node=None):
        """Screenshot the viewport; with `node`, outline that element (scrolled into view) for this frame."""
        if not self.out:
            return
        if node is not None:
            self.s.browser.evaluate(f"(() => {{ const e=window.__jevFast?.nodes.get({node}); if (!e) return; "
                                    "e.scrollIntoView({block:'center'}); e.style.outline='3px solid #f59e0b'; "
                                    "e.style.outlineOffset='3px'; })()")
            time.sleep(0.12)
        data = self.s.browser.call("Page.captureScreenshot", format="png")["data"]
        if node is not None:
            self.s.browser.evaluate(f"(() => {{ const e=window.__jevFast?.nodes.get({node}); "
                                    "if (e) { e.style.outline=''; e.style.outlineOffset=''; } })()")
        self.pending.append((data, hold))

    def blur(self, node):
        """Blur a field the tool typed into, so the value never appears in a frame."""
        if self.blur_typed:
            self.s.browser.evaluate(f"(() => {{ const e=window.__jevFast?.nodes.get({node}); "
                                    "if (e) e.style.filter='blur(6px)'; })()")

    def commit(self, action, page=None):
        """Keep the pending frames as one segment (one narration line later)."""
        if not self.out:
            return
        segment = f"{len(self.actions):02d}"
        for data, hold in self.pending:
            path = os.path.join(self.out, "frames", f"f{len(self.frames):04d}.png")
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
            self.frames.append({"path": path, "hold": hold, "segment": segment, "pending": False})
        self.pending = []
        if page is not None:
            action = {**action, "url": page["url"], "screen_title": page.get("title", ""),
                      "screen_text": " ".join((page.get("text") or "").split())[:1500],
                      **(self.page_map(segment) if self.page_maps else {})}
        self.actions.append({"segment": segment, **action})

    def discard(self):
        self.pending = []

    def page_map(self, segment):
        """Full-page screenshot + text-block positions, so the camera can pan to what narration mentions."""
        try:
            info = self.s.browser.evaluate("""(() => {
              const seen = new Set(), blocks = [];
              for (const e of document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,a,button,label,td,th,dt,dd,span,div')) {
                const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
                if (!own) continue;
                const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();
                const r = e.getBoundingClientRect();
                if (t.length < 2 || t.length > 240 || !r.width || !r.height || seen.has(t)) continue;
                seen.add(t);
                blocks.push({text: t, y: Math.round(r.top + scrollY), h: Math.round(r.height)});
                if (blocks.length >= 200) break;
              }
              return {scroll_y: Math.round(scrollY), vw: innerWidth, vh: innerHeight,
                      page_h: Math.min(document.documentElement.scrollHeight, 8000), blocks};
            })()""")
            shot = self.s.browser.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                                       clip={"x": 0, "y": 0, "width": info["vw"], "height": info["page_h"], "scale": 1})
            self.s.browser.evaluate(f"window.scrollTo(0, {info['scroll_y']})")
            path = os.path.join(self.out, "frames", f"page-{segment}.png")
            with open(path, "wb") as f:
                f.write(base64.b64decode(shot["data"]))
            return {"page_shot": path, **info}
        except Exception as error:  # a page map is optional; never fail the run for it
            print(f"  (no page map for segment {segment}: {error})")
            return {}

    def save(self, goal):
        if not self.out:
            return
        with open(os.path.join(self.out, "frames.json"), "w") as f:
            json.dump(self.frames, f, indent=1)
        with open(os.path.join(self.out, "actions.json"), "w") as f:
            json.dump({"goal": goal, "actions": self.actions}, f, indent=1)
        print(f"recorded {len(self.frames)} frames in {len(self.actions)} segments → {self.out}")
