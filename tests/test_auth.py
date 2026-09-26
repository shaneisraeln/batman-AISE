from batman.gateway.auth import (
    APIKeyStore,
    AuthError,
    KEY_PREFIX,
    generate_api_key,
    hash_key,
    verify_key_hash,
)
from batman.telemetry.store import TelemetryStore
import pytest


def test_generated_key_has_prefix_and_is_random():
    k1 = generate_api_key()
    k2 = generate_api_key()
    assert k1.startswith(KEY_PREFIX)
    assert k1 != k2


def test_hash_and_constant_time_verify():
    raw = generate_api_key()
    h = hash_key(raw)
    assert h != raw  # never store raw
    assert verify_key_hash(raw, h) is True
    assert verify_key_hash("bm_live_wrong", h) is False


def test_authenticate_lifecycle(tmp_db):
    store = TelemetryStore(tmp_db)
    ks = APIKeyStore(store)
    raw, record = ks.create_key("proj", "model")
    got = ks.authenticate(raw)
    assert got.project_id == "proj"
    assert got.model_id == "model"

    # Revoke -> auth fails.
    assert ks.revoke(record.key_id) is True
    with pytest.raises(AuthError):
        ks.authenticate(raw)
    store.close()


def test_unknown_and_malformed_keys(tmp_db):
    store = TelemetryStore(tmp_db)
    ks = APIKeyStore(store)
    with pytest.raises(AuthError):
        ks.authenticate("not_a_key")
    with pytest.raises(AuthError):
        ks.authenticate("bm_live_deadbeef")
    store.close()
