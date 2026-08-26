from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.commands import router as commands_router
from app.api.routes.intelligence import router as intelligence_router
from app.api.routes.imports import router as imports_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.recovery import customer_recovery_router, router as recovery_router
from app.api.routes.workflow import router as workflow_router
from app.api.routes.simulation import router as simulation_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="ReconMate API",
    version="0.1.0",
    description="REST API for the ReconMate revenue recovery platform.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.api_cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(commands_router)
app.include_router(intelligence_router)
app.include_router(imports_router)
app.include_router(portfolio_router)
app.include_router(recovery_router)
app.include_router(workflow_router)
app.include_router(simulation_router)
app.include_router(customer_recovery_router)
