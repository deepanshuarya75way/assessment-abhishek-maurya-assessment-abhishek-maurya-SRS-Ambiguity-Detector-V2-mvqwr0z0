#!/usr/bin/env bash
# Pre-commit secret scan (the project contract).
# Scans tracked + untracked (not-ignored) files for high-confidence secret
# shapes. Ignored paths (.env, *.pem, secrets/) are NEVER scanned — local
# secrets belong there. Exits 1 on any unallowlisted match.
#   ./scripts/secret-scan.sh
set -euo pipefail

# Resolve symlinks so the documented .git/hooks/pre-commit symlink works
# (relative link targets resolve against the link's directory, not $PWD).
SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  LINK_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$LINK_DIR/$SOURCE"
done
ROOT="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
ALLOW="$ROOT/scripts/secret-scan.allow"
cd "$ROOT"

PATTERN='\b(sk-ant-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{20,}|re_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{20,}|hf_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|Bearer [A-Za-z0-9._~+/-]{20,}|eyJ[A-Za-z0-9_-]{10,}\.eyJ|://[^/:@[:space:]]+:[^/@[:space:]]+@)'
ASSIGN_PATTERN="['\"]?\b(api[_-]?key|secret|token)\b['\"]?\s*[:=]+\s*['\"][A-Za-z0-9._~+/=-]{12,}['\"]"

FILES="$(git ls-files --cached --others --exclude-standard | grep -v -e '^frontend/package-lock.json$' -e '^scripts/secret-scan.allow$' || true)"
if [[ -z "$FILES" ]]; then
  echo "secret-scan: no files to scan"
  exit 0
fi

HITS="$(echo "$FILES" | xargs grep -nE -e "$PATTERN" -e "$ASSIGN_PATTERN" 2>/dev/null | grep -v -F -f <(grep -v -e '^#' -e '^$' "$ALLOW") || true)"
if [[ -n "$HITS" ]]; then
  echo "secret-scan: POSSIBLE SECRETS FOUND (remove or allowlist in scripts/secret-scan.allow):"
  echo "$HITS"
  exit 1
fi
echo "secret-scan: clean"
