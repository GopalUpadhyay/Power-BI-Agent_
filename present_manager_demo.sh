#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=============================================="
echo "Power BI Semantic Model AI Assistant - Demo"
echo "=============================================="

echo
echo "Step 1: Checking dependencies"
python - <<'PY'
import importlib
missing = []
for name in ["openai", "pandas", "pydantic"]:
  try:
    importlib.import_module(name)
  except Exception:
    missing.append(name)

if missing:
  print("Missing packages:", ", ".join(missing))
  print("Install them in your current environment before demo if needed.")
else:
  print("All required packages are available.")
PY

echo
echo "Step 2: Running end-to-end demo scenario"
python run_app.py --demo

echo
echo "Step 3: Next commands for live interaction"
echo "  python run_app.py --interactive"
echo
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Note: OPENAI_API_KEY is not set. Demo used fallback mode."
  echo "Set your key for AI mode:"
  echo "  export OPENAI_API_KEY='your-new-key'"
fi
