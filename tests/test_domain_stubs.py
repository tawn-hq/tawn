from typer.testing import CliRunner

from tawn.domains.stub import make_stub_domain

runner = CliRunner()


def test_stub_cli_reports_not_implemented():
    spec = make_stub_domain("work", "Work")
    result = runner.invoke(spec.cli, ["status"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output.lower()
    assert "stage 12" in result.output.lower()


def test_stub_view_endpoint_returns_empty_section():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    spec = make_stub_domain("research", "Research")
    app = FastAPI()
    app.include_router(spec.api_router)
    client = TestClient(app)
    resp = client.get("/view")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Research"
    assert body["sections"][0]["type"] == "empty"


def test_four_stub_modules_register():
    from tawn.domains.academic import register as academic_register
    from tawn.domains.hobby import register as hobby_register
    from tawn.domains.research import register as research_register
    from tawn.domains.work import register as work_register

    names = {register().name for register in (work_register, research_register, academic_register, hobby_register)}
    assert names == {"work", "research", "academic", "hobby"}
