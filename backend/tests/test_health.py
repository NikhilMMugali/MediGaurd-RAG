def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_and_api_metadata_use_the_official_project_name(client):
    assert client.get("/health").json()["service"] == "MediGuard RAG backend"
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "MediGuard RAG"
