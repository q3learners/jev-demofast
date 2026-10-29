"""Jobs: the product's tasks as paths mapping proved, made from the chains forms.handle recorded. A job is proven
when its result showed on screen (one sighting is enough); a path cut short by a refusal or a one-time step is kept as
partial, with where and why it stopped. Named by the model in the product's words, else by its first control."""
STOPPED = ("refused", "seen, not finished")
SKIPPED = ("not pressed", "refused: no safe way")
NAME_JOBS = """Each item is a task someone did in a web app: the controls used, in order, and what it ended with. Name
each task the way the product would, in a few words ("Add a kid", "Ask the tutor a question"), not as clicks. Reply
with JSON only: {"names": ["<name>", ...]} in the same order."""


def _landing(outcome):
    for head in ("→ ", "dialog "):
        if outcome.startswith(head):
            return outcome[len(head):]
    return None


def _job(m, chain):
    acts = m["actions"]
    steps = [i for i in chain if acts[i]["outcome"] not in SKIPPED]
    if not steps:
        return None
    first = acts[steps[0]]["screen"]
    opener = next((i for i, a in enumerate(acts) if a["outcome"] == f"→ {first}" and i not in steps), None)
    if opener is not None:
        steps.insert(0, opener)
    typed = [v for i in steps for v in (acts[i].get("values") or {}).values()]
    last = acts[steps[-1]]
    stopped = last["outcome"] if last["outcome"].startswith(STOPPED) else None
    end = m["screens"].get(_landing(last["outcome"]) or "", {})
    result = next((t for t in end.get("texts", []) for v in typed if v and v in t), "")
    added = next((a["outcome"] for a in (acts[i] for i in steps) if a["outcome"].startswith("added '")), None)
    result = result or (f"{added[7:-1]} added" if added else "")
    screens = {acts[i]["screen"] for i in steps} | {_landing(acts[i]["outcome"]) for i in steps} - {None}
    gone = any(m["screens"].get(k, {}).get("gone") for k in screens)
    state = m["account"]["state"] or "unknown"
    return {"name": acts[steps[0]]["control"], "steps": steps, "result": result, "repeatable": state == "set up",
            "needs": state, "proven": bool(result) and not stopped and not gone,
            **({"stopped": stopped} if stopped else {})}


def find(cf, m, log=print):
    found = [j for j in (_job(m, c) for c in m.get("chains", [])) if j]
    if not found:
        return []
    try:
        names = cf.chat_json(cf.s.read_model, NAME_JOBS, {"jobs": [
            {"controls": [m["actions"][i]["control"] for i in j["steps"]], "ended_with": j["result"]}
            for j in found]}).get("names") or []
    except Exception as err:
        log(f"blueprint: jobs not named ({type(err).__name__}); each is named by its first control")
        names = []
    for job, name in zip(found, names):
        if isinstance(name, str) and name.strip():
            job["name"] = name.strip()
    return found
