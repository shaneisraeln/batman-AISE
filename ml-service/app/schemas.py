"""Request / response schemas for the ML inference API."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, field_validator

from app.preprocessing import N_FEATURES


class PredictRequest(BaseModel):
    # A batch of samples, each a vector of N_FEATURES real values.
    instances: List[List[float]] = Field(
        ..., description=f"List of samples, each with {N_FEATURES} numeric features."
    )

    @field_validator("instances")
    @classmethod
    def check_shape(cls, v):
        if not v:
            raise ValueError("instances must be a non-empty list")
        for i, row in enumerate(v):
            if len(row) != N_FEATURES:
                raise ValueError(
                    f"instance {i} has {len(row)} features, expected {N_FEATURES}"
                )
        return v


class PredictResponse(BaseModel):
    predictions: List[int]
    labels: List[str]
    probabilities: List[List[float]]
    model_version: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    n_features: int
