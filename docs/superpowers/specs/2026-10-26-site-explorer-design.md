# Site explorer: a map of a live site, built from its URL

Status: design, for review · 26 October 2026

## Why

**Who the demo is for:** a founder presenting their product, to investors or for marketing. The video shows the product
the way they would: menus opening on camera, buttons clicked, pages browsed, and the result showcased at the end.

jev-demofast has two ways to know a product. With source code, `jev-demofast index` reads a Next.js repo and writes a
map of every screen, and Jev drives demos from it with no route guessing (saas-starter: 5 of 5 runs, 8–17 s). With only
a URL, an LLM guesses the route from the first page, and its guesses are the main cause of failed runs: labels it can't
see (GitHub's "Trending" sits inside a closed "Open Source" menu), the site's search box instead of its navigation, a
bare "1" as a target.

The site explorer closes that gap: given a URL, it browses the live site **once, ahead of time**, and writes the same
kind of map. Demos then drive from the map, as they do from a source-code map. This is the second of the two scenarios
for the hosted service (a repo, or a URL plus logins); the hosted service itself comes later.

Built ahead of time, not during each demo, because a good map needs every menu opened and each screen type seen once:
minutes, not seconds. One map serves many demos until the site changes.

## The first demo it must make work

> Show how to find men's running shoes under $100 on Allbirds

Today (no map): **0 of 2** runs. A newsletter pop-up hides the page, so the tool sees nothing ("STUCK: nothing on the
page means 'Men'"), and the planner invents filters ("Price", "Max price", "Under $100", "Apply").

What is actually there (recon, 26 October): `allbirds.com/collections/mens` lists 45 products and has these filters:
Sort By (9 options, including "Price, low to high"), Size (26), Color (10), **Price (min and max number inputs,
`filter.v.price.gte` / `filter.v.price.lte`)**, **Product Type (8, including "Running Shoes",
`filter.p.m.allbirds_v2.category_subtypes`)**, Material (7). Standard Shopify filters, reflected in the URL.

So the demo is: clear the pop-up → open the Men menu on camera → Product Type: Running Shoes → Price max 100 →
showcase the result (scroll through the listing, highlight two or three shoes, the narration naming them and their
prices), ending on the listing in that state.

## Goals (version 1)

1. `jev-demofast explore <url> --out site-map.json` maps a public site: the screens reachable from its navigation,
   **including menus that open on click or on hover**, with each menu's items and where they lead.
2. **Listing pages, one per template** (a Shopify `/collections/<handle>` is one template however many collections
   exist), with their **filter groups, filter values, sort options, and how each filter appears in the URL**.
3. **Pop-ups** that cover the page are cleared, both while exploring and while recording a demo.
4. `jev-demofast demo "<sentence>" --url <site> --index site-map.json` drives from the explored map with the existing
   map-driven driver (`drive/jev_drive.py`), extended for filters and pop-ups.
5. Works on sites it has never seen: no rule written for one site (CONTRIBUTING already requires this).

## Non-goals (version 1)

- **Product pages:** sizes, colours, "add to bag". Next version.
- **Logins:** public sites only. Logins are the version after (credentials stay `{{NAME}}` placeholders typed without
  reaching a model, as today).
- Checkout, accounts, wish lists, or anything else that changes data.
- The hosted service (accounts, queues, browsers on servers, storage).
- Detecting that a saved map is out of date.

## Anti-goals: failure even if it "works"

- **Getting around bot protection.** Zara, H&M, ASOS and Uniqlo answered "Access Denied" to the test browser. The
  explorer detects a block and stops with a clear message; it never tries to evade it. Founders allow the tool on their
  own product or use staging.
- **Changing anything while exploring:** no submits, sign-ups, newsletter forms, add-to-bag, deletes. Exploring only
  navigates, opens menus, and (to learn a filter's URL form, if needed) applies a filter.
- **Typing into a pop-up.** Clearing one means Escape or its close / "no thanks" control, never its email field.
- **A false success.** A demo verifies only when the final screen shows the goal in the state asked for (all running
  shoes at or under $100), the bar the screenshot check (Clef) now enforces.
- **Crawling a catalogue.** One or two pages per template, not every product or collection.

## Constraints

- Same safety guards as today: same site only; no sign-up, third-party login, log-out or delete clicks (`guards.py`).
- Decisions: Jev for clicks; the checks (`drive/check.py`) use Clef with a screenshot by default; language-model calls
  (planning, reading) use the configured provider (Nemotron on Nebius for the hackathon).
- Offline tests (`uv run pytest` needs no browser, keys or network); files under ~400 lines; match the surrounding code.
- Hackathon: submissions close Thursday 30 October 2026, 10:00 PT. The explorer is the chosen next piece; the
  submission video and write-up still need time before then.

## Decided (with the product owner)

| Decision | Choice |
|---|---|
| When the map is built | ahead of time, once per site; demos reuse it |
| First demo type | browsing and filtering listings; product pages later |
| Sites | public only; logins next |
| First test sites | Allbirds (target sentence), plus Everlane, Gymshark, Nike for generality (all load in the test browser) |
| Bot-protected sites | detect and stop; never evade |
| Menus in a demo | opened **on camera** (click or hover), then the item clicked: the viewer sees where things are. Never jump straight to a URL to skip the navigation |
| How a demo ends | showcasing the result: scroll the listing, highlight two or three items, narration names them |

## Map format

The explored map uses the source-code map's shape, so `index.route_for`, `index.summary` and `jev_drive` read it
unchanged, plus optional keys only the explorer writes:

```json
{
  "/collections/:handle": {
    "file": "explored: https://www.allbirds.com/collections/mens",
    "links": [{"label": "Men", "to": "/collections/mens"}],
    "buttons": [{"label": "Filter", "submit": false}],
    "fields": ["Min price", "Max price"],
    "texts": ["Sustainable Men's Shoes"],
    "submits": false,
    "kind": "listing",
    "filters": [
      {"group": "Product Type", "kind": "checkbox", "param": "filter.p.m.allbirds_v2.category_subtypes",
       "values": ["Everyday Sneakers", "Running Shoes", "..."]},
      {"group": "Price", "kind": "range", "param": ["filter.v.price.gte", "filter.v.price.lte"]}
    ],
    "sort": {"param": "sort_by", "options": ["Featured", "Price, low to high", "..."]},
    "examples": ["/collections/mens", "/collections/womens"]
  },
  "_site": {"start": "https://www.allbirds.com/", "explored_at": "2026-10-26T20:00:00Z",
            "menus": [{"opener": "Men", "opens_on": "hover", "items": [{"label": "Shoes", "to": "/collections/mens"}]}],
            "popups": [{"seen_on": "/", "cleared_by": "escape"}],
            "blocked": null}
}
```

`_site` holds site-wide facts (menus are shared across pages); routes keep the existing keys. `summary()` should add
filter groups for listing routes, so Jev sees "→ /collections/mens: listing | filters: Product Type, Price, Size" when
choosing where to go.

## How exploring works (proposed; details are the builder's call)

1. **Open and check for a block.** Load the start URL; if the page reads as a bot check ("Access Denied", captcha,
   "verify you are human") or shows almost no content, write `_site.blocked` and stop with a message.
2. **Clear pop-ups** on every new page before reading it: Escape first (it cleared Everlane's, which sits in a
   third-party frame); if the page is still covered, Jev picks the pop-up's close / "no thanks" control from the visible
   controls (Allbirds' did not close on Escape; its × is visible). Never type, never submit. Record what worked.
3. **Read the navigation:** top-level links, then each menu opener, revealed by click or by hover (Nike's category menu
   is the hover case to test). Record each menu's items and destinations. Menu openers didn't report themselves as
   menus (`aria-expanded`) on any of the four sites, so detection can't rely on that alone.
4. **Group URLs into templates:** same path shape, one varying segment → one route with `:param`
   (`/collections/mens`, `/collections/womens` → `/collections/:handle`). Visit one or two examples per template.
5. **Read listing pages:** filter groups, values and sort options from the page (labels, headings, form controls). If a
   filter's URL form isn't readable from the control (Shopify's input names give it directly), apply one value, read the
   URL, and go back.
6. **Budget:** a page limit and a time limit (proposed: 40 pages, 5 minutes), same site only, guards on.

## How demos use the map (changes to the map-driven driver)

- **Menus on camera:** when the screen a demo needs is inside a menu (`_site.menus`), the driver opens the menu the way
  the site does (click, or hover for menus like Nike's) with the opener outlined, then clicks the item. The menu's items
  are offered to Jev as options of the opener ("Men → opens: Shoes, Running…"). Hover is needed in the driver, not only
  in the explorer.
- **Pop-up clearing** before each screen, as while exploring.
- **Filters:** on a listing screen, the map tells Jev which filter groups and values exist ("Running Shoes" under
  Product Type, a Price max box), so it picks real controls instead of guessed labels. Price boxes are filled like form
  fields. Filter checkboxes must not count as "changes data": today `--dry-run` would stop at the first one.
- **Showcase ending:** on reaching the goal's listing, scroll through it and highlight two or three items, as the
  URL-only driver's read step does today (it extracts items and pans the camera to them), so the narration can name them.
- **Verification (builder check, my call):** runs on explored maps must pass the final-screen check (Clef + screenshot,
  0.75); where the map knows a filter's URL form, the URL must agree too (`filter.v.price.lte=100` present). Runs on
  source-code maps keep today's text check until saas-starter is re-measured, so its 5 of 5 isn't changed unseen.
- **Fallback:** a screen not in the map → plan from what is visible, as the URL-only driver does today, and log that the
  map didn't know it.

## Done when

1. The Allbirds sentence, driven from an explored map, verifies in at least 4 of 5 runs **with `--fresh`** (so the
   pop-up appears and is cleared each time), opening the Men menu on camera and ending on men's running shoes at or
   under $100 with two or three highlighted, the screenshot check agreeing.
2. `explore` on Everlane, Gymshark and Nike writes maps with their menus, at least one listing template each with its
   filters, and no site-specific code; Nike's menus are found even though they open on hover.
3. `explore` on a bot-protected site (Zara) stops within seconds with a clear message and an empty map.
4. Exploring a site takes at most the time budget; the map file is small enough to read (tens of KB).
5. Offline tests cover template grouping, filter reading, pop-up clearing decisions and the map format, from saved
   page snapshots, with no browser or network.

## Settled after the builder check (my calls)

- `explore` runs in its own browser context (`Target.createBrowserContext`), so the cookies it collects (a closed
  pop-up) don't hide pop-ups from later demos.
- A filter whose URL form isn't a query parameter (Nike likely encodes filters in the path) is recorded with its group
  and values and `param: null`; that counts as mapped for Done 2, and no URL check is made for it.
- Filter values for a template come from the examples reached through the menus, merged.
- A screen not in the map: carry on as `jev_drive` does today ("unknown screen") and log it.
- `--dry-run` must not treat filter controls (and a filter panel's "Apply") as data-changing (`guards.would_change`).

## Left to the builder

Exact budgets; how to tell a listing page from other pages; template-grouping rules beyond the one-varying-segment case;
how hover is performed (CDP mouse move); the module layout (a new `src/jev_demofast/explore/` package is the natural
home); whether Nemotron names or summarises screens; snapshot fixtures for tests.

## Evidence

- Recon, 8 sites, home page only, test browser: Allbirds, Everlane, Gymshark, Nike load; Zara, H&M, ASOS, Uniqlo
  "Access Denied". Allbirds and Everlane open newsletter pop-ups that hide the page from the tool (0 elements seen).
  Escape cleared Everlane's (0 → 27 elements), not Allbirds'.
- URL shapes: Shopify sites `/collections/<handle>`, `/products/<handle>`; Nike `/w/…` (listings), `/t/…` (products).
- Baseline, Allbirds sentence, URL-only driver: 0 of 2, stuck at the first step behind the pop-up.
