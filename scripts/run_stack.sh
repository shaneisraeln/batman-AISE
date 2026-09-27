#!/usr/bin/env bash
# One-command local startup for the BATMAN Phase-1 real stack (Unix).
#
#   ml-service (:9000)  ->  BATMAN gateway (:8000, proxy + breast-cancer detector)
#
# Usage:  ./scripts/run_stack.sh    (Ctrl+C stops both)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

cd "$ROOT"
echo "[batman] ensuring models exist..."
if [ ! -f "models/isolation_forest_breast_cancer.joblib" ]; then
  "$PY" -m training.prepare
  "$PY" -m training.train --dataset breast_cancer
fi
if [ ! -f "ml-service/model/model.joblib" ]; then
  (cd ml-service && "$PY" -m app.train)
fi

echo "[batman] starting ML service on :9000 ..."
(cd ml-service && "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 9000) &
ML_PID=$!
sleep 4

echo "[batman] starting BATMAN gateway on :8000 (proxy -> :9000) ..."
BATMAN_PROTECTED_MODEL_URL="http://127.0.0.1:9000" \
BATMAN_DETECTOR_PATH="models/isolation_forest_breast_cancer.joblib" \
"$PY" -m uvicorn batman.gateway.app:app --host 127.0.0.1 --port 8000 &
GW_PID=$!

trap 'echo "[batman] stopping..."; kill $ML_PID $GW_PID 2>/dev/null || true' INT TERM
echo ""
echo "[batman] stack up."
echo "  ML service : http://127.0.0.1:9000/health"
echo "  BATMAN     : http://127.0.0.1:8000/v1/health"
wait
