#!/usr/bin/env bash
# Stage-completion verification gate (see the project contract).
#   ./scripts/verify.sh         full gate (lint, typecheck, tests, builds, audits)
#   ./scripts/verify.sh --fast  skips only the production build
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAST=0
if [[ "${1:-}" == "--fast" ]]; then FAST=1; fi

pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; exit 1; }
section() { echo; echo "▶ $1"; }

cd "$ROOT"

section "Backend: ruff lint + format check"
cd backend
ruff check app tests alembic || fail "ruff check failed"
ruff format --check app tests alembic || fail "ruff format check failed"
pass "ruff clean"

section "Backend: mypy"
mypy app || fail "mypy failed"
pass "mypy clean"

section "Backend: pytest"
python -m pytest -q || fail "pytest failed"
pass "pytest green"

section "Backend: import + OpenAPI sanity"
python -c "from app.main import app; routes=sorted({r.path for r in app.routes}); assert '/api/v1/health/live' in routes, routes; assert '/api/v1/documents/upload' in routes, routes; assert '/api/v1/documents/{document_id}' in routes, routes; print('routes:', routes)"
pass "FastAPI app imports; health + documents routes mounted"

cd "$ROOT"

section "Frontend: eslint"
cd frontend
npm run lint --silent || fail "eslint failed"
pass "eslint clean"

section "Frontend: typecheck"
npm run typecheck --silent || fail "tsc failed"
pass "tsc clean"

section "Frontend: unit tests"
npm test --silent || fail "vitest failed"
pass "vitest green"

section "Frontend: prettier"
npm run format --silent || fail "prettier check failed (run: npm run format:write)"
pass "prettier clean"

if [[ "$FAST" == "0" ]]; then
  section "Frontend: production build"
  npm run build --silent || fail "next build failed"
  pass "next build green"
else
  echo "  ⏭  skipped production build (--fast)"
fi

cd "$ROOT"

section "Secret scan"
./scripts/secret-scan.sh || fail "secret scan found possible committed secrets"
pass "secret scan clean"

section "Dependency audit (npm)"
cd frontend
npm audit --silent || fail "npm audit found vulnerabilities"
pass "npm audit clean"

section "Dependency audit (pip)"
cd "$ROOT/backend"
# Accepted starlette findings (triaged Stage 20, roadmap-21 — see
# the project contract): the gate fails only on NEW advisories.
python -m pip_audit -r requirements.txt -r requirements-dev.txt \
  --ignore-vuln PYSEC-2026-1941 --ignore-vuln PYSEC-2026-1942 \
  --ignore-vuln PYSEC-2026-161 --ignore-vuln PYSEC-2026-2281 \
  --ignore-vuln PYSEC-2026-2280 --ignore-vuln PYSEC-2026-249 \
  --ignore-vuln PYSEC-2026-248 \
  || fail "pip-audit found NEW vulnerabilities (triage in SECURITY_SPEC.md §10)"
pass "pip-audit clean"

cd "$ROOT"
echo
echo "🎉 verify.sh: ALL CHECKS PASSED"
