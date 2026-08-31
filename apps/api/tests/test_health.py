from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.main import app
from app.api.routes.health import readiness_check


def test_health_check_returns_api_status() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "reconmate-api"}


class ReadySession:
    def execute(self, statement):
        assert "communication_consent_status" in str(statement)


class MissingSchemaSession:
    def execute(self, _statement):
        raise SQLAlchemyError("required column is missing")


def test_readiness_checks_required_customer_schema() -> None:
    result = readiness_check(ReadySession())  # type: ignore[arg-type]
    assert result.database == "ok"


def test_readiness_fails_closed_for_incomplete_schema() -> None:
    try:
        readiness_check(MissingSchemaSession())  # type: ignore[arg-type]
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "schema migration is incomplete" in exc.detail
    else:
        raise AssertionError("Readiness must reject an incomplete database schema.")
