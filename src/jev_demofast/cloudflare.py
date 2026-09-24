"""One client for every model call: Jev decisions, chat, embeddings, text-to-speech (Cloudflare Workers AI)."""
import json
import math
import re
import threading
import time

import httpx

from .config import Settings


class ModelError(RuntimeError):
    pass


class Cloudflare:
    def __init__(self, settings: Settings):
        self.s = settings
        self._local = threading.local()  # one connection per thread: an HTTP/2 client isn't safe to share
        self.stats = {"jev_calls": 0, "jev_seconds": 0.0, "llm_calls": 0, "llm_seconds": 0.0}

    @property
    def http(self):
        if not hasattr(self._local, "client"):
            self._local.client = httpx.Client(http2=True, timeout=180)
        return self._local.client

    def _post(self, url, body, token=None):
        headers = {"Authorization": f"Bearer {token or self.s.api_token}"}
        try:
            r = self.http.post(url, json=body, headers=headers)
        except httpx.TransportError:  # one retry on a fresh connection for transient network errors
            self._local.client = httpx.Client(http2=True, timeout=180)
            r = self.http.post(url, json=body, headers=headers)
        if r.headers.get("content-type", "").startswith("audio/"):
            return r.content
        data = r.json()
        if r.is_error or data.get("success") is False:
            raise ModelError(f"{url.rsplit('/', 2)[-2:]}: {data.get('errors') or r.status_code}")
        return data

    # --- Jev: typed decisions -------------------------------------------------------------------------------
    def jev(self, state, questions):
        """Ask Jev typed questions about a state. Returns {question id: answer}."""
        started = time.perf_counter()
        try:
            data = self._post(f"{self.s.base}/run", {"model": self.s.jev_model,
                                                    "input": {"state": state, "questions": questions}},
                              token=self.s.jev_token)
        finally:
            self.stats["jev_calls"] += 1
            self.stats["jev_seconds"] += time.perf_counter() - started
        result = data.get("result", data)
        result = result.get("result", result)  # Workers AI wraps the model output one level deeper
        return result["answers"]

    def choose(self, instructions, options, state, allow_none=False):
        """Jev picks one of `options` ({key: description}). Returns (key or None, confidence)."""
        criteria = dict(options)
        if allow_none:
            criteria["none"] = "none of these"
        ans = self.jev(state, {"q": {"type": "choice", "instructions": instructions, "criteria": criteria}})["q"]
        return (None if ans["choice"] == "none" else ans["choice"]), ans["confidence"]

    def yes(self, instructions, state, true="yes", false="no"):
        """Jev's probability that the answer is yes."""
        ans = self.jev(state, {"q": {"type": "noul", "instructions": instructions,
                                     "criteria": {"true": true, "false": false}}})["q"]
        return ans["noul"]

    # --- chat ---------------------------------------------------------------------------------------------
    def chat(self, model, system, user, extra=None, max_tokens=4000):
        started = time.perf_counter()
        try:
            data = self._post(f"{self.s.base}/v1/chat/completions", {
                "model": model, "max_tokens": max_tokens, "temperature": 0.7, **(extra or {}),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        finally:
            self.stats["llm_calls"] += 1
            self.stats["llm_seconds"] += time.perf_counter() - started
        return data["choices"][0]["message"].get("content") or ""

    def chat_json(self, model, system, context, extra=None):
        """Chat whose reply contains one JSON object; returns it."""
        text = self.chat(model, system, json.dumps(context), extra)
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ModelError(f"no JSON in reply: {text[:200]!r}")
        return json.loads(m.group(0))

    # --- embeddings and speech ----------------------------------------------------------------------------
    def embed(self, texts):
        data = self._post(f"{self.s.base}/run/{self.s.embed_model}", {"text": list(texts)})
        return data["result"]["data"]

    def speak(self, text, speaker):
        audio = self._post(f"{self.s.base}/run/{self.s.tts_model}", {"text": text, "speaker": speaker, "encoding": "mp3"})
        if not isinstance(audio, bytes):
            raise ModelError(f"text-to-speech returned no audio: {str(audio)[:200]}")
        return audio


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
