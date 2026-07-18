from decimal import Decimal

import pytest
from typer.testing import CliRunner

from tawn.capability.audit import AuditLog
from tawn.capability.fs import MediatedFS
from tawn.capability.grants import Grants
from tawn.cli import app
from tawn.domains.wealth.holdings import (
    HOLDINGS_TEMPLATE,
    Holdings,
    holdings_path,
    load_holdings,
)

runner = CliRunner()

SAMPLE = """\
fx_usdngn: 1650
targets: {ngx: 40, usd: 30, land: 20, cash: 10}
ngx:
  - {ticker: GTCO, units: 1000, price: 45.20}
usd:
  - {name: usd savings, value_usd: 1200}
land:
  - {name: epe plot, value_ngn: 3500000}
cash:
  - {name: gtb current, value_ngn: 250000}
"""


def _fs(home):
    return MediatedFS(Grants.deny_all(), AuditLog(home / "audit.log"), home=home)


def test_load_holdings_parses_decimals(tawn_home):
    p = holdings_path(tawn_home)
    p.parent.mkdir(parents=True)
    p.write_text(SAMPLE)
    h = load_holdings(_fs(tawn_home), tawn_home)
    assert h.fx_usdngn == Decimal("1650")
    assert h.ngx[0].units == Decimal("1000")
    assert h.ngx[0].price == Decimal("45.20")
    assert h.targets["ngx"] == Decimal("40")


def test_missing_holdings_raises_with_hint(tawn_home):
    with pytest.raises(FileNotFoundError, match="tawn wealth init"):
        load_holdings(_fs(tawn_home), tawn_home)


def test_wealth_init_writes_template_once(tawn_home):
    runner.invoke(app, ["init"])
    first = runner.invoke(app, ["wealth", "init"])
    assert first.exit_code == 0, first.output
    p = holdings_path(tawn_home)
    assert p.exists()
    p.write_text(SAMPLE)  # user customizes
    second = runner.invoke(app, ["wealth", "init"])
    assert second.exit_code == 0
    assert p.read_text() == SAMPLE  # never clobbered


def test_template_is_loadable(tawn_home):
    p = holdings_path(tawn_home)
    p.parent.mkdir(parents=True)
    p.write_text(HOLDINGS_TEMPLATE)
    h = load_holdings(_fs(tawn_home), tawn_home)
    assert isinstance(h, Holdings)
    assert sum(h.targets.values()) == Decimal(100)
