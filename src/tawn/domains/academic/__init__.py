from tawn.domains.base import DomainSpec
from tawn.domains.records import Collection, Field, record_domain


def register() -> DomainSpec:
    return record_domain(
        "academic",
        "Academic",
        collections=[
            Collection(name="courses", label="Courses", fields=[Field("name"), Field("status")]),
            Collection(
                name="assignments",
                label="Assignments",
                fields=[Field("course"), Field("title"), Field("due_date"), Field("status")],
            ),
            Collection(
                name="milestones",
                label="Milestones",
                fields=[Field("name"), Field("target_date"), Field("status")],
            ),
        ],
    )
