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
