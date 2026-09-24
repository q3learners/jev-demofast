"""Settings from the environment, validated once at start-up. Nothing else reads os.environ."""
import os
from dataclasses import dataclass, field


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

    @property
    def base(self):
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai"


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
    return Settings(account_id=account, api_token=token, jev_token=os.environ.get("JEV_TOKEN") or token,
                    cdp_url=os.environ.get("BU_CDP_URL", "http://127.0.0.1:9333"), **overrides)


def quiet_browser_harness():
    """browser-harness sends opt-out telemetry and checks for updates; keep both off unless the user opts in."""
    os.environ.setdefault("BH_TELEMETRY", "0")
    os.environ.setdefault("BH_UPDATE_CHECK", "0")


def secret(name):
    """A {{NAME}} placeholder's value, from DEMO_<NAME>. Never logged, never sent to a model."""
    return os.environ.get(f"DEMO_{name}")
