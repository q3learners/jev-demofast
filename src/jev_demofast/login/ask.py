"""The login question. The run asks for a demo account once it knows the site's sign-in forms; the founder picks one
and fills its fields, or skips. In a terminal secrets are read with getpass; a host process (the hosted app) gets one
`ask: {json}` log line and answers with one JSON line on stdin. The answer is never echoed, logged or written."""
import getpass as _getpass
import json
import re
import select
import sys

from ..drive.guards import PASSWORD_NAME

ASK_TIMEOUT_S = 300  # the founder may need to find the demo account; no answer by then is a skip


def secret_field(label, input_type=""):
    """A password input, or a label that names a secret (Password, Passcode, PIN)."""
    return input_type == "password" or bool(PASSWORD_NAME.search(re.sub(r"\W+", "_", label or "").strip("_")))


def question(forms, why, retry=None, qid="q1"):
    """{"id", "why", "forms": [{"id", "title", "page", "fields": [{"name", "label", "secret"}]}], "retry"}."""
    return {"id": qid, "why": why, "forms": forms, "retry": retry}


def _valid(q, answer):
    if not isinstance(answer, dict) or answer.get("id") != q["id"] or answer.get("skip"):
        return None
    form = next((f for f in q["forms"] if f["id"] == answer.get("form")), None)
    values = answer.get("values")
    if form is None or not isinstance(values, dict) or not all(isinstance(values.get(f["name"]), str)
                                                                for f in form["fields"]):
        return None
    return {"id": q["id"], "form": form["id"], "values": {f["name"]: values[f["name"]] for f in form["fields"]}}


def ask_terminal(q, input=input, getpass=_getpass.getpass, out=print):
    """Ask in the terminal. Returns the answer, or None to skip."""
    out(q["why"] + (f"\n{q['retry']}" if q.get("retry") else ""))
    forms = q["forms"]
    if len(forms) == 1:
        form = forms[0]
    else:
        for i, f in enumerate(forms, 1):
            out(f"  {i}. {f['title']} ({', '.join(x['label'] for x in f['fields'])})")
        choice = input(f"Which one (1-{len(forms)}, or s to skip)? ").strip().lower()
        if not choice.isdigit() or not 1 <= int(choice) <= len(forms):
            return None
        form = forms[int(choice) - 1]
    values = {}
    for field in form["fields"]:
        read = getpass if field["secret"] else input
        values[field["name"]] = read(f"{field['label']}: ")
    return _valid(q, {"id": q["id"], "form": form["id"], "values": values})


def _ready(stream, timeout):
    return bool(select.select([stream], [], [], timeout)[0])


def ask_stdin(q, stream=None, log=print, timeout=ASK_TIMEOUT_S):
    """Ask a host process: one `ask:` log line out, one JSON line in. Returns the answer, or None to skip."""
    stream = stream or sys.stdin
    log("ask: " + json.dumps(q))
    sys.stdout.flush()  # under a host's pipe stdout is block-buffered: the question must reach it now
    if not _ready(stream, timeout):
        return None
    try:
        return _valid(q, json.loads(stream.readline() or "null"))
    except ValueError:  # garbled: a skip, and the line is never echoed
        return None


def asker(via):
    """The ask function for --login-via: "terminal" or "stdin"."""
    return {"terminal": ask_terminal, "stdin": ask_stdin}[via]
