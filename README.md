# polyglot-intel

An MCP server that gives AI coding tools structural understanding of polyglot projects built with [MetaCall](https://metacall.io/).

Point it at a project folder. It parses every Python, JavaScript, TypeScript, Rust, Ruby, Go, C, and C++ file, maps the cross-language `metacall()` call graph, and exposes a set of tools your AI client can call directly.

Built as part of Google Summer of Code 2025 with the MetaCall organization.

---

## How it works

The server runs inside Docker. On startup it:

1. Parses the mounted project directory with Tree-sitter and builds a function registry
2. Resolves cross-language `metacall()` calls across files (e.g. `gateway.js` calling `analyze_data` in `engine.py`)
3. Starts an MCP server on port 8000
4. Opens an ngrok HTTPS tunnel and prints the URL

Your AI client connects to that URL. From there it can list functions, trace execution chains, analyze change impact, call individual functions, and read source.

All MetaCall execution runs in an isolated child subprocess so a C-core crash cannot take down the MCP server.

---

## Quickstart

### 1. Set your project path

Copy `.env.example` to `.env` and set `PROJECT_DIR` to your project folder:

```
PROJECT_DIR=C:/Users/yourname/your-project     # Windows
PROJECT_DIR=/home/yourname/your-project        # Mac / Linux
NGROK_AUTHTOKEN=your_ngrok_token
```

Get a free ngrok token at https://ngrok.com.

### 2. Run

```bash
docker-compose up --build
```

Wait for the URL to appear in the output:

```
Add this URL to Claude / your AI tool:

   https://xxxx.ngrok-free.app/mcp

Transport: HTTP  (not SSE, not stdio)
```

### 3. Connect

**Claude Code:**
```bash
claude mcp add --transport http polyglot-intel https://xxxx.ngrok-free.app/mcp
```

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "polyglot-intel": {
      "url": "https://xxxx.ngrok-free.app/mcp"
    }
  }
}
```

Restart Claude Desktop after saving.

---

## Tools

| Tool | Description |
|------|-------------|
| `health` | Server status, function count, detected languages |
| `list_functions` | All functions with names, files, languages, signatures |
| `scan_project` | Re-scan the project directory and refresh the registry |
| `call_function(fn_name, args)` | Call a single function via MetaCall |
| `run_app(function_name, args)` | Run the full polyglot call chain from an entry point |
| `trace_execution(function_id)` | Forward DFS from a function — shows the full call chain |
| `analyze_impact(function_id)` | Backward BFS — shows what breaks if this function changes |
| `generate_polyglot(caller_language, callee_function)` | Generate the correct `metacall()` call snippet |
| `get_registry` | Full registry JSON |
| `get_file(file_path)` | Raw source of any file in the project |
| `get_function_source(name)` | Source lines of a named function |
| `get_ground_truth` | MetaCall type IDs, loader tags, and call syntax reference |

`function_id` format: `filename:function_name` — e.g. `engine.py:analyze_data`

---

## Loader support

The server uses the MetaCall universal installer distributable. Loaders confirmed working in the Docker image:

- Python (`py_loader`) — stable
- Node.js (`node_loader`) — stable
- TypeScript (`ts_loader`) — present

Not currently available in the distributable:

- Ruby (`rb_loader`) — loads but segfaults on function calls (ABI mismatch with bundled Ruby 3.3.9)
- Rust (`rs_loader`) — not included in the distributable; requires building MetaCall from source with `-DOPTION_BUILD_LOADERS_RS=ON`

The demo project (`smart-api-demo-v2/`) uses Python and Node.js only.

---

## Demo project

`smart-api-demo-v2/` contains a minimal two-language project:

- `engine.py` — Python analytics functions (`analyze_data`, `summarize`)
- `gateway.js` — Node.js entry point that calls into Python via `metacall()`

Run it against the demo:

```bash
MSYS_NO_PATHCONV=1 docker run --rm \
  -p 8000:8000 \
  -v "/path/to/smart-api-demo-v2:/project" \
  -e PROJECT_DIR=/project \
  -e NGROK_AUTHTOKEN=your_token \
  polyglot-intel
```

---

## Local development (no Docker)

```bash
pip install -r requirements.txt

python3 parser.py ./smart-api-demo-v2 ./metacall-registry.json

PROJECT_DIR=./smart-api-demo-v2 python3 mcp_server.py
```

`call_function` and `run_app` require MetaCall installed locally. The graph tools (`trace_execution`, `analyze_impact`, `list_functions`, etc.) work without it.

---

## Project structure

```
polyglot-intel/
  parser.py            tree-sitter parser, builds function chunks from source
  registry_writer.py   assembles chunks into the registry JSON
  registry_manager.py  loads registry, builds call graph, exposes graph queries
  mcp_server.py        FastMCP server, all tool definitions
  metacall_runner.py   isolated subprocess worker for MetaCall execution
  startup.sh           container entrypoint: scan, start server, open tunnel
  Dockerfile
  requirements.txt
```
