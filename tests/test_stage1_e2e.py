"""Stage 1 end-to-end: fresh install → holdings → snapshot → dashboard + web."""

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tawn.cli import app
from tawn.db import make_engine
from tawn.domains.wealth.holdings import holdings_path
from tawn.web import create_app

runner = CliRunner()

HOLDINGS = """\
fx_usdngn: 1000
targets: {ngx: 30, us: 10, usd: 30, land: 20, cash: 10}
ngx:
  - {ticker: GTCO, units: 100, price: 50}
us:
  - {ticker: AAPL, units: 1, price: 5}
usd:
  - {name: savings, value_usd: 10}
land:
  - {name: plot, value_ngn: 3000}
cash:
  - {name: bank, value_ngn: 2000}
"""


def test_full_wealth_flow(tawn_home, tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", f"sqlite+pysqlite:///{tmp_path}/tawn.db")

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["db", "setup"]).exit_code == 0
    assert runner.invoke(app, ["wealth", "init"]).exit_code == 0

    holdings_path(tawn_home).write_text(HOLDINGS)

    snap = runner.invoke(app, ["wealth", "snapshot", "--offline"])
    assert snap.exit_code == 0, snap.output
    assert "25000" in snap.output

    show = runner.invoke(app, ["wealth", "show"])
    assert show.exit_code == 0
    assert "25000" in show.output

    web = TestClient(create_app(make_engine()))
    assert web.get("/api/status").status_code == 200
    assert web.get("/api/domains").status_code == 200
