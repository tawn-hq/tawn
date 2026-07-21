from tawn.domains.base import DomainSpec
from tawn.domains.records import Collection, Field, record_domain


def register() -> DomainSpec:
    return record_domain(
        "hobby",
        "Hobby",
        collections=[
            Collection(
                name="activities",
                label="Activities",
                fields=[Field("name"), Field("date"), Field("duration"), Field("notes")],
            ),
        ],
    )
