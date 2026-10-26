import pytest

from jev_demofast.cloudflare import Cloudflare
from jev_demofast.config import ConfigError, load

CF = {"CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "cf-token"}


def env(monkeypatch, **values):
    for k in ("JDF_LLM_PROVIDER", "NEBIUS_API_KEY", "JDF_NEBIUS_MODEL", "JDF_PLAN_MODEL", "JDF_PLAN_EXTRA",
              "JDF_SCRIPT_EXTRA"):
        monkeypatch.delenv(k, raising=False)
    for k, v in {**CF, **values}.items():
        monkeypatch.setenv(k, v)


def test_default_provider_is_cloudflare(monkeypatch):
    env(monkeypatch)
    s = load()
    assert s.llm_provider == "cloudflare"
    assert s.llm_url == "https://api.cloudflare.com/client/v4/accounts/acct/ai/v1/chat/completions"
    assert s.llm_token == "cf-token" and s.plan_model.startswith("@cf/")


def test_nebius_sends_language_model_calls_to_token_factory_with_nemotron(monkeypatch):
    env(monkeypatch, JDF_LLM_PROVIDER="nebius", NEBIUS_API_KEY="nb-key", JDF_NEBIUS_MODEL="nvidia/some-nemotron")
    s = load()
    assert s.llm_url == "https://api.tokenfactory.nebius.com/v1/chat/completions" and s.llm_token == "nb-key"
    assert s.plan_model == s.read_model == s.script_model == "nvidia/some-nemotron"
    assert s.plan_extra == {} and s.script_extra == {}          # GLM's reasoning_effort isn't sent to Nebius
    assert s.jev_model == "typesafe/jev" and s.jev_token == "cf-token"   # Jev stays on Cloudflare
    assert s.tts_model.startswith("@cf/")


def test_nebius_defaults_to_nemotron_ultra_without_thinking(monkeypatch):
    env(monkeypatch, JDF_LLM_PROVIDER="nebius", NEBIUS_API_KEY="nb-key")
    s = load()
    assert s.plan_model == s.read_model == s.script_model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert s.llm_extra == {"chat_template_kwargs": {"enable_thinking": False}}


def test_nebius_needs_its_key(monkeypatch):
    env(monkeypatch, JDF_LLM_PROVIDER="nebius", JDF_NEBIUS_MODEL="nvidia/some-nemotron")
    with pytest.raises(ConfigError):
        load()


def test_an_unknown_provider_is_an_error(monkeypatch):
    env(monkeypatch, JDF_LLM_PROVIDER="elsewhere")
    with pytest.raises(ConfigError):
        load()


def test_chat_posts_to_the_configured_provider(monkeypatch):
    env(monkeypatch, JDF_LLM_PROVIDER="nebius", NEBIUS_API_KEY="nb-key", JDF_NEBIUS_MODEL="nvidia/some-nemotron")
    cf = Cloudflare(load())
    sent = {}
    def fake_post(url, body, token=None):
        sent.update(url=url, token=token, model=body["model"], thinking=body["chat_template_kwargs"]["enable_thinking"])
        return {"choices": [{"message": {"content": "ok"}}]}
    monkeypatch.setattr(cf, "_post", fake_post)
    assert cf.chat(cf.s.plan_model, "system", "user") == "ok"
    assert sent == {"url": "https://api.tokenfactory.nebius.com/v1/chat/completions", "token": "nb-key",
                    "model": "nvidia/some-nemotron", "thinking": False}


def test_nebius_keeps_extras_the_user_set(monkeypatch):
    env(monkeypatch, JDF_LLM_PROVIDER="nebius", NEBIUS_API_KEY="nb-key", JDF_PLAN_EXTRA='{"temperature": 0.1}')
    s = load()
    assert s.plan_extra == {"temperature": 0.1} and s.script_extra == {}


def test_a_non_json_error_page_is_a_model_error_not_a_crash(monkeypatch):
    import httpx
    from jev_demofast.cloudflare import ModelError
    env(monkeypatch)
    cf = Cloudflare(load())
    cf._local.client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(502, text="<html>Bad gateway</html>", headers={"content-type": "text/html"})))
    with pytest.raises(ModelError, match="HTTP 502"):
        cf.chat(cf.s.plan_model, "system", "user")
