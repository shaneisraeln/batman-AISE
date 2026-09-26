import numpy as np

from batman.gateway.validation import ValidationConfig, validate_request


def test_valid_input_passes():
    res = validate_request([[1.0, 2.0, 3.0]])
    assert res.ok
    assert res.array.shape == (1, 3)


def test_missing_input_fails():
    res = validate_request(None)
    assert not res.ok and "missing_input" in res.errors


def test_nan_and_inf_rejected():
    res = validate_request([[1.0, np.nan, np.inf]])
    assert not res.ok
    assert any(e.startswith("nan") for e in res.errors)
    assert any(e.startswith("inf") for e in res.errors)


def test_dimension_mismatch():
    cfg = ValidationConfig(expected_dim=4)
    res = validate_request([[1.0, 2.0, 3.0]], cfg)
    assert not res.ok
    assert any("dimension_mismatch" in e for e in res.errors)


def test_value_bounds():
    cfg = ValidationConfig(min_value=0.0, max_value=10.0)
    res = validate_request([[1.0, 99.0]], cfg)
    assert not res.ok
    assert "value_above_min" not in res.errors
    assert "value_above_max" in res.errors


def test_non_numeric_rejected():
    res = validate_request([["a", "b"]])
    assert not res.ok and "non_numeric_input" in res.errors
