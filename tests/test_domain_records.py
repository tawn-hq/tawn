from typer.testing import CliRunner

from tawn.domains.records import Collection, Field, record_domain

runner = CliRunner()


def _work_domain(tawn_home):
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
        home=tawn_home,
    )


def test_add_then_list_within_one_collection(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    spec = _work_domain(tawn_home)
    result = runner.invoke(spec.cli, ["projects", "add", "--name", "tawn", "--status", "active"])
    assert result.exit_code == 0
    result = runner.invoke(spec.cli, ["projects", "list"])
    assert result.exit_code == 0
    assert "tawn" in result.output and "active" in result.output


def test_collections_have_independent_storage(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    spec = _work_domain(tawn_home)
    runner.invoke(spec.cli, ["projects", "add", "--name", "tawn", "--status", "active"])
    runner.invoke(
        spec.cli,
        ["tasks", "add", "--project", "tawn", "--title", "ship stage 3", "--status", "todo", "--due-date", "2026-08-01"],
    )
    projects_file = tawn_home / "domains" / "work" / "projects.jsonl"
    tasks_file = tawn_home / "domains" / "work" / "tasks.jsonl"
    assert projects_file.exists() and tasks_file.exists()
    import json

    assert json.loads(projects_file.read_text().strip()) == {"name": "tawn", "status": "active"}


def test_view_returns_one_table_section_per_collection(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    spec = _work_domain(tawn_home)
    runner.invoke(spec.cli, ["projects", "add", "--name", "tawn", "--status", "active"])

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(spec.api_router)
    client = TestClient(app)
    body = client.get("/view").json()
    assert body["title"] == "Work"
    # projects has a record → table; tasks has none → empty
    project_section = next(s for s in body["sections"] if s.get("columns") == ["name", "status"])
    assert project_section["rows"] == [["tawn", "active"]]
    empty_sections = [s for s in body["sections"] if s["type"] == "empty"]
    assert len(empty_sections) == 1  # tasks collection, no records yet


def test_domain_spec_shape():
    spec = _work_domain(None)
    assert spec.name == "work" and spec.label == "Work"
    assert spec.cli is not None and spec.api_router is not None
