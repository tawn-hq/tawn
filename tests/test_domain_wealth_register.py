from tawn.domains.wealth import register


def test_wealth_registers_with_cli_and_router():
    spec = register()
    assert spec.name == "wealth"
    assert spec.label == "Wealth"
    assert spec.cli is not None
    assert spec.api_router is not None
    assert spec.nav is True
