# batman-ml

Lightweight Python client for **BATMAN** — runtime security for machine-learning
inference APIs.

BATMAN detects anomalous behavior, abusive traffic, and systematic model probing
across inference requests, and enforces policy (allow / rate-limit / block) in
front of your model. This package is the **client**: a thin HTTP wrapper with a
single dependency (`httpx`). It does not bundle the detection engine.

## Install

```bash
pip install batman-ml
```

## Quick start

```python
from batman_ml import protect

# Your model is registered with BATMAN in the dashboard; inference is routed
# through the BATMAN API to your protected upstream.
protected = protect(
    api_key="bm_live_xxxxx",
    base_url="https://api.your-batman.example",
)

prediction = protected.predict([[/* feature vector */]])
```

Need the full security decision, not just the prediction?

```python
from batman_ml import BatmanClient

client = BatmanClient(api_key="bm_live_xxxxx", base_url="https://api.your-batman.example")
result = client.predict(X)

print(result.action)        # ALLOW | LOG | RATE_LIMIT | BLOCK | ESCALATE
print(result.threat_type)   # NONE | MODEL_EXTRACTION | ANOMALOUS_INPUT | ...
print(result.prediction)    # your model's output (when allowed)
print(result.request_id)    # traceable in the dashboard
```

## Configuration

| Argument | Env var | Default |
|---|---|---|
| `api_key` | `BATMAN_API_KEY` | required |
| `base_url` | `BATMAN_BASE_URL` | `http://127.0.0.1:8000` |
| `timeout` | — | `30.0` seconds |
| `max_retries` | — | `2` (transient network/5xx) |
| `raise_on_block` | — | `False` |

The API key is sent only in the `x-api-key` header and is never logged or
included in exception messages or `repr()`.

## Errors

All errors derive from `BatmanError`:

- `AuthenticationError` — missing/invalid/revoked key (401)
- `AuthorizationError` — not permitted for the resource (403)
- `BlockedError` — blocked by policy (carries `.decision`)
- `RateLimitedError` — throttled (carries `.retry_after`)
- `ValidationError` — bad payload (400/422)
- `UpstreamError` — your protected model/API failed (502/504)
- `ConnectionError` / `TimeoutError` — could not reach BATMAN
- `ServerError` — unexpected 5xx

```python
from batman_ml import BatmanClient, BlockedError, RateLimitedError

client = BatmanClient(api_key="bm_live_xxx", raise_on_block=True)
try:
    result = client.predict(X)
except BlockedError as e:
    print("blocked:", e.decision.get("threat_type"))
except RateLimitedError as e:
    print("retry after", e.retry_after, "s")
```

## What this client is not

- It does **not** run the detector locally — detection happens server-side.
- It does **not** require numpy, scikit-learn, or any ML framework. (numpy arrays
  are accepted if you already use them.)
- It does **not** store or transmit your API key anywhere except the BATMAN API.

## License

MIT
