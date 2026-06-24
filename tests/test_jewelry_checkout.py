import pytest
from fastapi import HTTPException

from app.api.v1.payments import _jewelry_product, _normalize_jewelry_source_page_path


def test_jewelry_product_catalog_has_discounted_checkout_amounts():
    assert _jewelry_product("swarovski-annual-snowflake").unit_amount_cents == 187500
    assert _jewelry_product("swarovski-sorcerer-mickey").unit_amount_cents == 18000
    assert _jewelry_product("christian-dior-necklace").unit_amount_cents == 42000


def test_swan_pin_set_is_visible_but_not_purchasable_until_priced():
    product = _jewelry_product("swarovski-swan-pin-set")
    assert product.label == "Swarovski Swan Crystal Pin Set"
    assert product.unit_amount_cents is None


def test_unknown_jewelry_product_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _jewelry_product("unknown-product")
    assert exc.value.status_code == 400


def test_jewelry_source_page_stays_on_matching_product_routes():
    assert (
        _normalize_jewelry_source_page_path("/jewelry/swarovski-sorcerer-mickey", "swarovski-sorcerer-mickey")
        == "/jewelry/swarovski-sorcerer-mickey"
    )
    assert (
        _normalize_jewelry_source_page_path("/white/jewelry/swarovski-sorcerer-mickey", "swarovski-sorcerer-mickey")
        == "/white/jewelry/swarovski-sorcerer-mickey"
    )
    assert (
        _normalize_jewelry_source_page_path("/hollywood-sports", "swarovski-sorcerer-mickey")
        == "/jewelry/swarovski-sorcerer-mickey"
    )
