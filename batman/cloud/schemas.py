"""Pydantic request/response models for the BATMAN cloud API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---- auth ----
class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"


# ---- projects ----
class CreateProjectRequest(BaseModel):
    name: str
    environment: str = "development"  # development | staging | production


# ---- models ----
class RegisterModelRequest(BaseModel):
    project_id: str
    name: str


# ---- keys ----
class CreateKeyRequest(BaseModel):
    project_id: str
    model_id: str
    name: str | None = None
    expires_at: str | None = None


# ---- upstream config ----
class UpstreamRequest(BaseModel):
    url: str
    method: str = "POST"
    predict_path: str = "/predict"
    request_format: str = "instances"       # instances | raw
    response_format: str = "predictions"     # predictions | raw
    auth_type: str = "none"                  # none | bearer | header
    auth_secret: str | None = None           # encrypted at rest; never returned
    auth_header_name: str | None = None      # for auth_type=header
    timeout_s: float = 15.0


# ---- data plane ----
class PredictRequest(BaseModel):
    inputs: Any
    session_id: str = "default"
    analyze_only: bool = False


# ---- analyst feedback (dashboard) ----
class FeedbackRequest(BaseModel):
    request_id: str
    label: str
    analyst_note: str = ""
