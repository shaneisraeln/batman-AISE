"""batman-ml — lightweight Python client for BATMAN.

Runtime security for ML inference APIs: behavioral detection of anomalous
behavior, abusive traffic, and systematic model probing, with policy-based
enforcement.

Quick start::

    from batman_ml import protect

    protected = protect(api_key="bm_live_xxx", base_url="https://api.batman.example")
    prediction = protected.predict(X)

Or use the client directly for full decisions::

    from batman_ml import BatmanClient

    client = BatmanClient(api_key="bm_live_xxx")
    result = client.predict(X)
    print(result.action, result.threat_type, result.prediction)
"""

from batman_ml._version import __version__
from batman_ml.client import BatmanClient, PredictionResult, ProtectedModel, protect
from batman_ml.errors import (
    AuthenticationError,
    AuthorizationError,
    BatmanError,
    BlockedError,
    ConnectionError,
    RateLimitedError,
    ServerError,
    TimeoutError,
    UpstreamError,
    ValidationError,
)

__all__ = [
    "__version__",
    "protect",
    "BatmanClient",
    "ProtectedModel",
    "PredictionResult",
    "BatmanError",
    "AuthenticationError",
    "AuthorizationError",
    "BlockedError",
    "RateLimitedError",
    "ValidationError",
    "UpstreamError",
    "ConnectionError",
    "TimeoutError",
    "ServerError",
]
