#!/usr/bin/env bash
# SessionStart hook: in cloud sessions (CLAUDE_CODE_REMOTE=true), install the Python and web
# dependencies so tests and the CLI work from the first prompt. A no-op locally.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"

if command -v uv >/dev/null 2>&1; then
  uv sync --locked --extra server --extra dev
  venv_bin="$PWD/.venv/bin"
else
  python3 -m venv .venv
  .venv/bin/pip install -q -e '.[server,dev]'
  venv_bin="$PWD/.venv/bin"
fi
(cd web && npm ci --no-audit --no-fund)

# Chromium for the e2e tests; best effort (needs the browser CDN, which some network policies block).
"$venv_bin/python" -m playwright install chromium >/dev/null 2>&1 || echo "playwright: chromium not installed (e2e tests will fail)" >&2

# Later Bash calls in this session get the venv on PATH.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$venv_bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
