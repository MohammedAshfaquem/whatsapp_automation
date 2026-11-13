import pytest

@pytest.mark.django_db
def test_swagger_ui_endpoint(client):
    response = client.get('/api/docs/')
    assert response.status_code == 200
    assert b"swagger-ui" in response.content.lower()

@pytest.mark.django_db
def test_openapi_schema_endpoint(client):
    response = client.get('/api/schema/')
    assert response.status_code == 200
    assert "application/vnd.oai.openapi" in response['Content-Type'] or "application/yaml" in response['Content-Type'] or "text/yaml" in response['Content-Type']
