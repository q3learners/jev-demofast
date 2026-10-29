"""Where blueprints live: one per site and account, keyed so the account's email never appears on disk and can't be
recomputed from a guessed email without the secret made once on this machine."""
import os

import pytest

from jev_demofast.behaviour import store
from jev_demofast.behaviour.model import empty
from jev_demofast.behaviour.store import load_map, map_path, save_map


@pytest.fixture(autouse=True)
def maps(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MAPS", tmp_path / "maps")
    return tmp_path / "maps"


def test_the_path_never_holds_the_email():
    p = str(map_path("k12.test", "parent@demo.test"))
    assert "parent" not in p and "demo.test" not in p and p.endswith(".behaviour.json") and "k12.test" in p


def test_the_key_needs_the_secret(maps):
    first = map_path("k12.test", "parent@demo.test")
    (maps / ".key").unlink()
    assert map_path("k12.test", "parent@demo.test") != first


def test_the_secret_is_private(maps):
    map_path("k12.test", "parent@demo.test")
    assert os.stat(maps / ".key").st_mode & 0o777 == 0o600


def test_save_then_load_round_trips():
    m = empty()
    m["account"]["state"] = "set up"
    save_map(m, "k12.test", "Parent@Demo.test")
    assert load_map("k12.test", "parent@demo.test") == m


def test_unknown_account_loads_none():
    assert load_map("k12.test", "nobody@demo.test") is None


def test_maps_are_private_and_never_written_through_a_link(maps, tmp_path):
    """Security review: a blueprint holds what the demo account shows (kids' names): the folder is 0700, each map
    0600, and a symlink planted at a map's path is never written through."""
    path = save_map(empty(), "k12.test", "parent@demo.test")
    assert os.stat(maps).st_mode & 0o777 == 0o700 and os.stat(path).st_mode & 0o777 == 0o600
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text("untouched")
    path.unlink()
    path.symlink_to(elsewhere)
    with pytest.raises(OSError):
        save_map(empty(), "k12.test", "parent@demo.test")
    assert elsewhere.read_text() == "untouched"
