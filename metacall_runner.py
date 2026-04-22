"""
Isolated MetaCall execution worker.

Runs as a child subprocess so a C-core crash or segfault cannot take down
the MCP server process. Prints a single JSON line to stdout and exits.

Usage:
  python3 metacall_runner.py <registry_path> <project_dir> <function_name> <args_json>

Output:
  {"ok": true,  "result": <value>, "deploy_log": [...]}
  {"ok": false, "error": "<msg>",  "deploy_log": [...]}
"""

import json
import os
import sys


def main():
    if len(sys.argv) < 5:
        print(json.dumps({"ok": False, "error": "usage: runner <registry> <project> <fn> <args_json>"}))
        sys.exit(1)

    registry_path = sys.argv[1]
    project_dir   = sys.argv[2]
    fn_name       = sys.argv[3]
    call_args     = json.loads(sys.argv[4])
    deploy_log    = []

    try:
        from metacall import metacall_load_from_file, metacall
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"metacall import failed: {e}", "deploy_log": []}))
        sys.exit(1)

    try:
        with open(registry_path, "r") as f:
            registry = json.load(f)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"registry load failed: {e}", "deploy_log": []}))
        sys.exit(1)

    files = registry.get("files", {})

    fn_to_file = {}
    for file_name, file_data in files.items():
        for func in file_data.get("functions", []):
            fn_to_file[func["name"]] = file_name

    def required_files(start_fn: str) -> list:
        # Walk the call graph from start_fn and collect only the files actually needed.
        # This avoids loading files with top-level server.listen() or other blocking code.
        needed = []
        visited = set()
        queue = [start_fn]
        while queue:
            fn = queue.pop(0)
            if fn in visited:
                continue
            visited.add(fn)
            f_file = fn_to_file.get(fn)
            if f_file and f_file not in needed:
                needed.append(f_file)
            f_data = files.get(f_file, {}) if f_file else {}
            for func in f_data.get("functions", []):
                if func["name"] == fn:
                    for call in func.get("calls", []):
                        if call.get("resolved"):
                            queue.append(call["callee"])
        return needed

    needed = required_files(fn_name)
    deploy_log.append(f"Loading only files needed for '{fn_name}': {needed}")

    def sort_key(fname):
        # Load compiled loaders first so their symbols are available when interpreted files load
        return 0 if files[fname].get("loader") in ("rs", "c", "cpp") else 1

    for file_name in sorted(needed, key=sort_key):
        file_data = files[file_name]
        loader    = file_data["loader"]
        abs_path  = os.path.join(os.path.abspath(project_dir), file_name)

        if loader in ("rs", "c", "cpp"):
            so_path = abs_path.rsplit(".", 1)[0] + ".so"
            if os.path.exists(so_path):
                abs_path = so_path
            else:
                deploy_log.append(f"MISSING .so for {file_name}")
                continue

        if not os.path.exists(abs_path):
            deploy_log.append(f"MISSING: {abs_path}")
            continue

        try:
            status = metacall_load_from_file(loader, [abs_path])
            ok = (status == 0)
            deploy_log.append(f"{'LOAD✓' if ok else f'LOAD✗({status})'} [{loader}] {os.path.basename(abs_path)}")
        except Exception as e:
            deploy_log.append(f"ERROR [{loader}] {file_name}: {e}")

    try:
        result = metacall(fn_name, *call_args)
        print(json.dumps({"ok": True, "result": result, "deploy_log": deploy_log}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "deploy_log": deploy_log}))


if __name__ == "__main__":
    main()
