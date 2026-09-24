"""Settings from the environment, validated once at start-up. Nothing else reads os.environ."""
import os
from dataclasses import dataclass, field, replace


class ConfigError(SystemExit):
    pass


@dataclass(frozen=True)
class Settings:
    account_id: str
    api_token: str
    jev_token: str
    # Models (all Cloudflare Workers AI). Override with env vars of the same name, upper-cased with JDF_ prefix.
    jev_model: str = "typesafe/jev"
    # Route plans: GLM-5.3-flash (reasoning low) gave the same sensible plan 3/3; Llama 3.3 varied run to run.
    plan_model: str = "@cf/zai-org/glm-5.3-flash"
    plan_extra: dict = field(default_factory=lambda: {"reasoning_effort": "low"})
    read_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"  # extraction and form values: fast, good enough
    script_model: str = "@cf/zai-org/glm-5.3-flash"
    script_extra: dict = field(default_factory=lambda: {"reasoning_effort": "low"})
    embed_model: str = "@cf/baai/bge-base-en-v1.5"
    tts_model: str = "@cf/deepgram/aura-2-en"
    cdp_url: str = "http://127.0.0.1:9333"
    # Where the language-model calls (route plans, page reading, scripts) go. Jev, voice and embeddings stay on
    # Cloudflare whichever provider is chosen. Empty means Cloudflare Workers AI.
    llm_provider: str = "cloudflare"
    llm_url: str = ""
    llm_token: str = ""
    llm_extra: dict = field(default_factory=dict)  # sent with every chat call to this provider

    @property
    def base(self):
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai"


# OpenAI-compatible chat providers for the language-model calls: chat completions URL, API key variable, default
# model, and request fields sent with every call.
# Nebius: NVIDIA Nemotron 3 Ultra with thinking off planned the GitHub route best of the four Nemotron models
# (Open Source > Trending > This week > a repo) in about 1 s; with thinking on, every model took 4-15 s.
LLM_PROVIDERS = {
    "nebius": {"url": "https://api.tokenfactory.nebius.com/v1/chat/completions", "key": "NEBIUS_API_KEY",
               "model": "nvidia/Nemotron-3-Ultra-550b-a55b",
               "extra": {"chat_template_kwargs": {"enable_thinking": False}}},
}


def _llm_provider(overrides):
    """JDF_LLM_PROVIDER picks where language-model calls go. The provider's model (override with JDF_NEBIUS_MODEL)
    serves plans, reading and scripts unless JDF_PLAN_MODEL / JDF_READ_MODEL / JDF_SCRIPT_MODEL say otherwise."""
    name = os.environ.get("JDF_LLM_PROVIDER", "cloudflare").lower()
    if name == "cloudflare":
        return {}
    if name not in LLM_PROVIDERS:
        raise ConfigError(f"JDF_LLM_PROVIDER={name!r} is not supported (use cloudflare or {', '.join(LLM_PROVIDERS)})")
    p = LLM_PROVIDERS[name]
    token = os.environ.get(p["key"], "")
    if not token:
        raise ConfigError(f"JDF_LLM_PROVIDER={name} needs {p['key']}")
    model = os.environ.get(f"JDF_{name.upper()}_MODEL") or p["model"]
    chosen = {"llm_provider": name, "llm_url": p["url"], "llm_token": token, "llm_extra": p["extra"],
              "plan_extra": {}, "script_extra": {}}
    for role in ("plan_model", "read_model", "script_model"):
        chosen[role] = overrides.get(role, model)
    return chosen


def load(require_cloudflare=True) -> Settings:
    """Read settings. Cloudflare credentials are required for anything that calls a model."""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if require_cloudflare and not (account and token):
        raise ConfigError("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (Workers AI). "
                          "Jev also needs AI Gateway credits on that account.")
    overrides = {}
    for name in ("jev_model", "plan_model", "read_model", "script_model", "embed_model", "tts_model"):
        value = os.environ.get(f"JDF_{name.upper()}")
        if value:
            overrides[name] = value
    import json
    for name in ("script_extra", "plan_extra"):
        if os.environ.get(f"JDF_{name.upper()}"):
            overrides[name] = json.loads(os.environ[f"JDF_{name.upper()}"])
    overrides.update(_llm_provider(overrides))
    settings = Settings(account_id=account, api_token=token, jev_token=os.environ.get("JEV_TOKEN") or token,
                        cdp_url=os.environ.get("BU_CDP_URL", "http://127.0.0.1:9333"), **overrides)
    if not settings.llm_url:  # Cloudflare Workers AI's OpenAI-compatible endpoint
        settings = replace(settings, llm_url=f"{settings.base}/v1/chat/completions", llm_token=token)
    return settings


def quiet_browser_harness():
    """browser-harness sends opt-out telemetry and checks for updates; keep both off unless the user opts in."""
    os.environ.setdefault("BH_TELEMETRY", "0")
    os.environ.setdefault("BH_UPDATE_CHECK", "0")


def secret(name):
    """A {{NAME}} placeholder's value, from DEMO_<NAME>. Never logged, never sent to a model."""
    return os.environ.get(f"DEMO_{name}")
