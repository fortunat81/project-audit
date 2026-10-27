"""The check modules, one file each. A module defines:

    NAME        "10-secrets" (the order of the names is the order the checks run in)
    applies(ctx)  True if the module is relevant to the detected project
    tools(ctx)    the external tools it needs (used by --check and --install); optional
    run(ctx)      runs the checks: ctx.run(...), ctx.skip(...), ctx.record(...), ctx.result(...)

To add a check: add a file here, add it to MODULES below, and add a test scenario for it.
"""
import importlib

MODULE_FILES = [
    "m10_secrets", "m15_code_security", "m20_dependencies", "m30_structure", "m40_types_lint", "m45_project_health",
    "m50_backend_rules", "m55_exposed_keys", "m60_ci", "m65_release_readiness", "m70_mobile_native", "m80_live_site",
]


def load_modules():
    """The modules in running order. A module that cannot be loaded is returned as (name, None, error)."""
    loaded = []
    for fname in MODULE_FILES:
        try:
            mod = importlib.import_module("audit_checks." + fname)
            if not all(hasattr(mod, a) for a in ("NAME", "applies", "run")):
                raise ImportError("module file is broken: missing NAME, applies or run")
            loaded.append((mod.NAME, mod, None))
        except Exception as exc:   # a broken module must show up as a gap, not vanish silently
            loaded.append((fname.replace("_", "-", 1), None, str(exc)))
    return loaded
