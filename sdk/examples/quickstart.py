"""batman-ml quickstart example.

Prereqs:
  - A running BATMAN API (Phase-1 gateway or hosted).
  - A BATMAN API key (bm_live_...), e.g. minted via POST /v1/keys.

Run:
    export BATMAN_API_KEY=bm_live_xxxxx
    export BATMAN_BASE_URL=http://127.0.0.1:8000
    python examples/quickstart.py
"""

from batman_ml import BatmanClient, BlockedError, RateLimitedError

# One feature vector for the demo Breast Cancer model (30 features).
SAMPLE = [[
    17.99, 10.38, 122.8, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.07871,
    1.095, 0.9053, 8.589, 153.4, 0.006399, 0.04904, 0.05373, 0.01587, 0.03003,
    0.006193, 25.38, 17.33, 184.6, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601,
    0.1189,
]]


def main() -> None:
    client = BatmanClient()  # reads BATMAN_API_KEY / BATMAN_BASE_URL
    print("health:", client.health())

    try:
        result = client.predict(SAMPLE, session_id="quickstart")
        print("action     :", result.action)
        print("threat_type:", result.threat_type)
        print("prediction :", result.prediction)
        print("request_id :", result.request_id)
    except BlockedError as e:
        print("BLOCKED:", e.decision.get("threat_type"))
    except RateLimitedError as e:
        print("RATE LIMITED, retry after", e.retry_after)
    finally:
        client.close()


if __name__ == "__main__":
    main()
