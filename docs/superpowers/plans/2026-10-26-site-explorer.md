# Site Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jev-demofast explore <url>` maps a public site (menus, listing templates with filters, pop-ups) ahead of time, and `demo --index <map>` drives a founder-style demo from it: menus opened on camera, filters applied, the result showcased, verified by the screenshot check.

**Architecture:** A new `explore/` package builds the map with the existing browser layer and writes the existing index shape plus `kind`/`filters`/`sort`/`examples` per route and a `_site` record (menus, pop-ups, block). The map-driven driver (`drive/jev_drive.py`) gains four small collaborators in their own modules (pop-ups, menus, filters, showcase) and the stricter check for explored maps.

**Tech Stack:** Python 3.12, Chrome DevTools Protocol via browser-harness, pytest (offline), Jev / Clef / Nemotron through `cloudflare.Cloudflare`.

**Spec:** `docs/superpowers/specs/2026-10-26-site-explorer-design.md`

## Global Constraints

- Tests run offline: no browser, keys or network (`uv run pytest`). Fake sessions and fake `cf`, in the style of `tests/test_goal_reached.py`.
- No rule written for one site: no site names, hostnames or Allbirds parameter names in `src/`.
- Never evade bot protection; never submit, sign up, add to bag, type into a pop-up, or leave the site while exploring.
- Same safety guards as today (`drive/guards.py`: `blocked`, `on_site`); secrets stay `{{NAME}}` placeholders.
- Explored maps verify with `check.goal_reached` (Clef + screenshot, `GOAL_CONFIDENT` 0.75) and, where a filter's URL form is known, the URL must agree. Source-code maps keep `jev_drive.confirmed`.
- Menus in a demo open on camera (click, or hover where the map says hover), then the item is clicked; never navigate straight to a URL to skip navigation.
- Files under ~400 lines; match the surrounding code (short functions, plain names, comments only for the non-obvious reason).
- Exploring budget defaults: 40 pages, 5 minutes, same site only.
- Done by Wednesday 29 October 2026; Thursday is for the hackathon submission.

## Review Focus

- **A pop-up that appears late** (seconds after load, as Allbirds' did on one visit but not another): `clear_popups` runs before every screen decision, not only at start. Pinned in Task 7 (`test_a_popup_that_appears_mid_run_is_cleared`).
- **A pop-up whose only visible controls are an email field and "Continue"**: never fill, never click a sign-up control; leave it and log. Pinned in Task 2 (`test_never_types_or_signs_up_to_clear_a_popup`).
- **A menu opener that is also a link** (Nike's "Men" navigates when clicked): explore by hover first and click only button-like openers; in demos follow the map's `opens_on`. Pinned in Task 5 (`test_a_link_opener_is_hovered_not_clicked`).
- **A listing with no filters in the URL** (path-encoded or client-side): recorded with `param: None`; verification uses the screenshot check alone. Pinned in Task 3 (`test_filters_without_url_names_are_kept_with_param_none`).
- **A map from an older `explore` run that lacks `_site` or `filters`**: the driver treats a missing key as "not known" and falls back to today's behaviour. Pinned in Task 8 (`test_a_map_without_site_or_filters_still_drives`).

---

### Task 1: Isolated browser context and hover

**Files:**
- Modify: `src/jev_demofast/browser/cdp.py` (`Browser.__init__`, `Browser.close`)
- Modify: `src/jev_demofast/drive/session.py` (`Session.__init__`, new `Session.hover`)
- Test: `tests/test_session_context_hover.py`

**Interfaces:**
- Produces: `Browser(url, isolated: bool = False)`; when `isolated`, it calls `Target.createBrowserContext` and passes `browserContextId` to `Target.createTarget`; `close()` also calls `Target.disposeBrowserContext`.
- Produces: `Session(url, fresh=False, isolated=False)` passing `isolated` through.
- Produces: `Session.hover(element: dict) -> None`: reads the node's centre with `getBoundingClientRect` (via `window.__jevFast.nodes`) and sends `Input.dispatchMouseEvent` `type="mouseMoved"` at it; raises `StalePage` if the node is gone.

- [ ] **Step 1: Write the failing tests** (monkeypatch `jev_demofast.browser.cdp.cdp` and `ensure_daemon` with recorders):
  - `test_an_isolated_browser_opens_its_own_context`: `Browser("about:blank", isolated=True)` → recorded calls include `Target.createBrowserContext`, and the `Target.createTarget` call has `browserContextId` equal to the id it returned; after `close()`, `Target.disposeBrowserContext` was called with that id.
  - `test_a_default_browser_uses_the_shared_profile`: no `createBrowserContext` call.
  - `test_hover_moves_the_mouse_to_the_element_centre`: fake browser `evaluate` returns `{"x": 100, "y": 50, "w": 40, "h": 20}` → `call("Input.dispatchMouseEvent", type="mouseMoved", x=120, y=60)`.
- [ ] **Step 2: Run** `uv run pytest tests/test_session_context_hover.py -q` → 3 failed.
- [ ] **Step 3: Implement** the three interfaces above. `Browser.__init__` keeps its readiness loop unchanged.
- [ ] **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** `git commit -m "Browser: optional isolated context; Session.hover"`

### Task 2: Bot-check detection and pop-up clearing

**Files:**
- Create: `src/jev_demofast/drive/popups.py`
- Test: `tests/test_popups.py`

**Interfaces:**
- Produces: `bot_check(page: dict) -> str | None`: the matched phrase if the page reads as a block, else `None`. Pattern (case-insensitive, first 3000 chars of `text` plus `title`): `access denied|captcha|verify you are (a )?human|are you a robot|press (&|and) hold|just a moment|unusual (traffic|activity)|request blocked|pardon our interruption`.
- Produces: `COVERED_JS` and `covered(s) -> bool`: true when a visible `[role=dialog]`, `dialog[open]` or `[aria-modal=true]` overlaps the viewport centre, or when `body` has more than 3 direct children with `aria-hidden="true"`/`inert` while the viewport shows fewer than 5 observed elements.
- Produces: `clear_popups(cf, s, log=print) -> str | None`: returns `"escape"`, `"close: <label>"`, or `None` (nothing covered, or could not clear). Order: if not `covered(s)` → `None`; press Escape (`Input.dispatchKeyEvent` keyDown/keyUp `Escape`), `s.wait_for_page()`, `s.observe()`; if no longer covered → `"escape"`; else candidates = observed elements with `"click"` in actions, role `button` or `link`, not `blocked(label)`, and not matching `sign ?up|subscribe|continue|submit|join|get .*off|unlock` (case-insensitive); `cf.choose("A pop-up covers the page. Which control closes it without signing up or giving any details? 'none' if none.", {node: describe(e)}, {"url": ..., "text": ...}, allow_none=True)`; click only at confidence ≥ 0.5, then wait and re-check. Never fills anything.

- [ ] **Step 1: Write the failing tests:**
  - `test_bot_check_reads_a_block_page`: `bot_check({"title": "Access Denied", "text": "You don't have permission"}) == "Access Denied"`; a normal shop page → `None`.
  - `test_escape_clears_a_popup`: fake session where `covered` is true until an Escape key event is sent → `clear_popups(...) == "escape"`, and `cf.choose` never called.
  - `test_a_close_button_clears_a_popup_escape_cannot`: still covered after Escape; elements `["Email Address" (textbox), "Continue" (button), "Close" (button)]`; fake `cf.choose` returns the Close node at 0.9 → returns `"close: Close"`; the only `act` was a click on Close.
  - `test_never_types_or_signs_up_to_clear_a_popup`: elements `["Email Address" (textbox), "Continue" (button)]` → `cf.choose` is not offered "Continue"; returns `None`; no `act` call.
- [ ] **Step 2: Run** `uv run pytest tests/test_popups.py -q` → 4 failed.
- [ ] **Step 3: Implement** `drive/popups.py` per the interfaces.
- [ ] **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** `git commit -m "Pop-ups: detect a bot block; clear a covering pop-up without signing up"`

### Task 3: Reading a listing's filters and sort

**Files:**
- Create: `src/jev_demofast/explore/__init__.py` (empty for now), `src/jev_demofast/explore/listing.py`
- Test: `tests/test_explore_listing.py`

**Interfaces:**
- Produces: `READ_LISTING_JS` (returns raw groups from the DOM, hidden controls included): `{"groups": [{"heading": str, "controls": [{"type": "checkbox"|"radio"|"number"|"text"|"select", "name": str, "label": str}]}], "item_links": int}`. Headings come from the nearest `summary`, `legend`, `[aria-label]` group, or preceding heading; `item_links` counts distinct same-site links that share the most common two-segment path prefix.
- Produces: `parse_listing(raw: dict) -> dict` → `{"kind": "listing"|"page", "filters": [{"group": str, "kind": "checkbox"|"range"|"radio", "param": str | list[str] | None, "values": list[str]}], "sort": {"param": str | None, "options": list[str]} | None}`. A group is the sort when its heading or name matches `sort`; range when it has two number/text inputs whose names or labels say min/max or gte/lte; `param` is the controls' shared `name` when it looks like a URL key (contains `.` or `_` or `[`), else `None`. `kind` is `"listing"` when `item_links >= 8` and there is at least one filter group or a sort.
- Produces: `read_listing(s) -> dict`: `parse_listing(s.browser.evaluate(READ_LISTING_JS))`.

- [ ] **Step 1: Write the failing tests:**
  - `test_shopify_style_filters` (fixture shaped like the recon: headings Sort By / Size / Price / Product Type; names `sort_by`, `filter.p.m.x.category_sizes`, `filter.v.price.gte`/`lte`, `filter.p.m.x.category_subtypes`; `item_links` 45) → kind `"listing"`; Price is `{"kind": "range", "param": ["filter.v.price.gte", "filter.v.price.lte"]}`; Product Type values include `"Running Shoes"` with param `filter.p.m.x.category_subtypes`; sort options include `"Price, low to high"`.
  - `test_filters_without_url_names_are_kept_with_param_none`: fieldset `legend "Colour"`, checkbox controls with empty names → one filter, `param is None`, values kept.
  - `test_a_page_without_items_is_not_a_listing`: `item_links` 3 → `"page"`.
- [ ] **Step 2: Run** → 3 failed. **Step 3: Implement.** **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** `git commit -m "Explore: read a listing's filters and sort from the page"`

### Task 4: URL templates

**Files:**
- Create: `src/jev_demofast/explore/templates.py`
- Test: `tests/test_explore_templates.py`

**Interfaces:**
- Produces: `templates(paths: list[str]) -> dict[str, str]` mapping each path to its route: paths with the same number of segments that differ in exactly one position, with at least 2 distinct values there, share a route with that segment replaced by `:handle` (`:handle2` if a route needs two). Everything else maps to itself; `/` stays `/`; trailing slashes and query strings are ignored.
- Produces: `pick_examples(paths, routes, per_route=2) -> list[str]`: for each route, the first `per_route` paths in input order (input order is discovery order, so menu destinations come first).

- [ ] **Step 1: Write the failing tests:** `test_siblings_share_a_route` (`/collections/mens`, `/collections/womens` → `/collections/:handle`; `/pages/about` alone stays); `test_queries_and_trailing_slashes_are_ignored`; `test_two_examples_per_route_in_discovery_order`.
- [ ] **Steps 2–4:** run (fail), implement, run `uv run pytest -q` (pass).
- [ ] **Step 5: Commit** `git commit -m "Explore: group URLs into route templates"`

### Task 5: Discovering menus

**Files:**
- Create: `src/jev_demofast/explore/menus.py`
- Test: `tests/test_explore_menus.py`

**Interfaces:**
- Consumes: `Session.hover` (Task 1), `clear_popups` (Task 2).
- Produces: `VISIBLE_LINKS_JS` → `[{"label": str, "to": str}]` for visible same-site `a[href]` (path only).
- Produces: `new_links(before: list[dict], after: list[dict]) -> list[dict]`: links in `after` whose `to` is not in `before`, de-duplicated by `to`, in `after` order.
- Produces: `discover_menus(s, log=print, max_openers=12) -> list[dict]`: openers are observed elements in the top 220 px with role `button` or `link`, not `blocked`. For each: hover, `wait_for_page`, diff visible links; if nothing new and the opener is a `button` (not a link), click instead, diff again, then press Escape. Returns `[{"opener": label, "opens_on": "hover"|"click", "items": [{"label", "to"}]}]` for openers that revealed at least 2 links; never clicks a `link`.

- [ ] **Step 1: Write the failing tests:** `test_new_links_only_lists_revealed_destinations`; `test_a_hover_menu_is_recorded_as_hover` (fake session: hovering "Men" makes 3 more links visible); `test_a_link_opener_is_hovered_not_clicked` (a `link` "Men" with no hover effect → no click, no menu); `test_a_button_menu_is_recorded_as_click` (a `button` "Shop" reveals links only on click → `opens_on == "click"`, then Escape sent).
- [ ] **Steps 2–4:** run (fail), implement, run `uv run pytest -q` (pass).
- [ ] **Step 5: Commit** `git commit -m "Explore: discover hover and click menus"`

### Task 6: The explorer, its map, and `jev-demofast explore`

**Files:**
- Modify: `src/jev_demofast/explore/__init__.py` (the crawl)
- Modify: `src/jev_demofast/index/__init__.py` (`summary` mentions filters; `route_for` skips keys starting with `_`)
- Modify: `src/jev_demofast/cli.py` (`explore` subcommand)
- Test: `tests/test_explore_crawl.py`, `tests/test_index.py` (one added test)

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: `explore(url: str, out: str | None = None, max_pages: int = 40, max_minutes: float = 5, cf=None, log=print, session=Session) -> dict` returning the map (spec "Map format"), writing JSON to `out` when given. Steps: `session(url, isolated=True)`; `bot_check` → `_site.blocked` set, map otherwise empty, return; `clear_popups(cf, s)` (record in `_site.popups` as `{"seen_on": path, "cleared_by": how}`); `discover_menus` → `_site.menus`; queue = menu item destinations, then visible top-region links, then other same-site links (de-duplicated, `blocked` labels skipped); route by `templates`; visit `pick_examples`, stopping at `max_pages` or `max_minutes`; on each page: `clear_popups`, `read_listing`, headings (`h1`–`h3`, up to 10) as `texts`, visible links/buttons as `links`/`buttons`, visible fields as `fields`, `submits: False`, `file: "explored: <url>"`, `examples`. Filter values for a route merge across its examples (union, order kept).
- Produces: route keys starting with `_` are ignored by `route_for`; `summary()` appends `filters: <group>, <group>` (up to 4) for routes with `filters`.
- Produces: `jev-demofast explore <url> [--out site-map.json] [--pages 40] [--minutes 5]` printing `<n> routes, <m> listings, <k> menus → <out>`, or `blocked: <phrase>` with exit code 1.

- [ ] **Step 1: Write the failing tests** (a fake `session` class serving a three-page fake site; fake `cf` whose `choose` returns `None`):
  - `test_explore_writes_menus_listings_and_templates`: home has menu "Men" (hover → `/collections/mens`, `/collections/womens`) and link `/pages/about`; collection pages return a listing raw → map has `/collections/:handle` with `kind == "listing"` and its filters, `/pages/about`, and `_site.menus[0]["opener"] == "Men"`.
  - `test_explore_stops_on_a_bot_check`: home title "Access Denied" → `_site.blocked == "Access Denied"`, no routes, one page visited.
  - `test_explore_respects_the_page_budget`: 10 sibling pages, `max_pages=3` → at most 3 `observe`d paths.
  - `tests/test_index.py::test_route_for_ignores_site_records_and_summary_lists_filters`.
- [ ] **Step 2: Run** → fail. **Step 3: Implement.** **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** `git commit -m "Explore: crawl a site into a map; jev-demofast explore"`

### Task 7: Demos clear pop-ups and open menus on camera

**Files:**
- Create: `src/jev_demofast/drive/menus.py`
- Modify: `src/jev_demofast/drive/jev_drive.py` (`run` loop start; `_navigate` options)
- Test: `tests/test_drive_menus_popups.py`

**Interfaces:**
- Consumes: `clear_popups` (Task 2), `Session.hover` (Task 1), map `_site.menus` (Task 6).
- Produces: `menu_options(index: dict, els: list[dict]) -> list[tuple[dict, dict]]`: `(opener element, menu)` for each map menu whose `opener` label matches a visible element (`elements.words` equality, as `_navigate` already matches labels).
- Produces: `open_menu(cf, s, rec, opener: dict, menu: dict, goal: str, state: dict, log) -> bool`: `rec.snap(1.0, node=opener["node"])`; hover or click per `menu["opens_on"]`; `wait_for_page`; `rec.snap(0.8)`; `rec.commit({"do": "click" | "hover", "target": f"open the {opener['label']} menu"}, page)`; then `cf.choose("Which menu item moves toward the goal?", ...)` over now-visible elements whose label matches one of `menu["items"]`; click it like `_navigate` does (snap with outline, act, wait, commit). Returns `False` if no item is visible after opening.
- In `jev_drive.run`: call `clear_popups(cf, s, log)` at the top of every loop iteration, before reading the screen.
- In `_navigate`: add each menu option as `opener label + " → opens: " + ", ".join(item labels[:8])`; choosing one calls `open_menu` instead of a plain click.

- [ ] **Step 1: Write the failing tests:** `test_a_menu_opens_on_camera_then_its_item_is_clicked` (fake session: hovering "Men" reveals "Running"; fake `cf` picks the menu option, then "Running" → actions recorded in order `hover Men`, `click Running`; two committed segments); `test_a_popup_that_appears_mid_run_is_cleared` (pop-up appears on the second screen → Escape sent before that screen's decision).
- [ ] **Steps 2–4:** run (fail), implement, run `uv run pytest -q` (pass).
- [ ] **Step 5: Commit** `git commit -m "Demos: clear pop-ups every screen; open menus on camera"`

### Task 8: Filters, verification for explored maps, and the showcase ending

**Files:**
- Create: `src/jev_demofast/drive/filters.py`, `src/jev_demofast/drive/showcase.py`
- Modify: `src/jev_demofast/drive/jev_drive.py` (listing screens; done/verify path)
- Test: `tests/test_drive_filters_showcase.py`

**Interfaces:**
- Consumes: route entry `filters` (Task 3 shape); `check.goal_reached`; `plan.extract`.
- Produces: `FILTER_VALUES` prompt and `choose_filters(cf, goal, filters) -> dict` → `{"checks": [{"group", "value"}], "ranges": [{"group", "min": str|None, "max": str|None}], "sort": str|None}` from `cf.chat_json(cf.s.read_model, FILTER_VALUES, {...})`, keeping only groups and values present in `filters` (anything invented is dropped).
- Produces: `apply_filters(cf, s, rec, goal, entry, log) -> list[str]` returning the URL params expected afterwards (`"<param>=<value>"`, values URL-encoded; ranges give the max/min param). For each choice: if the control isn't visible, click the group's heading (`summary`/button whose label matches the group) on camera; click the checkbox/radio whose label matches the value, or fill the range box (`Session.act(e, "fill", text=...)`, then press Enter); `wait_for_page`; snap with outline; commit `{"do": "filter", "target": f"{group}: {value}"}`. Never calls `_stop_if_dry_run` for filter controls.
- Produces: `url_agrees(url: str, expected: list[str]) -> bool`: every expected `param=value` is in the decoded query.
- Produces: `showcase(cf, s, rec, goal, log, count=3) -> list[str]`: `items = extract(cf, "the items this page lists that the goal is about, each with its price", url, s.full_text())`; for each of the first `count` items, the visible link whose label contains the item's first 30 characters is scrolled into view and snapped with an outline (`rec.snap(1.5, node=...)`); one commit `{"do": "read", "target": "showcase", "items": items}`. Returns items.
- In `jev_drive.run`: an index is "explored" when it has `_site`. On a screen whose route entry has `filters` and `kind == "listing"`, when Jev's mode is `act_here`, call `apply_filters` instead of `_fill_and_submit`; then verify with `goal_reached(cf, goal, page, screenshot)` (explored maps) and `url_agrees` when params are known; verified → `showcase`, then stop. For explored maps the `done` mode also uses `goal_reached`. Source-code maps keep `confirmed`.

- [ ] **Step 1: Write the failing tests:** `test_invented_filter_values_are_dropped` (chat returns `"Product Type": "Trail Shoes"` not in values → dropped); `test_filters_apply_on_camera_and_the_url_must_agree` (fake session: clicking "Running Shoes" and filling max 100 set the URL query → `apply_filters` returns the two params; `url_agrees` true; segments committed for each filter); `test_a_wrong_url_fails_verification_even_if_the_screen_check_passes`; `test_showcase_highlights_three_items`; `test_a_map_without_site_or_filters_still_drives` (a source-code-style map: no `_site`, no filters → today's `_fill_and_submit`/`confirmed` path is taken).
- [ ] **Steps 2–4:** run (fail), implement, run `uv run pytest -q` (pass).
- [ ] **Step 5: Commit** `git commit -m "Demos: apply mapped filters on camera, verify explored maps, showcase the result"`

### Task 9: Live acceptance, docs, PR

**Files:**
- Modify: `README.md` (an "Explore a live site" section with measured numbers), `docs/how-it-works.md` (one paragraph)

- [ ] **Step 1: Explore Allbirds:** `uv run jev-demofast explore https://www.allbirds.com/ --out out/allbirds-map.json` → prints routes/listings/menus; the map has `/collections/:handle` with Product Type ("Running Shoes") and a Price range.
- [ ] **Step 2: Five demo runs:** `uv run jev-demofast demo "Show how to find men's running shoes under \$100 on Allbirds" --url https://www.allbirds.com/ --index out/allbirds-map.json --fresh --out out/allbirds-<n>.mp4` ×5. Pass: ≥ 4 `verified: True`, each ending on a URL with the running and `price.lte=100` params, Men menu opened on camera, 2–3 shoes highlighted. Watch one video end to end.
- [ ] **Step 3: Generality:** `explore` Everlane, Gymshark, Nike → each map has `_site.menus` and at least one listing route with filters (Nike's menus `opens_on: hover`). `explore https://www.zara.com/us/` → `blocked: Access Denied` within 15 s.
- [ ] **Step 4: Record results** in README and the PR description (pass counts, timings, which sites, what failed and why).
- [ ] **Step 5: Commit and open the PR.** Run `uv run pytest -q` first; all pass.
