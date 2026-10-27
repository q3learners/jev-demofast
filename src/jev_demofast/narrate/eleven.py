"""ElevenLabs: the whole voice-over in one take, with the time each character is spoken.

One take keeps a person's intonation across sentences; separate clips per line (Deepgram) each started flat and
sounded like a computer. The character timings let each recorded moment come up on its marker.
"""
import base64

import httpx

from ..cloudflare import ModelError

URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128"
# ElevenLabs' default conversational voices that suit a founder (names as --voice takes them).
VOICES = {"chris": "iP95p4xoKVk53GoZ742B", "eric": "cjVigY5qzO86Huf0OWal", "will": "bIHbv24MWmeRgasZH58o",
          "sarah": "EXAVITQu4vr4xnSDxMaL", "jessica": "cgSgspJ2msm6clMCkdW9"}


def speaks(settings, voice_name):
    """ElevenLabs narrates when its key is set and the voice is one of its voices."""
    return bool(settings.eleven_key) and (voice_name or "").lower() in VOICES


class ElevenLabs:
    def __init__(self, key, model, http=None):
        self.key, self.model = key, model
        self.http = http or httpx.Client(timeout=180)

    def speak(self, text, voice_name):
        """(MP3 bytes, the start time of each character of `text` in seconds, the audio's length in seconds)."""
        r = self.http.post(URL.format(voice=VOICES[voice_name.lower()]), headers={"xi-api-key": self.key},
                           json={"text": text, "model_id": self.model})
        if r.is_error:
            raise ModelError(f"ElevenLabs: HTTP {r.status_code}: {r.text[:200]!r}")
        data = r.json()
        timing = data.get("alignment") or {}
        starts, ends = timing.get("character_start_times_seconds", []), timing.get("character_end_times_seconds", [])
        if len(starts) != len(text):
            raise ModelError(f"ElevenLabs: timings for {len(starts)} characters, the text has {len(text)}")
        return base64.b64decode(data["audio_base64"]), starts, ends[-1] if ends else 0.0
