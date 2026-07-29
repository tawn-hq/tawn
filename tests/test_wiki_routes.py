import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tawn.memory.schema import Entity, EntityEdge
from tawn.web import create_app


def _client_for(db_engine):
    """Bind the app to the test engine.

    `Depends(get_session)` builds its own engine from settings, so without the
    override every request would hit the developer's real Postgres.
    """
    import tawn.db as db_mod

    def _get_session():
        with Session(db_engine) as s:
            yield s

    app = create_app(db_engine)
    app.dependency_overrides[db_mod.get_session] = _get_session
    return TestClient(app)


@pytest.fixture()
def client(tawn_home, db_engine):
    (tawn_home / "wiki" / "work").mkdir(parents=True)
    (tawn_home / "wiki" / "work" / "index.md").write_text("# Work\n\nSee [[Tawn]].")
    return _client_for(db_engine)


def test_tree_lists_domains(client):
    body = client.get("/api/wiki/tree").json()
    assert body["ready"] is True
    assert "work" in [d["name"] for d in body["domains"]]


def test_tree_not_ready_without_wiki(tawn_home, db_engine):
    body = _client_for(db_engine).get("/api/wiki/tree").json()
    assert body["ready"] is False


def test_page_returns_markdown(client):
    body = client.get("/api/wiki/page", params={"path": "work/index.md"}).json()
    assert "# Work" in body["content"]


def test_page_rejects_traversal(client):
    r = client.get("/api/wiki/page", params={"path": "../../../etc/passwd"})
    assert r.status_code in (400, 404)


def test_page_404_for_missing(client):
    r = client.get("/api/wiki/page", params={"path": "nope/index.md"})
    assert r.status_code == 404
    assert "compile" in r.json()["detail"].lower()


def test_entity_returns_related_and_backlinks(client, db_engine):
    with Session(db_engine) as s:
        a = Entity(canonical="ClauseWise", domain="work")
        b = Entity(canonical="pgvector", domain="work")
        s.add_all([a, b])
        s.flush()
        s.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id,
                         relation="uses", weight=2))
        s.commit()

    body = client.get("/api/wiki/entity/ClauseWise").json()
    assert body["canonical"] == "ClauseWise"
    assert body["related"][0]["label"] == "pgvector"
    assert body["related"][0]["relation"] == "uses"

    back = client.get("/api/wiki/entity/pgvector").json()
    assert back["backlinks"][0]["label"] == "ClauseWise"


def test_entity_404_when_unknown(client):
    assert client.get("/api/wiki/entity/NotThere").status_code == 404


def test_graph_returns_nodes_and_links(client, db_engine):
    with Session(db_engine) as s:
        a = Entity(canonical="A", domain="work")
        b = Entity(canonical="B", domain="work")
        s.add_all([a, b])
        s.flush()
        s.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id, relation="uses"))
        s.commit()

    body = client.get("/api/wiki/graph").json()
    assert len(body["nodes"]) == 2
    assert len(body["links"]) == 1


def test_graph_clusters_by_domain(client, db_engine):
    with Session(db_engine) as s:
        s.add_all([Entity(canonical="X", domain="work"),
                   Entity(canonical="Y", domain="research")])
        s.commit()

    body = client.get("/api/wiki/graph", params={"cluster": "true"}).json()
    counts = {c["domain"]: c["count"] for c in body["clusters"]}
    assert counts["work"] >= 1
    assert counts["research"] >= 1


def test_graph_scoped_to_entity_neighbourhood(client, db_engine):
    with Session(db_engine) as s:
        a = Entity(canonical="Root")
        b = Entity(canonical="Near")
        c = Entity(canonical="Far")
        s.add_all([a, b, c])
        s.flush()
        s.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id, relation="uses"))
        s.commit()

    body = client.get("/api/wiki/graph", params={"entity": "Root", "depth": 1}).json()
    labels = {n["label"] for n in body["nodes"]}
    assert labels == {"Root", "Near"}


def test_graph_empty_corpus(client):
    body = client.get("/api/wiki/graph").json()
    assert body["nodes"] == []
    assert body["links"] == []


def test_links_404_before_compile(client):
    assert client.get("/api/wiki/links").status_code == 404


def test_links_returns_generated_index(client, tawn_home):
    (tawn_home / "wiki" / "links.json").write_text('{"nodes": [], "links": []}')
    body = client.get("/api/wiki/links").json()
    assert body == {"nodes": [], "links": []}
