"""Entity name and relation-label hygiene."""

import pytest

from tawn.compiler.hygiene import (
    is_junk_entity,
    normalize_entity_name,
    normalize_relation,
)


@pytest.mark.parametrize("name", [
    "127.0.0.1",
    "0x1f4a2b",
    "app/api/auth.py",
    "src/api/v1/optimize.py",
    "General #2bGFAdUX",
    "Food & Dining #oBNrLz4E",
    "12g",
    "3.14",
    "/usr/local/bin",
    "https://example.com/path",
])
def test_junk_is_rejected(name):
    assert is_junk_entity(name) is True


@pytest.mark.parametrize("name", [
    "Clara",
    "Justin Thacker",
    "Boyd Hill Nature Preserve",
    "gpt-4o-mini",
    "Open-Meteo",
    "NaijaReview",
    "PostgreSQL",
    "Gulf Animal Hospital",
])
def test_real_entities_are_kept(name):
    assert is_junk_entity(name) is False


def test_relation_normalisation_unifies_spellings():
    for variant in ("is located in", "located_in", "located in", "IS_LOCATED_IN", "Located In"):
        assert normalize_relation(variant) == "located in"


def test_relation_normalisation_strips_leading_copula():
    assert normalize_relation("is associated with") == "associated with"
    assert normalize_relation("associated_with") == "associated with"
    assert normalize_relation("are part of") == "part of"


def test_relation_normalisation_keeps_meaningful_verbs():
    assert normalize_relation("USES") == "uses"
    assert normalize_relation("sends reports to") == "sends reports to"
    assert normalize_relation("INTEGRATES_WITH") == "integrates with"


def test_relation_normalisation_handles_empty():
    assert normalize_relation("") == "related to"
    assert normalize_relation(None) == "related to"


def test_entity_name_normalisation_is_case_folding_key():
    assert normalize_entity_name("Uniswap") == normalize_entity_name("uniswap")
    assert normalize_entity_name("  eBay  ") == normalize_entity_name("EBAY")


def test_entity_name_normalisation_preserves_distinct_names():
    assert normalize_entity_name("Clara") != normalize_entity_name("Claire")
