# Stand-in for the claude program (used by serve_test.py): prints stream-json lines like the real one and records how it was called.
import json, sys, time, os
prompt = sys.stdin.read()
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stub-called.txt"), "w", encoding="utf-8").write(" ".join(sys.argv[1:]) + "\n---\n" + prompt)
for text in ["Checking git status...", "Creating branch audit-fix/test", "Applied P-2 and committed", "Applied P-3 and committed"]:
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}), flush=True)
    time.sleep(1.2)
print(json.dumps({"type": "result", "result": "All approved fixes applied on branch audit-fix/test."}), flush=True)
