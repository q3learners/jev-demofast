"""Pages built from one template (every collection, every product) share one route in the map."""
from jev_demofast.explore.templates import pick_examples, templates


def test_siblings_share_a_route():
    routes = templates(["/collections/mens", "/collections/womens", "/pages/about"])
    assert routes == {"/collections/mens": "/collections/:handle", "/collections/womens": "/collections/:handle",
                      "/pages/about": "/pages/about"}


def test_queries_and_trailing_slashes_are_ignored():
    routes = templates(["/collections/mens/?page=2", "/collections/womens", "/"])
    assert routes["/collections/mens/?page=2"] == "/collections/:handle" and routes["/"] == "/"


def test_siblings_on_one_prefix_group_and_a_lone_deep_page_keeps_its_path():
    routes = templates(["/w/mens-shoes-nik1zy7ok", "/w/womens-running-37v7jz", "/t/air-max/DM0029"])
    assert routes["/w/mens-shoes-nik1zy7ok"] == "/w/:handle" and routes["/t/air-max/DM0029"] == "/t/air-max/DM0029"


def test_two_examples_per_route_in_discovery_order():
    paths = ["/collections/mens", "/pages/about", "/collections/womens", "/collections/sale"]
    assert pick_examples(paths, templates(paths)) == ["/collections/mens", "/pages/about", "/collections/womens"]


def test_kept_paths_are_their_own_routes_query_included():
    """Pages found through buttons (a Flutter app): grouped, the account step's password field marked every K-12 page
    as a sign-in page, and ?mode=signin and ?mode=signup are different screens."""
    paths = ["/setup/who", "/setup/account?mode=signin", "/setup/account?mode=signup", "/setup/student"]
    r = templates(paths, keep=frozenset(paths))
    assert r == {p: p for p in paths}


def test_other_paths_still_group_beside_kept_ones():
    r = templates(["/collections/mens", "/collections/womens", "/setup/who"], keep=frozenset({"/setup/who"}))
    assert r["/collections/mens"] == "/collections/:handle" and r["/setup/who"] == "/setup/who"
