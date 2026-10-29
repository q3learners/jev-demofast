"""After mapping: a readable summary of the blueprint, whether this account can show the demo asked for, and when it
can't, the founder is asked how to go on (record what it can show, use another account, or stop; no answer stops)."""
from jev_demofast.behaviour import fit
from jev_demofast.behaviour.model import add_action, empty


def blueprint(state="set up"):
    m = empty()
    m["account"] = {"state": state, "sections": ["Home", "Kids"]}
    steps = [add_action(m, "/kids", "Add a kid", "click", "→ /kids/new", "t1"),
             add_action(m, "/kids/new", "First name", "fill", "no change", "t1", values={"First name": "Maya"}),
             add_action(m, "/kids/new", "Add", "click", "added 'Maya'", "t1")]
    m["jobs"] = [{"name": "Add a kid", "steps": steps, "result": "Maya added", "repeatable": True, "needs": "set up",
                  "proven": True}]
    m["left"] = ["/subjects: 38 more items"]
    return m


class Picks:
    def __init__(self, key, conf=0.9):
        self.key, self.conf = key, conf

    def choose(self, instructions, options, state, allow_none=False):
        return self.key, self.conf


def test_summary_lists_state_sections_jobs_and_what_was_left():
    text = fit.summary(blueprint())
    assert "set up" in text and "Home, Kids" in text and "38 more items" in text
    assert "Add a kid: Add a kid → First name → Add (proven)" in text


def test_a_partway_account_does_not_fit_an_in_app_add():
    m = blueprint()
    m["account"]["state"] = "partway: Your kids"
    assert fit.fits(Picks("0"), "Show parents how to add a kid", m) == (False, "set up")


def test_a_matching_job_on_the_right_account_fits():
    assert fit.fits(Picks("0"), "Show parents how to add a kid", blueprint()) == (True, None)


def test_no_matching_job_fits():
    assert fit.fits(Picks(None, 0.0), "Show the pricing page", blueprint()) == (True, None)
    assert fit.fits(Picks("0", 0.3), "Show the pricing page", blueprint()) == (True, None)


def test_no_answer_is_stop():
    asked = []
    assert fit.ask_how(lambda q: asked.append(q), "set up", "partway: Your kids") == "stop"
    assert [c["id"] for c in asked[0]["choices"]] == ["record", "account", "stop"]
    assert "set up" in asked[0]["why"] and "partway: Your kids" in asked[0]["why"]


def test_the_founders_choice_is_returned():
    assert fit.ask_how(lambda q: {"id": q["id"], "choice": "record"}, "set up", "partway: Your kids") == "record"
