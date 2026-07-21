from fastapi import APIRouter
import typer

from tawn.domains.base import DomainSpec, mediated_fs


def test_domain_spec_defaults():
    spec = DomainSpec(name="wealth", label="Wealth")
    assert spec.cli is None
    assert spec.api_router is None
    assert spec.nav is True


def test_domain_spec_with_cli_and_router():
    app = typer.Typer()
    router = APIRouter()
    spec = DomainSpec(name="work", label="Work", cli=app, api_router=router, nav=False)
    assert spec.cli is app
    assert spec.api_router is router
    assert spec.nav is False


def test_mediated_fs_uses_tawn_home(tawn_home, monkeypatch):
    from tawn.capability.grants import DEFAULT_GRANTS_YAML
    from tawn.capability.integrity import confirm

    tawn_home.mkdir(parents=True, exist_ok=True)
    grants_path = tawn_home / "grants.yaml"
    grants_path.write_text(DEFAULT_GRANTS_YAML)
    confirm(grants_path)

    fs = mediated_fs(tawn_home)
    assert fs.home == tawn_home.resolve()
