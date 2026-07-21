from tawn.domains.base import DomainSpec
from tawn.domains.records import Collection, Field, record_domain


def register() -> DomainSpec:
    return record_domain(
        "work",
        "Work",
        collections=[
            Collection(name="projects", label="Projects", fields=[Field("name"), Field("status")]),
            Collection(
                name="tasks",
                label="Tasks",
                fields=[Field("project"), Field("title"), Field("status"), Field("due_date")],
            ),
        ],
    )
