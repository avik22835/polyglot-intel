#!/bin/bash

# Load resolved MetaCall library paths baked in at image build time
if [ -f /etc/metacall.env ]; then
    set -a; source /etc/metacall.env; set +a
fi

PROJECT="${PROJECT_DIR:-/project}"
REGISTRY="${REGISTRY_PATH:-/app/metacall-registry.json}"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        MetaCall Polyglot Intelligence Server         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Pre-compile / syntax-check supported languages ───────────────────
echo "▶ Checking project files in $PROJECT..."

find "$PROJECT" -name "*.py" 2>/dev/null | while read SRC; do
    if python3 -m py_compile "$SRC" 2>/dev/null; then
        echo "  [py]  ✓ $(basename $SRC)"
    else
        echo "  [py]  ✗ $(basename $SRC) — syntax error"
    fi
done

find "$PROJECT" -name "*.js" 2>/dev/null | while read SRC; do
    if node --check "$SRC" 2>/dev/null; then
        echo "  [js]  ✓ $(basename $SRC)"
    else
        echo "  [js]  ✗ $(basename $SRC) — syntax error"
    fi
done

find "$PROJECT" -name "*.ts" 2>/dev/null | while read SRC; do
    echo "  [ts]  ✓ $(basename $SRC) (loaded by ts_loader at runtime)"
done

# ── Step 2: Scan project and build registry ───────────────────────────────────
echo ""
echo "▶ Scanning project and building intelligence registry..."
python3 /app/parser.py "$PROJECT" "$REGISTRY"

SUMMARY=$(python3 -c "
import json
try:
    d = json.load(open('$REGISTRY'))
    s = d['summary']
    print(f\"{s['total_functions']} functions | {s['total_files']} files | languages: {', '.join(s['languages'])}\")
except Exception as e:
    print(f'(registry error: {e})')
")
echo "  $SUMMARY"

# ── Step 3: Start MCP server in background ────────────────────────────────────
echo ""
echo "▶ Starting MCP server on port 8000..."
python3 -u /app/mcp_server.py &
MCP_PID=$!

# Give the server a moment to bind
sleep 3

# ── Step 4: Start ngrok tunnel ────────────────────────────────────────────────
if [ -n "$NGROK_AUTHTOKEN" ]; then
    ngrok config add-authtoken "$NGROK_AUTHTOKEN" 2>/dev/null
    ngrok http 8000 --log=stdout > /tmp/ngrok.log 2>&1 &

    echo "▶ Opening ngrok tunnel..."
    PUBLIC_URL=""
    for i in $(seq 1 30); do
        PUBLIC_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
            | python3 -c "
import sys, json
try:
    tunnels = json.load(sys.stdin).get('tunnels', [])
    for t in tunnels:
        if t.get('proto') == 'https':
            print(t['public_url'])
            break
except: pass
" 2>/dev/null)
        [ -n "$PUBLIC_URL" ] && break
        sleep 1
    done

    if [ -n "$PUBLIC_URL" ]; then
        echo ""
        echo "┌─────────────────────────────────────────────────────┐"
        echo "│                                                     │"
        echo "│   Add this URL to Claude / your AI tool:            │"
        echo "│                                                     │"
        echo "│   ${PUBLIC_URL}/mcp"
        echo "│                                                     │"
        echo "│   Transport: HTTP  (not SSE, not stdio)             │"
        echo "│                                                     │"
        echo "└─────────────────────────────────────────────────────┘"
        echo ""
    else
        echo "  ✗ ngrok tunnel did not start in time. Check NGROK_AUTHTOKEN."
        echo "    MCP available locally at http://localhost:8000/mcp"
    fi
else
    echo ""
    echo "┌─────────────────────────────────────────────────────┐"
    echo "│   No NGROK_AUTHTOKEN — local access only:           │"
    echo "│   http://localhost:8000/mcp                         │"
    echo "│                                                     │"
    echo "│   To get a public HTTPS URL, restart with:          │"
    echo "│   -e NGROK_AUTHTOKEN=your_token                     │"
    echo "└─────────────────────────────────────────────────────┘"
    echo ""
fi

# Keep container alive — wait for MCP server process
wait $MCP_PID
