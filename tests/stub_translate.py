# Stand-in for the claude program when it is asked to translate (used by translate_test.py).
# It does what a correct translation would do, without calling Claude: AUDIT.<target>.md is a copy of
# AUDIT.md with the verdict phrase in the target language, and fixes.json gets a second language.
import json
import os
import re
import sys

prompt = sys.stdin.read()
m = re.search(r"AUDIT\.(en|fr)\.md", prompt)
target = m.group(1) if m else "fr"
if "AUDIT.%s.md" % target in prompt and os.path.exists("AUDIT.md"):
    text = open("AUDIT.md", encoding="utf-8").read()
    if target == "fr":
        text = text.replace("Launch with limits", "Lancement avec réserves").replace("Don't launch yet", "Ne pas lancer tout de suite")
        text = text.replace("No blocking problems found", "Aucun problème bloquant trouvé").replace("# Audit", "# Audit (français)")
    open("AUDIT.%s.md" % target, "w", encoding="utf-8").write(text)
if "fixes.json" in prompt and os.path.exists("fixes.json"):
    data = json.load(open("fixes.json", encoding="utf-8"))
    for fix in data["fixes"]:
        for key in ("title", "why", "change", "verify"):
            v = fix.get(key)
            if isinstance(v, str) and v:
                fix[key] = {"en": v, "fr": "[fr] " + v} if target == "fr" else {"fr": "[fr] " + v, "en": v}
    json.dump(data, open("fixes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "translated"}]}}), flush=True)
print(json.dumps({"type": "result", "result": "done"}), flush=True)
