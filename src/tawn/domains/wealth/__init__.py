"""Wealth domain — read-only, always (PRD §9)."""

from tawn.domains.base import DomainSpec


def register() -> DomainSpec:
    from tawn.domains.wealth.api import router
    from tawn.domains.wealth.cli import wealth_app

    return DomainSpec(name="wealth", label="Wealth", cli=wealth_app, api_router=router, nav=True)

