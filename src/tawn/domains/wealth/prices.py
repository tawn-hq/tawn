"""NGX price sources. Public market data only — no credentials, ever.

The NGX endpoint is unofficial and may change shape; that's why every
path through here degrades to the manual prices in holdings.yaml.
"""

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from tawn.domains.wealth.holdings import EquityPosition

NGX_EQUITIES_URL = (
    "https://doclib.ngxgroup.com/REST/api/statistics/equities/"
    "?market=&sector=&orderby=&pageSize=300&pageNo=0"
)

#: Stooq free quotes — keyless CSV endpoint for US (and world) equities.
STOOQ_URL = "https://stooq.com/q/l/"


class PriceSource(Protocol):
    name: str

    def get_prices(self, tickers: list[str]) -> dict[str, Decimal]: ...


class ManualPrices:
    name = "manual"

    def __init__(self, positions: list[EquityPosition]):
        self._prices = {p.ticker: p.price for p in positions if p.price is not None}

    def get_prices(self, tickers: list[str]) -> dict[str, Decimal]:
        return {t: self._prices[t] for t in tickers if t in self._prices}


class StooqPriceSource:
    """US equities via stooq.com — public data, no key, batched CSV."""

    name = "stooq"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=10.0)

    def get_prices(self, tickers: list[str]) -> dict[str, Decimal]:
        if not tickers:
            return {}
        symbols = "+".join(f"{t.lower()}.us" for t in tickers)
        resp = self._client.get(
            STOOQ_URL, params={"s": symbols, "f": "sd2t2ohlcv", "h": "", "e": "csv"}
        )
        resp.raise_for_status()
        out: dict[str, Decimal] = {}
        for row in csv.DictReader(io.StringIO(resp.text)):
            symbol = (row.get("Symbol") or "").removesuffix(".US")
            try:
                out[symbol] = Decimal(row["Close"])
            except (InvalidOperation, KeyError, TypeError):
                continue  # N/D row — unknown ticker or no data
        return out


class NgxPriceSource:
    name = "ngx"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=10.0)

    def get_prices(self, tickers: list[str]) -> dict[str, Decimal]:
        resp = self._client.get(NGX_EQUITIES_URL)
        resp.raise_for_status()
        wanted = set(tickers)
        out: dict[str, Decimal] = {}
        for row in resp.json():
            symbol = row.get("Symbol")
            close = row.get("ClosePrice")
            if symbol in wanted and close is not None:
                out[symbol] = Decimal(str(close))
        return out


def fetch_or_fallback(
    source: PriceSource, fallback: PriceSource, tickers: list[str]
) -> tuple[dict[str, Decimal], str]:
    """Primary first; fill gaps (or total failure) from the fallback."""
    try:
        prices = source.get_prices(tickers)
    except Exception:
        prices = {}
    missing = [t for t in tickers if t not in prices]
    if not missing:
        return prices, source.name
    filled = fallback.get_prices(missing)
    prices.update(filled)
    if not prices or all(t in filled for t in tickers):
        return prices, fallback.name
    return prices, f"{source.name}+{fallback.name}"
