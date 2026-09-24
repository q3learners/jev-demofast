"""A failed flow must not be reported as a success, and the narrator must be told it failed."""
import json

from jev_demofast.drive import jev_drive
from jev_demofast.narrate import script


def test_the_narrator_sees_a_steps_outcome(tmp_path):
    (tmp_path / "actions.json").write_text(json.dumps({"goal": "invite someone", "actions": [
        {"segment": "00", "do": "click", "target": "Invite Member", "screen_text": "User is already a member of this team",
         "outcome": "not confirmed: the page did not show success"}]}))
    seen = {}

    class FakeCf:
        class s:
            script_model, script_extra = "m", {}
        def chat(self, model, system, user, extra=None):
            seen["system"], seen["context"] = system, json.loads(user)
            return "00 | Invite | We tried to invite them, but the page says they're already a member."

    script.write(FakeCf(), str(tmp_path))
    assert seen["context"]["segments"][0]["outcome"].startswith("not confirmed")
    assert "never describe a step as successful" in seen["system"]


def test_done_is_verified_only_when_the_screen_confirms_it():
    class FakeCf:
        def __init__(self, confirm): self.confirm = confirm
        def yes(self, instructions, state, true="yes", false="no"): return self.confirm
    page = {"url": "http://app/dashboard", "text": "User is already a member of this team"}
    assert jev_drive.confirmed(FakeCf(0.25), "invite someone", page) is False
    assert jev_drive.confirmed(FakeCf(0.82), "invite someone", page) is True
