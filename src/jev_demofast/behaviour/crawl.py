"""The walk through the signed-in app that writes the blueprint: the account's state, every section, every control
mapping may press, back to where it started each time, within budget. Every press goes through Session.act, so the
login branch's safety rules (hazard labels, the money judge, the own-email rule) apply unchanged."""

ACCOUNT = """You see the first screen of a web app right after signing in. Is the account still partway through a setup
or onboarding flow it hasn't finished (a step list with a "current step", a "finish setting up" screen)? Reply with
JSON only: {"setup_unfinished": true|false, "current_step": "<the current step's name as shown, or empty>"}."""


def account_state(cf, screen, log=print):
    """"set up", "partway: <step>", or "unknown" when the model can't say (never guessed)."""
    try:
        ans = cf.chat_json(cf.s.read_model, ACCOUNT, {"texts": screen.get("texts", []),
                                                      "controls": screen.get("controls", [])[:30]})
    except Exception as err:
        log(f"blueprint: couldn't read the account's state ({type(err).__name__})")
        return "unknown"
    if not isinstance(ans, dict) or "setup_unfinished" not in ans:
        return "unknown"
    step = str(ans.get("current_step") or "").strip()
    return f"partway: {step}" if ans["setup_unfinished"] else "set up"


