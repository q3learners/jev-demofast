"""Jobs: the product's tasks as proven paths, made from what the walk did. Proven when the result showed on screen;
partial (with where and why it stopped) when a refusal or a one-time step cut it short; one-time when it ran on an
account partway through setup; named in the product's words by the model, else by its first control."""
from fakeapp import FakeApp
from test_behaviour_forms import Model

from jev_demofast.behaviour import crawl as crawl_mod
from jev_demofast.behaviour import jobs


class Named(Model):
    def __init__(self, names=None, **k):
        super().__init__(**k)
        self.names = names

    def chat_json(self, model, system, context, extra=None):
        if system == jobs.NAME_JOBS:
            if self.names is None:
                raise RuntimeError("model down")
            return {"names": self.names[:len(context["jobs"])]}
        return super().chat_json(model, system, context, extra)


def walk(app, cf):
    return crawl_mod.crawl(app.restart, cf, "https://k12.test", log=lambda m: None, now="t1")


def controls(m, job):
    return [m["actions"][i]["control"] for i in job["steps"]]


def test_add_a_kid_is_a_proven_repeatable_job():
    m = walk(FakeApp(), Named(names=["Add a kid"]))
    job = next(j for j in m["jobs"] if j["name"] == "Add a kid")
    assert controls(m, job) == ["Add a kid", "First name", "Age", "Continue", "Add", "Login ID", "Next", "Grade",
                                "Next"]
    assert job["proven"] and job["repeatable"] and job["needs"] == "set up" and "Maya" in job["result"]


def test_partway_setup_is_a_partial_one_time_job():
    m = walk(FakeApp(state="partway"), Named(names=["Set up your kids"], state="partway", finishes=0.9))
    job = m["jobs"][0]
    assert not job["proven"] and job["stopped"] == "seen, not finished"
    assert not job["repeatable"] and job["needs"] == "partway: Your kids"


def test_unnamed_job_falls_back():
    m = walk(FakeApp(), Named(names=None))
    assert any(j["name"] == "Add a kid" for j in m["jobs"])


def test_a_job_through_a_gone_screen_is_not_proven():
    m = walk(FakeApp(), Named(names=["Add a kid"]))
    login = next(k for k in m["screens"] if k.startswith("/kids/setup/login"))
    m["screens"][login]["gone"] = True
    assert not next(j for j in jobs.find(Named(names=["Add a kid"]), m) if j["name"] == "Add a kid")["proven"]


def again(app, saved, cf=None):
    app.pressed.clear()
    return crawl_mod.crawl(app.restart, cf or Named(names=["Add a kid"]), "https://k12.test", saved=saved,
                           log=lambda m: None, now="t2")


def test_an_unchanged_map_is_not_walked_again():
    app = FakeApp()
    m = again(app, walk(app, Named(names=["Add a kid"])))
    assert set(app.pressed) <= set(app.tabs)
    assert m["screens"]["/kids/ava"]["last_seen"] == "t2"


def test_a_new_section_is_walked():
    app = FakeApp()
    saved = walk(app, Named(names=["Add a kid"]))
    app.tabs.append("Schedule")
    m = again(app, saved)
    assert "Schedule" in m["account"]["sections"] and "/schedule" in m["screens"] and "Add a kid" not in app.pressed


def test_a_changed_account_state_walks_everything():
    app = FakeApp()
    saved = walk(app, Named(names=["Add a kid"]))
    saved["account"]["state"] = "partway: Your kids"
    again(app, saved)
    assert "Add a kid" in app.pressed


def test_jobs_survive_a_learning_run():
    """A job's steps are indexes into the actions: a merge must keep them pointing at the same actions."""
    app = FakeApp()
    saved = walk(app, Named(names=["Add a kid"]))
    app.tabs.append("Schedule")
    m = again(app, saved)
    job = next(j for j in m["jobs"] if j["name"] == "Add a kid")
    assert job["proven"] and controls(m, job)[:4] == ["Add a kid", "First name", "Age", "Continue"]
