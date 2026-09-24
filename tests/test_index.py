from pathlib import Path

from jev_demofast.index import build, route_for, summary

APP = Path(__file__).parent / "fixtures" / "nextapp"


def index():
    return build(APP)


def test_routes_strip_groups_and_skip_api():
    routes = set(index())
    assert {"/", "/about", "/login", "/auth/forgot-password", "/courses/:id"} <= routes
    assert not any("api" in r for r in routes)
    assert not any("(" in r for r in routes)


def test_links_from_jsx_nav_objects_reexports_and_router_push():
    idx = index()
    home = {(l["label"], l["to"]) for l in idx["/"]["links"]}
    assert ("Log in", "/login") in home                 # <Link href>
    assert ("Catalog", "/courses") in home              # { label, href } nav object in an imported component
    login = {(l["label"], l["to"]) for l in idx["/login"]["links"]}
    assert ("Forgot password?", "/auth/forgot-password") in login   # reached through `export { default } from`
    assert ("Create account", "/signup") in login                  # router.push in onClick


def test_fields_buttons_texts_and_submits():
    forgot = index()["/auth/forgot-password"]
    assert "Email address" in forgot["fields"]
    assert any(b["label"] == "Send reset link" and b["submit"] for b in forgot["buttons"])
    assert "Forgot your password?" in forgot["texts"]
    assert forgot["submits"] is True


def test_route_for_matches_dynamic_segments_and_summary_is_compact():
    idx = index()
    assert route_for("/courses/42", idx) == "/courses/:id"
    assert route_for("/login/", idx) == "/login"
    assert route_for("/nope", idx) is None
    s = summary("/auth/forgot-password", idx)
    assert "Email address" in s and len(s) <= 420


def test_layout_links_apply_to_every_page_beneath_them():
    idx = index()
    for route in ("/dashboard", "/dashboard/settings"):
        links = {(l["label"], l["to"]) for l in idx[route]["links"]}
        assert ("Settings", "/dashboard/settings") in links and ("Team", "/dashboard") in links
    assert not any(l["label"] == "Settings" for l in idx["/login"]["links"])  # not outside the layout's folder
