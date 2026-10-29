"""After mapping: the blueprint in a few readable lines, whether this account can show the demo asked for, and when
it can't, asking the founder how to go on. A demo the account can't support is caught before recording, not on camera."""
from ..drive.check import CONFIDENT
from ..login.ask import choice_question

CHOICES = [("record", "Record what this account can show"), ("account", "Use a different account"), ("stop", "Stop")]
NEEDS_Q = "Which of these tasks does the demo need to show? 'none' if none of them."


def summary(m):
    acts = m["actions"]
    lines = ["Product blueprint:", f"  account: {m['account']['state']}",
             f"  sections: {', '.join(m['account']['sections']) or '(none)'}"]
    for job in m["jobs"]:
        how = "proven" if job["proven"] else f"stopped: {job['stopped']}" if job.get("stopped") else "not proven"
        steps = " → ".join(acts[i]["control"] for i in job["steps"])
        lines.append(f"  job {job['name']}: {steps} ({how})")
    lines += [f"  left: {item}" for item in m["left"]]
    return "\n".join(lines)


def fits(cf, sentence, m):
    """(True, None) when no job matches clearly or the matching job's account state is this account's; else
    (False, the state the job needs)."""
    if not m["jobs"]:
        return True, None
    try:
        key, conf = cf.choose(NEEDS_Q, {str(i): f"{j['name']}: {j['result']}" for i, j in enumerate(m["jobs"])},
                              {"demo": sentence}, allow_none=True)
    except Exception:
        return True, None
    if key is None or conf < CONFIDENT:
        return True, None
    job = m["jobs"][int(key)]
    return (True, None) if job["needs"] == m["account"]["state"] else (False, job["needs"])


def ask_how(ask, needed, state):
    """"record", "account" or "stop"; no answer stops."""
    why = (f"This demo needs an account that is {needed}; this one is {state}. How should the demo go on?")
    answer = ask(choice_question(why, CHOICES, qid="q4"))
    return answer["choice"] if answer else "stop"
