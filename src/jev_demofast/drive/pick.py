"""Choosing elements: keyword matching, Jev, or both.

Modes:
  keyword  plain word-stem matching only (no model).
  hybrid   keywords decide when every word of the target matches; otherwise Jev decides (or reports not found).
  jev      Jev decides every pick (from the keyword shortlist, or the whole page when nothing matches).
"""
import time

from ..browser.elements import describe, relevance, shortlist, words
from .guards import blocked

CONFIDENT = 0.5


class Picker:
    def __init__(self, cf, mode="jev"):
        if mode not in ("keyword", "hybrid", "jev"):
            raise ValueError(f"unknown picker mode {mode!r}")
        self.cf, self.mode = cf, mode

    def _state(self, page, goal):
        return {"goal": goal, "page": page.get("title", ""), "url": page["url"]}

    def semantic(self, els, target, kind, page, goal, limit=80):
        """Jev: which element does the same thing as `target`? 'none' allowed; below CONFIDENT counts as none."""
        els = els[:limit]
        if not els or self.mode == "keyword":
            return None, 0.0
        key, conf = self.cf.choose(f"Which element does the same thing as '{target}' ({kind})? "
                                   "Labels may use different words with the same meaning.",
                                   {str(e["node"]): describe(e) for e in els}, self._state(page, goal), allow_none=True)
        if key is None or conf < CONFIDENT:
            return None, conf
        return next(e for e in els if str(e["node"]) == key), conf

    def pick(self, target, kind, els, page, goal):
        """Returns (element or None, confidence, how)."""
        if not els:
            return None, 0.0, "none"
        ranked = shortlist(els, target, 8)
        top = max(ranked, key=lambda e: relevance(e, target))
        best = relevance(top, target)
        full = best >= max(1, len(words(target)))
        if self.mode == "keyword":
            return (top, 1.0, "keyword") if best > 0 else (None, 0.0, "none")
        if self.mode == "hybrid":
            if full:
                return top, 1.0, "keyword"
            chosen, conf = self.semantic(els, target, kind, page, goal)
            return (chosen, conf, "jev") if chosen is not None else (None, conf, "none")
        # jev: Jev decides every pick. A full keyword match narrows the options to the shortlist; a partial or
        # descriptive target ("first trending repository link") gets the whole page, since sharing one word
        # with a tab or nav link says little.
        if full:
            key, conf = self.cf.choose(f"Goal: {goal}. Next step: {kind} '{target}'. Which element is it?",
                                       {str(e["node"]): describe(e) for e in ranked}, self._state(page, goal))
            return next(e for e in ranked if str(e["node"]) == key), conf, "jev"
        # Jev unsure and only a partial keyword match: report "not found" (→ reveal, then re-plan with the real
        # labels) rather than click something that merely shares a word with the target.
        chosen, conf = self.semantic(els, target, kind, page, goal)
        return (chosen, conf, "jev") if chosen is not None else (None, conf, "none")

    def reveal(self, els, target, page, goal, failed=()):
        """Jev: which menu, dropdown, filter or tab would reveal a target that isn't visible?"""
        if self.mode == "keyword":
            return None
        ctrls = [e for e in els if "click" in e["actions"] and e["role"] in ("button", "combobox", "tab")
                 and not blocked(e["label"]) and (page["url"], e["node"]) not in failed][:30]
        if not ctrls:
            return None
        key, conf = self.cf.choose(f"'{target}' is not visible on this page. Which control (a menu, dropdown, "
                                   "filter or tab) would you open to find it?",
                                   {str(e["node"]): describe(e) for e in ctrls}, self._state(page, goal), allow_none=True)
        if key is None or conf < CONFIDENT:
            return None
        return next(e for e in ctrls if str(e["node"]) == key)

    def lookahead(self, session, steps, i, goal, polls=6):
        """After a click at step i: index of the first upcoming step whose target is now visible, or None.
        The next step may match loosely (any word, or Jev); skipping further ahead needs every word to match,
        because plans guess hops on pages they haven't seen and a loose skip loses the user's intent."""
        ahead = [j for j in range(i + 1, min(i + 4, len(steps))) if steps[j]["do"] != "read"]
        if not ahead or ahead[0] != i + 1:
            return i + 1
        for attempt in range(polls):
            els = session.elements()
            # 1. exact evidence first, for every upcoming step: a later step fully matching means skip ahead
            for j in ahead:
                target, jkind = steps[j]["target"], "fill" if steps[j]["do"] == "fill" else "click"
                need = 1 if j == i + 1 else max(1, len(words(target)))
                if any(relevance(e, target) >= need for e in els if jkind in e["actions"]):
                    return j
            # 2. then a judgment for the immediate next step only: a synonym on screen, or one menu-open away
            if self.mode != "keyword":
                nxt = steps[i + 1]
                nkind = "fill" if nxt["do"] == "fill" else "click"
                if self.semantic([e for e in els if nkind in e["actions"]], nxt["target"], nkind,
                                 session.page, goal)[0] is not None:
                    return i + 1
                if self.reveal(els, nxt["target"], session.page, goal) is not None:
                    return i + 1
            if attempt < polls - 1:
                time.sleep(0.5)
                session.observe()
        return None
