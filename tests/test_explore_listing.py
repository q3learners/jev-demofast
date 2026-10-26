"""A listing page's filters and sort are read from the page, including controls in closed filter panels."""
from jev_demofast.explore.listing import parse_listing


def boxes(name, labels, kind="checkbox"):
    return [{"type": kind, "name": name, "label": label} for label in labels]


SHOPIFY = {"item_links": 45, "groups": [
    {"heading": "Sort By", "controls": boxes("sort_by", ["Featured", "Best selling", "Price, low to high"], "radio")},
    {"heading": "Size", "controls": boxes("filter.p.m.x.category_sizes", ["8", "8.5", "9"])},
    {"heading": "Price", "controls": [{"type": "number", "name": "filter.v.price.gte", "label": "From"},
                                      {"type": "number", "name": "filter.v.price.lte", "label": "To"}]},
    {"heading": "Product Type", "controls": boxes("filter.p.m.x.category_subtypes",
                                                  ["Everyday Sneakers", "Running Shoes", "Slip Ons"])},
]}


def test_shopify_style_filters():
    listing = parse_listing(SHOPIFY)
    assert listing["kind"] == "listing"
    by_group = {f["group"]: f for f in listing["filters"]}
    assert by_group["Price"]["kind"] == "range"
    assert by_group["Price"]["param"] == ["filter.v.price.gte", "filter.v.price.lte"]
    assert by_group["Product Type"]["param"] == "filter.p.m.x.category_subtypes"
    assert "Running Shoes" in by_group["Product Type"]["values"]
    assert "Sort By" not in by_group
    assert listing["sort"] == {"param": "sort_by", "options": ["Featured", "Best selling", "Price, low to high"]}


def test_filters_without_url_names_are_kept_with_param_none():
    raw = {"item_links": 20, "groups": [{"heading": "Colour", "controls": boxes("", ["Black", "White"])}]}
    (f,) = parse_listing(raw)["filters"]
    assert f == {"group": "Colour", "kind": "checkbox", "param": None, "values": ["Black", "White"]}


def test_a_page_without_items_is_not_a_listing():
    assert parse_listing({**SHOPIFY, "item_links": 3})["kind"] == "page"


def test_a_page_full_of_items_but_no_filters_or_sort_is_not_a_listing():
    assert parse_listing({"item_links": 30, "groups": []})["kind"] == "page"


def test_product_card_swatches_are_not_filters():
    """Each product card's colour swatches are radios with no heading and one value: not a filter."""
    swatches = [{"heading": f"swatch-group-{n}", "controls": boxes(f"swatch-group-{n}", ["on"], "radio")}
                for n in (4870549274704, 7205207343184)]
    listing = parse_listing({**SHOPIFY, "groups": SHOPIFY["groups"] + swatches})
    assert not any(f["group"].startswith("swatch-group") for f in listing["filters"])
    assert len(listing["filters"]) == 3


def test_a_product_page_is_not_a_listing():
    """Live, Nike: a product page's size and colour pickers looked like filters. A page with an add-to-bag button is a
    product page."""
    raw = {**SHOPIFY, "add_to_cart": True}
    assert parse_listing(raw)["kind"] == "product"
