"""Daily Close tool HTTP endpoints for local browser testing."""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.errors import ErrorCode, MCPError
from app.models.schemas import build_success_response
from src.tools.daily_close.close_pos_session import execute as close_pos_session_execute
from src.tools.daily_close.detect_anomalies import execute as detect_anomalies_execute
from src.tools.daily_close.get_pos_transactions import execute as get_pos_transactions_execute
from src.tools.daily_close.validate_pos_totals import execute as validate_pos_totals_execute

router = APIRouter(prefix="/tools/daily_close", tags=["Daily Close Tools"])


class DailyCloseBaseInput(BaseModel):
    date: str = Field(description="Business date in YYYY-MM-DD format")
    tenant_id: str = Field(default="daily-close-local")


class GetPOSTransactionsInput(DailyCloseBaseInput):
    pos_profile: str | None = None


class ClosePOSSessionInput(DailyCloseBaseInput):
    force_close: bool = False


@router.post("/get_pos_transactions")
async def get_pos_transactions(input_data: GetPOSTransactionsInput) -> dict:
    start = time.time()
    try:
        data = get_pos_transactions_execute(date=input_data.date, pos_profile=input_data.pos_profile)
    except RuntimeError as exc:
        raise MCPError(ErrorCode.VALIDATION_ERROR, str(exc)) from exc
    return build_success_response(
        tool="get_pos_transactions",
        tenant_id=input_data.tenant_id,
        data=data,
        execution_time_ms=int((time.time() - start) * 1000),
    )


@router.post("/validate_pos_totals")
async def validate_pos_totals(input_data: DailyCloseBaseInput) -> dict:
    start = time.time()
    try:
        data = validate_pos_totals_execute(date=input_data.date)
    except RuntimeError as exc:
        raise MCPError(ErrorCode.VALIDATION_ERROR, str(exc)) from exc
    return build_success_response(
        tool="validate_pos_totals",
        tenant_id=input_data.tenant_id,
        data=data,
        execution_time_ms=int((time.time() - start) * 1000),
    )


@router.post("/detect_anomalies")
async def detect_anomalies(input_data: DailyCloseBaseInput) -> dict:
    start = time.time()
    try:
        data = detect_anomalies_execute(date=input_data.date)
    except RuntimeError as exc:
        raise MCPError(ErrorCode.VALIDATION_ERROR, str(exc)) from exc
    return build_success_response(
        tool="detect_anomalies",
        tenant_id=input_data.tenant_id,
        data=data,
        execution_time_ms=int((time.time() - start) * 1000),
    )


@router.post("/close_pos_session")
async def close_pos_session(input_data: ClosePOSSessionInput) -> dict:
    start = time.time()
    try:
        data = close_pos_session_execute(date=input_data.date, force_close=input_data.force_close)
    except RuntimeError as exc:
        raise MCPError(ErrorCode.VALIDATION_ERROR, str(exc)) from exc
    return build_success_response(
        tool="close_pos_session",
        tenant_id=input_data.tenant_id,
        data=data,
        execution_time_ms=int((time.time() - start) * 1000),
    )
