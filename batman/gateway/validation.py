"""Input validation. Treats all client input as untrusted.

Validation failures are surfaced as security events (INVALID_REQUEST) rather
than opaque 500s.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MAX_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5 MB default cap


@dataclass
class ValidationConfig:
    expected_dim: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    allow_nan: bool = False
    allow_inf: bool = False
    max_payload_bytes: int = MAX_PAYLOAD_BYTES


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    array: np.ndarray | None = None


def _estimate_payload_bytes(inputs) -> int:
    try:
        arr = np.asarray(inputs, dtype=float)
        return arr.nbytes
    except Exception:
        return len(str(inputs).encode("utf-8"))


def validate_request(inputs, config: ValidationConfig | None = None) -> ValidationResult:
    """Validate a raw inference payload.

    Checks: presence, type coercion, dimensions, payload size, NaN/Inf,
    and configurable value bounds.
    """
    config = config or ValidationConfig()
    errors: list[str] = []

    if inputs is None:
        return ValidationResult(ok=False, errors=["missing_input"])

    # Payload size guard before heavy coercion.
    if _estimate_payload_bytes(inputs) > config.max_payload_bytes:
        return ValidationResult(ok=False, errors=["payload_too_large"])

    # Type coercion to a numeric 2D array (rows = samples, cols = features).
    try:
        arr = np.asarray(inputs, dtype=float)
    except (ValueError, TypeError):
        return ValidationResult(ok=False, errors=["non_numeric_input"])

    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    elif arr.ndim != 2:
        errors.append("bad_dimensionality")

    if arr.size == 0:
        errors.append("empty_input")

    # NaN / Inf.
    nan_count = int(np.isnan(arr).sum()) if arr.size else 0
    inf_count = int(np.isinf(arr).sum()) if arr.size else 0
    if nan_count and not config.allow_nan:
        errors.append(f"nan_values:{nan_count}")
    if inf_count and not config.allow_inf:
        errors.append(f"inf_values:{inf_count}")

    # Feature dimension.
    if config.expected_dim is not None and arr.ndim == 2:
        if arr.shape[1] != config.expected_dim:
            errors.append(
                f"dimension_mismatch:expected_{config.expected_dim}_got_{arr.shape[1]}"
            )

    # Value bounds (ignore NaN/Inf here to avoid double-reporting).
    finite = arr[np.isfinite(arr)] if arr.size else arr
    if finite.size:
        if config.min_value is not None and finite.min() < config.min_value:
            errors.append("value_below_min")
        if config.max_value is not None and finite.max() > config.max_value:
            errors.append("value_above_max")

    if errors:
        return ValidationResult(ok=False, errors=errors, array=arr)
    return ValidationResult(ok=True, errors=[], array=arr)
