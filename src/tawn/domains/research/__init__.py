from tawn.domains.base import DomainSpec
from tawn.domains.records import Collection, Field, record_domain


def register() -> DomainSpec:
    return record_domain(
        "research",
        "Research",
        collections=[
            Collection(
                name="sources",
                label="Sources",
                fields=[Field("title"), Field("authors"), Field("status"), Field("notes")],
            ),
            Collection(
                name="experiments",
                label="Experiments",
                fields=[Field("hypothesis"), Field("method"), Field("outcome"), Field("date")],
            ),
        ],
    )
