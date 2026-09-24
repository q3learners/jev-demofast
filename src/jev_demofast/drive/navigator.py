"""Navigator: an LLM plans the route once; each step's element is picked (keyword / Jev), checked, recorded.

Works on any site without an app index. Checks around every click:
  lookahead  the click must reveal the next target (or a later one, then skip ahead); otherwise undo it
  reveal     a target hidden in a menu → Jev picks the menu to open, then the step is retried
  guards     same site only; no sign-up / third-party login / log-out / delete; secrets typed, never shown
  verify     the plan's finish text (if any) must appear; information steps read the whole page
"""
import json
import time

from ..record.recorder import Recorder
from .guards import DryRunStop, blocked, fill_text, has_secret, on_site, would_change
from .pick import Picker
from .plan import extract, make_plan
from .session import Session, StalePage, fingerprint


def run(cf, url, goal, out=None, picker="jev", fresh=False, max_steps=25, replan=True, page_maps=False,
        blur_typed=True, dry_run=False, log=print):
    t0 = time.perf_counter()
    ms = lambda: round((time.perf_counter() - t0) * 1000)
    s = Session(url, fresh=fresh)
    rec = Recorder(out, s, page_maps=page_maps, blur_typed=blur_typed)
    log = rec.tee(log)
    pick = Picker(cf, picker)
    result = {"goal": goal, "verified": False, "items": [], "dry_run": dry_run}
    try:
        rec.snap(2.0)
        rec.commit({"do": "open"}, s.page)
        plan = make_plan(cf, goal, s.page)
        steps, done_text = plan["steps"], plan["done_text"]
        log(f"{ms():>6} ms  plan: " + " → ".join(f"{st['do']} {st['target']!r}" for st in steps))
        i, actions, replans, reveals, failed, done = 0, 0, 0, {}, set(), []
        while i < len(steps) and actions < max_steps:
            step, page = steps[i], s.page
            if step["do"] == "read":
                items = extract(cf, step["target"], page["url"], s.full_text())
                result["items"] = items
                if items:  # scroll the first item into view for the frame
                    s.browser.evaluate("(t => { const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); "
                                       "let n; while ((n=w.nextNode())) if (n.textContent.includes(t)) "
                                       "{ n.parentElement.scrollIntoView({block:'start'}); window.scrollBy(0,-80); return; } })"
                                       f"({json.dumps(items[0][:40])})")
                    time.sleep(0.3)
                s.observe()
                rec.snap(3.0)
                rec.commit({"do": "read", "target": step["target"], "items": items}, s.page)
                log(f"{ms():>6} ms  read {step['target']!r}: {items}")
                i += 1
                continue
            kind = "fill" if step["do"] == "fill" else "click"
            if kind == "fill" and has_secret(step.get("value")):
                if s.type_secret_into_password(fill_text(step["value"])):
                    time.sleep(0.2)
                    s.observe()
                    rec.snap(1.2)
                    rec.commit({"do": "fill", "target": step["target"], "chose": "password field"}, s.page)
                    log(f"{ms():>6} ms  fill {step['target']!r} (typed into the password field; value never shown)")
                    actions += 1
                    i += 1
                    continue
            els = [e for e in s.elements() if kind in e["actions"] and (page["url"], e["node"]) not in failed
                   and not blocked(e["label"], unless=step["target"])]
            chosen, conf, how = pick.pick(step["target"], kind, els, page, goal)
            if chosen is None:
                opener = pick.reveal(s.elements(), step["target"], page, goal, failed) if reveals.get(i, 0) < 2 else None
                if opener is not None:
                    reveals[i] = reveals.get(i, 0) + 1
                    rec.snap(1.2, node=opener["node"])
                    s.act(opener, "click")
                    time.sleep(0.5)
                    s.observe()
                    rec.snap(0.8)
                    rec.commit({"do": "click", "target": f"open the menu holding {step['target']}",
                                "chose": opener["label"][:80]}, s.page)
                    log(f"{ms():>6} ms  reveal {step['target']!r} → opened {opener['label'][:40]!r}")
                    continue
                if replan and replans < 2:
                    replans += 1
                    plan = make_plan(cf, goal, page, done)
                    steps, i = plan["steps"], 0
                    done_text = plan["done_text"] or done_text
                    log(f"{ms():>6} ms  re-plan: " + " → ".join(f"{st['do']} {st['target']!r}" for st in steps))
                    continue
                log(f"{ms():>6} ms  STUCK: nothing on the page means {step['target']!r}")
                break
            prev_url = page["url"]
            if dry_run and kind == "click" and would_change(chosen):
                rec.would_click(chosen["node"], chosen["label"], page)
                raise DryRunStop(chosen["label"][:60])
            rec.snap(1.3, node=chosen["node"])
            before = fingerprint(s.observe())
            try:
                s.act(chosen, kind, text=fill_text(step.get("value")) if kind == "fill" else None)
            except StalePage:
                rec.discard()
                s.observe()
                continue
            if kind == "fill":
                rec.blur(chosen["node"])
            time.sleep(0.4)
            page = s.observe()
            changed = fingerprint(page) != before
            rec.snap(1.0)
            actions += 1
            log(f"{ms():>6} ms  {kind} {step['target']!r} → {chosen['label'][:40]!r} ({how} {conf:.2f})"
                f"{'' if changed else ' [no change]'}")
            if not on_site(page["url"], s.host):
                log(f"{ms():>6} ms  GUARD: left {s.host}; stopped")
                rec.discard()
                break
            last_action = all(st["do"] == "read" for st in steps[i + 1:])  # finish text only counts at the end
            if done_text and last_action and done_text in (page.get("text") or "").lower():
                rec.commit({"do": kind, "target": step["target"], "chose": chosen["label"][:80]}, page)
                result["verified"] = True
                log(f"{ms():>6} ms  VERIFIED: page shows {done_text!r}")
                reads = [st for st in steps[i + 1:] if st["do"] == "read"]
                if reads:  # destination reached, but information was asked for
                    steps, i, done_text = reads, 0, ""
                    continue
                break
            if kind == "click" and not changed:
                failed.add((prev_url, chosen["node"]))
                rec.discard()
                continue
            nxt = i + 1
            if kind == "click":
                reached = pick.lookahead(s, steps, i, goal)
                if reached is None:
                    log(f"         lookahead: nothing from the next steps appeared; going back")
                    failed.add((prev_url, chosen["node"]))
                    s.browser.call("Page.navigate", url=prev_url) if page["url"] != prev_url else s.browser.call("Page.reload")
                    s.wait_loaded()
                    s.observe()
                    rec.discard()
                    continue
                if reached > i + 1:
                    log(f"         lookahead: {steps[reached]['target']!r} is already here; skipping ahead")
                nxt = reached
            rec.commit({"do": kind, "target": step["target"], "chose": chosen["label"][:80]}, page)
            done.append(f"{kind} {step['target']!r}")
            i = nxt
        if i >= len(steps) and not done_text and steps and steps[-1]["do"] == "read":
            result["verified"] = bool(result["items"])  # an information goal is done when its reads return data
        if i >= len(steps) and done_text and not result["verified"]:
            s.settle(s.page.get("text") or "", max_s=6)
            result["verified"] = done_text in (s.page.get("text") or "").lower()
            log(f"{ms():>6} ms  {'VERIFIED' if result['verified'] else 'UNVERIFIED'}: finish text {done_text!r}")
    except DryRunStop as stop:
        result["would_click"] = str(stop)
        log(f"{ms():>6} ms  DRY RUN: stopped before {str(stop)!r}; nothing was changed")
    finally:
        rec.save(goal, cf.decisions)
        s.close()
    result.update(seconds=round((time.perf_counter() - t0), 1), **cf.stats)
    log(f"done in {result['seconds']} s | Jev {cf.stats['jev_calls']} calls, {cf.stats['jev_seconds']:.1f} s | "
        f"LLM {cf.stats['llm_calls']} calls, {cf.stats['llm_seconds']:.1f} s")
    return result
