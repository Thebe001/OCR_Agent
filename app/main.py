"""Floravi MCP Server entry point."""

import time
from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.models.errors import ErrorCode, MCPError
from app.models.schemas import build_error_response
from app.services.erpnext_client import ERPNextClient
from app.tools import invoice_tools, item_tools, ocr_tools, supplier_tools

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("floravi-mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Floravi MCP Server starting")
    logger.info("Python executable: %s", sys.executable)
    if settings.app_env.lower() == "production" and settings.allowed_origins.strip() == "*":
        logger.warning("ALLOWED_ORIGINS is '*' in production. Restrict it before deploying.")
    yield
    await ERPNextClient.close_shared_client()
    logger.info("Floravi MCP Server stopping")


app = FastAPI(
    title="Floravi MCP Server",
    description="MCP tools for the Floravi Invoice OCR Agent.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} "
        f"({int((time.time() - start) * 1000)}ms)"
    )
    return response


@app.exception_handler(MCPError)
async def mcp_error_handler(request: Request, exc: MCPError):
    status_map = {
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.AUTH_ERROR: 401,
        ErrorCode.PERMISSION_ERROR: 403,
        ErrorCode.TENANT_ERROR: 404,
        ErrorCode.RATE_LIMIT: 429,
        ErrorCode.ERPNEXT_ERROR: 502,
        ErrorCode.AI_SERVICE_ERROR: 502,
        ErrorCode.ENTITLEMENT_ERROR: 403,
    }
    return JSONResponse(
        status_code=status_map.get(exc.code, 500),
        content=build_error_response(
            tool="unknown",
            tenant_id="unknown",
            code=exc.code.value,
            message=exc.message,
            details=exc.details if settings.debug else None,
            recoverable=exc.recoverable,
        ),
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=build_error_response(
            tool="unknown",
            tenant_id="unknown",
            code=ErrorCode.ERPNEXT_ERROR.value,
            message="An unexpected error occurred. Please try again later.",
            details=str(exc) if settings.debug else None,
        ),
    )


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "Floravi MCP Server",
        "status": "running",
        "version": "0.1.0",
        "environment": settings.app_env,
        "agent_ui": "/agent",
        "api_docs": "/docs",
    }


@app.get("/agent", include_in_schema=False)
async def agent_ui():
    return FileResponse("app/static/index.html")


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "debug": settings.debug,
        "erpnext_configured": bool(settings.erpnext_base_url),
        "ocr_configured": bool(settings.azure_ocr_endpoint),
        "ocr_provider": settings.ocr_provider,
        "default_tenant": settings.default_tenant_id,
        "tools_registered": 4,
    }


app.include_router(ocr_tools.router)
app.include_router(supplier_tools.router)
app.include_router(item_tools.router)
app.include_router(invoice_tools.router)
