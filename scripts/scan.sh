#!/usr/bin/env bash
# Project audit launcher. The scanner itself is Python (audit_scan.py); this file only finds a working
# Python 3.8+ and hands over. Run it from the project root. See audit_scan.py for the options.
#   bash scan.sh                  run the scan
#   bash scan.sh --check          list missing tools and how to install them
#   bash scan.sh --help-modes     (see the top of audit_scan.py for every mode)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/find-python.sh"
if ! find_python; then
  echo "The audit needs Python 3.8 or newer (none found). Install it from https://www.python.org/downloads/ and try again."
  exit 1
fi
PYTHONUTF8=1 exec $PYTHON "$SCRIPT_DIR/audit_scan.py" "$@"
