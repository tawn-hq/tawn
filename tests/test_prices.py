from decimal import Decimal

import httpx
import respx

from tawn.domains.wealth.holdings import Holdings
from tawn.domains.wealth.prices import (
    NGX_EQUITIES_URL,
    STOOQ_URL,
    ManualPrices,
    NgxPriceSource,
    StooqPriceSource,
    fetch_or_fallback,
)

HOLDINGS = Holdings.model_validate(
    {
        "fx_usdngn": 1650,
        "ngx": [
            {"ticker": "GTCO", "units": 1000, "price": "44.00"},
            {"ticker": "MTNN", "units": 50, "price": "210.00"},
        ],
        "us": [
            {"ticker": "AAPL", "units": 2, "price": "180.00"},
        ],
    }
)


def test_manual_prices_come_from_positions():
    prices = ManualPrices(HOLDINGS.ngx).get_prices(["GTCO", "MTNN"])
    assert prices == {"GTCO": Decimal("44.00"), "MTNN": Decimal("210.00")}
    assert ManualPrices(HOLDINGS.us).get_prices(["AAPL"]) == {"AAPL": Decimal("180.00")}


@respx.mock
def test_stooq_source_parses_close_prices():
    csv = (
        "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
        "AAPL.US,2026-07-07,22:00:00,210.0,212.0,208.0,211.45,1000000\n"
        "MSFT.US,2026-07-07,22:00:00,500.0,505.0,498.0,503.10,900000\n"
    )
    respx.get(url__startswith=STOOQ_URL).mock(return_value=httpx.Response(200, text=csv))
    prices = StooqPriceSource().get_prices(["AAPL", "MSFT"])
    assert prices["AAPL"] == Decimal("211.45")
    assert prices["MSFT"] == Decimal("503.10")


@respx.mock
def test_stooq_skips_no_data_rows():
    csv = (
        "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
        "AAPL.US,2026-07-07,22:00:00,210.0,212.0,208.0,211.45,1000000\n"
        "NOPE.US,N/D,N/D,N/D,N/D,N/D,N/D,N/D\n"
    )
    respx.get(url__startswith=STOOQ_URL).mock(return_value=httpx.Response(200, text=csv))
    prices = StooqPriceSource().get_prices(["AAPL", "NOPE"])
    assert prices == {"AAPL": Decimal("211.45")}


@respx.mock
def test_ngx_source_parses_close_prices():
    respx.get(NGX_EQUITIES_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"Symbol": "GTCO", "ClosePrice": 45.2},
                {"Symbol": "MTNN", "ClosePrice": 212.5},
                {"Symbol": "OTHER", "ClosePrice": 1.0},
            ],
        )
    )
    prices = NgxPriceSource().get_prices(["GTCO", "MTNN"])
    assert prices["GTCO"] == Decimal("45.2")
    assert prices["MTNN"] == Decimal("212.5")
    assert "OTHER" not in prices


@respx.mock
def test_fetch_or_fallback_survives_network_failure():
    respx.get(NGX_EQUITIES_URL).mock(side_effect=httpx.ConnectError("offline"))
    prices, source = fetch_or_fallback(
        NgxPriceSource(), ManualPrices(HOLDINGS.ngx), ["GTCO", "MTNN"]
    )
    assert source == "manual"
    assert prices["GTCO"] == Decimal("44.00")


@respx.mock
def test_fetch_or_fallback_fills_missing_tickers_from_manual():
    respx.get(NGX_EQUITIES_URL).mock(
        return_value=httpx.Response(200, json=[{"Symbol": "GTCO", "ClosePrice": 45.2}])
    )
    prices, source = fetch_or_fallback(
        NgxPriceSource(), ManualPrices(HOLDINGS.ngx), ["GTCO", "MTNN"]
    )
    assert prices["GTCO"] == Decimal("45.2")   # fetched
    assert prices["MTNN"] == Decimal("210.00")  # manual fill
    assert source == "ngx+manual"
