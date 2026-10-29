"""Where blueprints live, so mapping is done once and learns after that. One file per site and account, keyed by an
HMAC of the account's email with a secret made once on this machine: the email never appears on disk, and a guessed
email can't find its map. The map holds what the demo account shows and what mapping typed, never a password."""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

MAPS = Path("~/.cache/jev-demofast/maps").expanduser()


def _secret(maps):
    key = maps / ".key"
    if not key.exists():
        maps.mkdir(parents=True, exist_ok=True)
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    return key.read_bytes()


def map_path(host, email, maps=None):
    maps = maps or MAPS
    digest = hmac.new(_secret(maps), (email or "").lower().encode(), hashlib.sha256).hexdigest()[:16]
    return maps / f"{host}.{digest}.behaviour.json"


def load_map(host, email):
    path = map_path(host, email)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_map(m, host, email):
    path = map_path(host, email)
    with open(path, "w") as f:
        json.dump(m, f, indent=1)
    return path
