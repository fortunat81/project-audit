#!/usr/bin/env bash
# Checks a finished audit report for mistakes: bash verify-report.sh [audit-folder]
# The checks themselves are in audit_verify.py (Python 3.8 or newer); this file only finds Python.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/find-python.sh"
if ! find_python; then
  echo "FAIL: the report check needs Python 3.8 or newer (none found). Install Python from https://www.python.org/downloads/ and try again."
  exit 1
fi
PYTHONUTF8=1 exec $PYTHON "$SCRIPT_DIR/audit_verify.py" "$@"
