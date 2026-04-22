import json
import os
import subprocess
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from registry_manager import RegistryManager

try:
    from metacall import metacall_load_from_file, metacall
    NATIVE_ACTIVE = True
except ImportError:
    NATIVE_ACTIVE = False

PROJECT_DIR   = os.environ.get("PROJECT_DIR", "./simulation")
REGISTRY_PATH = os.environ.get("REGISTRY_PATH", "metacall-registry.json")

mcp = FastMCP(
    "MetaCall Polyglot Intelligence",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

manager = RegistryManager(REGISTRY_PATH)


@mcp.tool()
def list_functions() -> str:
    """List all functions in the project with names, languages, files, and signatures."""
    funcs = [
        {
            "name": n["name"],
            "language": n["language"],
            "file": n["file"],
            "signature": n["signature"]
        }
        for n in manager.nodes
    ]
    return json.dumps(funcs, indent=2)


@mcp.tool()
def scan_project(project_path: str = None) -> str:
    """Re-scan the project directory and refresh the registry."""
    global manager
    target = project_path or PROJECT_DIR

    from parser import MetaCallParser
    from registry_writer import RegistryWriter

    intel = MetaCallParser()
    chunks = intel.parse_directory(target)
    writer = RegistryWriter(chunks)
    registry = writer.build_registry(REGISTRY_PATH)

    if registry:
        manager = RegistryManager(REGISTRY_PATH)
        s = registry["summary"]
        return (
            f"Scan complete: {s['total_functions']} functions in "
            f"{s['total_files']} files. Languages: {', '.join(s['languages'])}"
        )
    return "Scan failed — check that the project path exists and contains supported source files."


_RUNNER_TIMEOUT = int(os.environ.get("METACALL_RUNNER_TIMEOUT", "120"))


def _run_in_subprocess(fn_name: str, call_args: list) -> dict:
    # Isolated child process so a MetaCall C-core crash cannot kill the server
    r = subprocess.run(
        [
            "python3", "/app/metacall_runner.py",
            REGISTRY_PATH, PROJECT_DIR,
            fn_name, json.dumps(call_args)
        ],
        capture_output=True, text=True, timeout=_RUNNER_TIMEOUT
    )
    if r.stdout.strip():
        try:
            return json.loads(r.stdout.strip())
        except Exception:
            pass
    return {
        "ok": False,
        "error": (r.stderr.strip() or f"exit code {r.returncode}"),
        "deploy_log": []
    }


@mcp.tool()
def deploy_function() -> str:
    """Show the file manifest — what would be loaded into MetaCall and which loaders would be used."""
    files = manager.data.get("files", {})
    if not files:
        return "No files in registry. Run scan_project() first."

    lines = ["Registry manifest (files ready for MetaCall execution):\n"]
    for file_name, file_data in files.items():
        loader = file_data["loader"]
        funcs  = [f["name"] for f in file_data.get("functions", [])]
        so_path = os.path.join(os.path.abspath(PROJECT_DIR), file_name.rsplit(".", 1)[0] + ".so")
        compiled = " [.so ready]" if loader in ("rs", "c", "cpp") and os.path.exists(so_path) else ""
        lines.append(f"  [{loader}]{compiled} {file_name} — exports: {', '.join(funcs)}")

    lines.append(f"\nnative_metacall available: {NATIVE_ACTIVE}")
    return "\n".join(lines)


_TYPE_DEFAULTS = {
    "Int": 42, "Long": 42, "Short": 42,
    "Float": 3.14, "Double": 3.14,
    "String": "hello", "Bool": True,
    "Array": [1.5, 2.5, 3.5],
    "Map": {}, "Ptr": None,
}


def _default_args_for(func_name: str) -> list:
    for file_data in manager.data.get("files", {}).values():
        for f in file_data.get("functions", []):
            if f["name"] == func_name:
                sig_args = f.get("signature", {}).get("args", [])
                return [
                    _TYPE_DEFAULTS.get(a.get("metacall_type", {}).get("name", "Ptr"), None)
                    for a in sig_args
                ]
    return []


@mcp.tool()
def call_function(function_name: str, args: list = None) -> str:
    """
    Call a single registered function via MetaCall in an isolated subprocess.
    If args is omitted, defaults are generated from the registry signature.
    Example: call_function('analyze_data', [[1.5, 2.5, 3.5]])
    """
    call_args = args if args is not None else _default_args_for(function_name)
    out = _run_in_subprocess(function_name, call_args)
    deploy = "\n  ".join(out.get("deploy_log", []))
    if out.get("ok"):
        return (
            f"metacall('{function_name}', {call_args})\n"
            f"-> {repr(out['result'])}\n\n"
            f"Load log:\n  {deploy}"
        )
    return f"Error: {out.get('error')}\n\nLoad log:\n  {deploy}"


def _get_lang(file_name: str) -> str:
    for fn, fd in manager.data.get("files", {}).items():
        if fn == file_name:
            return fd.get("language", "?")
    return "?"


def _get_callees(func_name: str) -> list:
    for fd in manager.data.get("files", {}).values():
        for f in fd.get("functions", []):
            if f["name"] == func_name:
                return [c["callee"] for c in f.get("calls", []) if c.get("resolved")]
    return []


@mcp.tool()
def run_app(function_name: str = None, args: list = None) -> str:
    """
    Execute the polyglot call chain via MetaCall.

    Calls each function in the chain leaves-first and pipes results upward.
    This avoids the context isolation issue where nested metacall() calls inside
    loaded files cannot see each other's registry.
    """
    entry_points = manager.find_entry_points()
    target_name  = function_name or (entry_points[0]["name"] if entry_points else None)

    if not target_name:
        return "No entry points found. Run scan_project() first."

    target_id = next(
        (f"{fn}:{target_name}" for fn, fd in manager.data.get("files", {}).items()
         for f in fd.get("functions", []) if f["name"] == target_name),
        target_name
    )

    chain_steps = manager.trace_execution(target_id)
    chain_lines = []
    for step in chain_steps:
        indent = "  " * step["depth"]
        prefix = ">" if step["depth"] == 0 else "└──"
        step_file = step["id"].split(":")[0]
        lang = _get_lang(step_file)
        chain_lines.append(f"{indent}{prefix} {step['id']}  ({lang})")

    seen = []
    for step in chain_steps:
        fname = step["id"].split(":")[-1]
        if fname not in seen:
            seen.append(fname)
    leaves_first = list(reversed(seen))

    exec_log      = []
    results_cache = {}

    for fname in leaves_first:
        callees = _get_callees(fname)
        if callees and all(c in results_cache for c in callees):
            call_args = [results_cache[c] for c in callees]
        else:
            call_args = _default_args_for(fname) if args is None else args

        out = _run_in_subprocess(fname, call_args)
        if out.get("ok"):
            results_cache[fname] = out["result"]
            exec_log.append(f"  ok  {fname}({call_args}) -> {repr(out['result'])}")
        else:
            results_cache[fname] = None
            exec_log.append(f"  err {fname}({call_args}) -> {out.get('error', 'unknown error')}")

    final = results_cache.get(target_name)
    return (
        f"Polyglot call chain:\n" + "\n".join(chain_lines) + "\n\n"
        f"Execution (leaves first):\n" + "\n".join(exec_log) +
        f"\n\nResult of '{target_name}': {repr(final)}"
    )


@mcp.tool()
def trace_execution(function_id: str) -> str:
    """
    DFS forward trace from a function — shows the full execution chain.
    function_id format: 'filename:function_name'  e.g. 'gateway.js:handle_request'
    """
    path = manager.trace_execution(function_id)
    if not path:
        return (
            f"Function '{function_id}' not found in registry.\n"
            f"Use list_functions() to see valid IDs."
        )
    lines = []
    for step in path:
        indent = "  " * step["depth"]
        prefix = ">" if step["depth"] == 0 else "└──"
        lines.append(f"{indent}{prefix} {step['id']}")
    return "\n".join(lines)


@mcp.tool()
def analyze_impact(function_id: str) -> str:
    """
    BFS backward — shows every function that would be affected if this one changes.
    function_id format: 'filename:function_name'  e.g. 'engine.py:analyze_data'
    """
    victims = manager.analyze_impact(function_id, direction="backward")
    if not victims:
        node_ids = [n["id"] for n in manager.nodes]
        if function_id not in node_ids:
            return (
                f"Function '{function_id}' not found in registry.\n"
                f"Use list_functions() to see valid IDs."
            )
        return f"No callers found for '{function_id}' — safe to change without breaking anything upstream."

    lines = [f"Impact of changing '{function_id}':"]
    for v in victims:
        lines.append(f"  level {v['distance']}: {v['id']}")
    return "\n".join(lines)


@mcp.tool()
def generate_polyglot(caller_language: str, callee_function: str) -> str:
    """
    Generate the correct metacall() snippet for calling a function from another language.
    Uses the real registry signature so argument names and types are accurate.
    caller_language: 'python' | 'javascript' | 'ruby' | 'go' | 'typescript'
    callee_function: function name, e.g. 'analyze_data'
    """
    target = next((n for n in manager.nodes if n["name"] == callee_function), None)
    if not target:
        return (
            f"Function '{callee_function}' not found in registry.\n"
            f"Use list_functions() to see available functions."
        )

    sig = target["signature"]
    arg_names  = [a["name"] for a in sig.get("args", [])]
    args_typed = ", ".join(
        f"{a['name']}: {a['metacall_type']['name']}"
        for a in sig.get("args", [])
    )
    ret_type  = sig.get("ret", {}).get("name", "Ptr")
    args_call = ", ".join(arg_names)
    lang      = caller_language.lower()

    snippets = {
        "python": (
            f"from metacall import metacall\n\n"
            f"result = metacall('{callee_function}', {args_call})"
        ),
        "javascript": (
            f"const {{ metacall }} = require('metacall');\n\n"
            f"const result = metacall('{callee_function}', {args_call});"
        ),
        "typescript": (
            f"import {{ metacall }} from 'metacall';\n\n"
            f"const result = metacall('{callee_function}', {args_call});"
        ),
        "ruby": (
            f"require 'metacall'\n\n"
            f"result = metacall('{callee_function}', {args_call})"
        ),
        "go": (
            f"import mc \"github.com/metacall/core/source/ports/go_port/source\"\n\n"
            f"result := mc.Call(\"{callee_function}\", {args_call})"
        ),
    }

    snippet = snippets.get(lang, f"metacall('{callee_function}', {args_call})")

    return (
        f"Function:  {callee_function}\n"
        f"Source:    {target['file']} ({target['language']})\n"
        f"Signature: ({args_typed}) -> {ret_type}\n\n"
        f"Call from {caller_language}:\n"
        f"{snippet}"
    )


GROUND_TRUTH = """
MetaCall type IDs (metacall reflect system):
  METACALL_BOOL=0     METACALL_CHAR=1     METACALL_SHORT=2    METACALL_INT=3
  METACALL_LONG=4     METACALL_FLOAT=5    METACALL_DOUBLE=6   METACALL_STRING=7
  METACALL_BUFFER=8   METACALL_ARRAY=9    METACALL_MAP=10     METACALL_PTR=11
  METACALL_FUTURE=12  METACALL_FUNCTION=13 METACALL_NULL=14   METACALL_CLASS=15

Loader tags:
  py=Python  node=JavaScript  ts=TypeScript  rb=Ruby
  rs=Rust    go=Go            c=C            cpp=C++

Loading files (absolute paths required):
  metacall_load_from_file("py",   ["/abs/path/file.py"])
  metacall_load_from_file("node", ["/abs/path/file.js"])
  metacall_load_from_file("rb",   ["/abs/path/file.rb"])
  metacall_load_from_file("rs",   ["/abs/path/lib.rs"])   # must have #[no_mangle]

Calling functions:
  result = metacall("function_name", arg1, arg2)   # Python
  result = metacall('function_name', arg1, arg2)   # Ruby
  const r = metacall("fn", arg)                    # JavaScript
  r := mc.Call("fn", arg)                          # Go

metacall.json format (required for FaaS deployment):
  {"language_id": "py",   "path": ".", "scripts": ["model.py"]}
  {"language_id": "node", "path": ".", "scripts": ["main.js"]}

Rules:
  - Rust: only #[no_mangle] pub extern "C" functions are callable
  - All paths passed to metacall_load_from_file must be absolute
  - Dynamic calls (variable function name) cannot be statically resolved
  - inferred: true means the type was guessed from an untyped parameter
"""


@mcp.tool()
def get_registry() -> str:
    """Return the full metacall-registry.json."""
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Registry not found. Run scan_project() first."


@mcp.tool()
def get_file(file_path: str) -> str:
    """Return the raw source of any file in the project. file_path is relative to project root."""
    project_root = os.path.abspath(PROJECT_DIR)
    safe_path = os.path.normpath(os.path.join(project_root, file_path))
    if not safe_path.startswith(project_root):
        return "Error: path is outside the project directory."
    if not os.path.exists(safe_path):
        return f"File not found: {file_path}"
    try:
        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


@mcp.tool()
def get_function_source(name: str) -> str:
    """Return the source lines of a named function using start/end line from the registry."""
    for file_name, file_data in manager.data.get("files", {}).items():
        for func in file_data.get("functions", []):
            if func["name"] == name:
                file_path = os.path.join(os.path.abspath(PROJECT_DIR), file_name)
                if not os.path.exists(file_path):
                    return f"Source file not found: {file_name}"
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    start = func["start_line"] - 1
                    end = func["end_line"]
                    return "".join(lines[start:end])
                except Exception as e:
                    return f"Error reading source: {str(e)}"
    return f"Function '{name}' not found. Use list_functions() to check available names."


@mcp.tool()
def get_ground_truth() -> str:
    """MetaCall type IDs, loader tags, call syntax, and rules."""
    return GROUND_TRUTH


@mcp.tool()
def health() -> str:
    """Server status: function count, detected languages, MetaCall availability."""
    s = manager.data.get("summary", {})
    return json.dumps({
        "status": "ok",
        "functions": s.get("total_functions", 0),
        "files": s.get("total_files", 0),
        "languages": s.get("languages", []),
        "project_dir": PROJECT_DIR,
        "native_metacall": NATIVE_ACTIVE,
    }, indent=2)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
