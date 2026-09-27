"""Dataclasses for BATMAN persistence entities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class User:
    user_id: str
    email: str
    password_hash: str
    display_name: str | None
    status: str
    created_at: str


@dataclass
class Project:
    project_id: str
    user_id: str
    name: str
    environment: str  # development | staging | production
    created_at: str


@dataclass
class Model:
    model_id: str
    project_id: str
    user_id: str
    name: str
    status: str
    created_at: str


@dataclass
class UpstreamConfig:
    model_id: str
    user_id: str
    project_id: str
    url: str
    method: str = "POST"
    predict_path: str = "/predict"
    request_format: str = "instances"   # how to wrap inputs
    response_format: str = "predictions"  # how to read predictions
    auth_type: str = "none"             # none | bearer | header | basic
    auth_secret_enc: str | None = None  # ENCRYPTED upstream credential
    auth_header_name: str | None = None  # header name when auth_type == "header"
    timeout_s: float = 15.0
    created_at: str = ""
    updated_at: str | None = None
