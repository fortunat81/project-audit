# Sourced by the scripts that need Python. Sets PYTHON to a working Python 3.8+ command, or to an
# empty string when there is none. On Windows, "python3" is often a stub that opens the Microsoft
# Store instead of running Python, so each candidate must actually run a line of code.
#   . "$SCRIPT_DIR/find-python.sh"; find_python || echo "no Python"; $PYTHON script.py

find_python() {
  PYTHON=""
  local c check='import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
  for c in python3 python py; do
    command -v "$c" >/dev/null 2>&1 || continue
    if [ "$c" = py ]; then
      if py -3 -c "$check" >/dev/null 2>&1; then PYTHON="py -3"; return 0; fi
    elif "$c" -c "$check" >/dev/null 2>&1; then
      PYTHON="$c"; return 0
    fi
  done
  return 1
}
