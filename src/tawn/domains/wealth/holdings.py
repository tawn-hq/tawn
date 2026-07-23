"""The user's holdings file — the single wealth input for v0.

Lives inside the Tawn home (self-granted), read through MediatedFS.
All money is Decimal; floats are a defect.
"""

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from tawn.capability.fs import MediatedFS

HOLDINGS_TEMPLATE = """\
# ~/.tawn/domains/wealth/holdings.yaml — your positions, valued by `tawn wealth snapshot`.
# Read-only input: Tawn never edits this file; you do.
fx_usdngn: 1650          # manual USD→NGN rate for valuing usd + us classes
targets:                 # blueprint allocation, % of total (must sum to 100)
  ngx: 30
  us: 10
  usd: 25
  land: 25
  cash: 10
ngx:                     # Nigerian equities · price = NGN manual fallback
  - {ticker: GTCO, units: 0, price: 0}
us:                      # US equities · price = USD manual fallback
  - {ticker: AAPL, units: 0, price: 0}
usd:
  - {name: usd savings, value_usd: 0}
land:
  - {name: example plot, value_ngn: 0}
cash:
  - {name: main account, value_ngn: 0}
"""


class EquityPosition(BaseModel):
    ticker: str
    units: Decimal
    price: Decimal | None = None  # manual fallback (NGN for ngx, USD for us)


#: Back-compat alias; ngx and us positions share one shape.
NgxPosition = EquityPosition


class ValuedPosition(BaseModel):
    name: str
    value_usd: Decimal | None = None
    value_ngn: Decimal | None = None


class Holdings(BaseModel):
    fx_usdngn: Decimal
    targets: dict[str, Decimal] = Field(default_factory=dict)
    ngx: list[EquityPosition] = Field(default_factory=list)
    us: list[EquityPosition] = Field(default_factory=list)
    usd: list[ValuedPosition] = Field(default_factory=list)
    land: list[ValuedPosition] = Field(default_factory=list)
    cash: list[ValuedPosition] = Field(default_factory=list)


def holdings_path(home: Path) -> Path:
    return home / "domains" / "wealth" / "holdings.yaml"


def load_holdings(fs: MediatedFS, home: Path) -> Holdings:
    path = holdings_path(home)
    try:
        raw = fs.read_text(path)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"{path} not found — run `tawn wealth init` to create the template"
        )
    return Holdings.model_validate(yaml.safe_load(raw))
