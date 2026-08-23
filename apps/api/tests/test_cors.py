from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


VERCEL_PREVIEW_ORIGIN_REGEX = r"^https://recon-mate-slice-[a-z0-9]+-boiitsvinnys-projects\.vercel\.app$"


def _cors_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://recon-mate-slice.vercel.app"],
        allow_origin_regex=VERCEL_PREVIEW_ORIGIN_REGEX,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_cors_allows_stable_and_project_preview_origins() -> None:
    client = _cors_client()
    for origin in (
        "https://recon-mate-slice.vercel.app",
        "https://recon-mate-slice-5kxvgpx7p-boiitsvinnys-projects.vercel.app",
        "https://recon-mate-slice-f6rkuw26o-boiitsvinnys-projects.vercel.app",
    ):
        response = _preflight(client, origin)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unrelated_vercel_origins() -> None:
    response = _preflight(_cors_client(), "https://unrelated-project.vercel.app")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
