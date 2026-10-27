#!/usr/bin/env bash
# Project audit launcher. The scanner itself is Python (audit_scan.py); this file only finds a working
# Python 3.8+ and hands over. Run it from the project root. See audit_scan.py for the options.
#   bash scan.sh                  run the scan
#   bash scan.sh --check          list missing tools and how to install them
#   bash scan.sh --help-modes     (see the top of audit_scan.py for every mode)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/find-python.sh"
if ! find_python; then
  echo "MISSING	python	The audit needs Python 3.8 or newer (none found)."
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) echo "INSTALL-COMMAND	winget install -e --id Python.Python.3.12  (then close and reopen the terminal)" ;;
    Darwin*) echo "INSTALL-COMMAND	brew install python  (or download it from https://www.python.org/downloads/)" ;;
    *) echo "INSTALL-COMMAND	install python3 with your package manager (for example: apt install python3), or download it from https://www.python.org/downloads/" ;;
  esac
  exit 1
fi
PYTHONUTF8=1 exec $PYTHON "$SCRIPT_DIR/audit_scan.py" "$@"
