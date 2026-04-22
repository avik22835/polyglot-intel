# polyglot-intel

An MCP server that gives AI coding tools structural understanding of polyglot projects built with MetaCall. It parses your project, maps cross-language `metacall()` call graphs, and exposes tools so Claude or any MCP-compatible agent can list functions, trace execution chains, analyze change impact, and call functions live across language boundaries.

---

## Setup

**1. Build the image**

```bash
git clone https://github.com/avik22835/polyglot-intel
cd polyglot-intel
docker build -t polyglot-intel .
```

**2. Run against your project**

```bash
docker run --rm \
  -p 8000:8000 \
  -v /absolute/path/to/your/project:/project \
  -e PROJECT_DIR=/project \
  -e NGROK_AUTHTOKEN=your_ngrok_token \
  polyglot-intel
```

Get a free ngrok token at https://ngrok.com.

On Windows, prefix the command with `MSYS_NO_PATHCONV=1`.

**3. Get the URL**

After about 10 seconds the terminal prints:

```
https://xxxx.ngrok-free.app/mcp
```

**4. Add to your AI tool**

Claude Code:
```bash
claude mcp add --transport http polyglot-intel https://xxxx.ngrok-free.app/mcp
```

Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "polyglot-intel": { "url": "https://xxxx.ngrok-free.app/mcp" }
  }
}
```
