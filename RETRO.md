# Building an MCP Server, Honestly

A retro on shipping [kroger-mcp](https://github.com/pattpjy/kroger-mcp) — a Kroger grocery integration for Claude. Written for anyone who has heard the acronym "MCP" thrown around and isn't sure where to start.

This isn't a how-to. It's the story of what we tried, what worked, and the wrong turns we took — so you can skip them.

---

## TL;DR

- Building an MCP server is **easier than the docs make it sound.** A useful one fits in ~200 lines of Python.
- The hard part isn't the code. It's figuring out **which Claude surface you're targeting** and which transport/config file to use. These aren't obvious.
- For personal use: **stdio server + GitHub repo + one config line.** You don't need PyPI, you don't need the MCP Registry, you don't need a cloud host.
- **Claude Cowork can use your local MCP server** through the Claude Desktop bridge. We didn't know this. It cost us a long detour.

---

## What we built

A Model Context Protocol server that exposes the Kroger grocery API to Claude. Four tools:

- Search products at a specific store
- Find stores by ZIP code
- Add items to your cart
- Turn a shopping list of ingredient names into matched Kroger products

With this plugged in, you can tell Claude *"take this week's meal plan and add everything to my Kroger cart"* and it does.

---

## What went well: the core build

The MCP Python SDK (`mcp` on PyPI) has a decorator-based API called `FastMCP` that makes tool definition trivial:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("Kroger")

@mcp.tool()
def kroger_find_stores(zip_code: str, limit: int = 5) -> str:
    """Find Kroger stores near a ZIP code."""
    # ... your implementation
    return json.dumps({"stores": [...]})

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

That's a working MCP server. The docstring becomes the tool description Claude sees. The function signature becomes the input schema. Return a string (we used JSON); Claude parses it.

The whole [server.py](server.py) is under 250 lines and covers all four tools plus OAuth token management.

**Lesson:** If you're intimidated by MCP, don't be. The SDK does almost everything.

---

## Detour 1: The config file maze

First surprise: where does the MCP server registration *go*?

I guessed `.claude/settings.local.json`. Wrong — got a schema error. The answer was `.mcp.json` at the project root.

Turns out Claude Code has **three** places MCP server configs can live:

| Scope | File | When to use |
|---|---|---|
| Project (committed) | `.mcp.json` | Shared with your team via git |
| User (personal) | `~/.claude.json` | Your private MCP servers |
| Via CLI | `claude mcp add` | Writes to one of the above |

**Lesson:** `.mcp.json` is the one you want 90% of the time. It sits at your project root and looks like this:

```json
{
  "mcpServers": {
    "kroger": {
      "command": "python3",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

That's the whole registration. No other ceremony.

---

## Detour 2: SDK version mismatch

First smoke test crashed:

```
TypeError: FastMCP.__init__() got an unexpected keyword argument 'description'
```

I'd written `FastMCP("Kroger", description="...")` from memory. That parameter exists in some SDK versions, not mine. Deleted it, moved on.

**Lesson:** When writing against an SDK, run a two-line smoke test before building out the full thing. I could have caught this with `python3 -c "from mcp.server.fastmcp import FastMCP; FastMCP('test')"` before committing to anything.

---

## Shipping it: what actually goes in the repo

For a personal/sharable MCP server, you need exactly:

```
kroger-mcp/
├── .env.example      # template for credentials
├── .gitignore        # MUST exclude .env and token files
├── LICENSE           # MIT is fine
├── README.md         # how to install + use
├── requirements.txt  # mcp, plus your API client
└── server.py         # the MCP server itself
```

That's it. Six files. Put it on GitHub.

**Critical:** Your `.gitignore` must exclude `.env` and any OAuth token cache files. I've seen people commit secrets in MCP repos by accident. Write the `.gitignore` first, before `git add .`.

**What you don't need (despite what you might hear):**

- **PyPI publishing.** Optional. Nice for `pip install`, but users can just clone.
- **The MCP Registry.** Optional. It's a catalog for discoverability. Launched preview Sep 2025, still evolving. Not required to *use* your server.
- **A `server.json` for Registry submission.** Only if you're submitting to the Registry.
- **Docker, Kubernetes, deploy scripts.** Not for a stdio server people run locally.

---

## Detour 3: the big one — overthinking Cowork

This is the detour worth warning you about.

When we asked *"how do we make this work in Claude Cowork?"* I confidently laid out two paths:

1. **Path A:** Publish to the MCP Registry (PyPI + `mcp-publisher` + `server.json`)
2. **Path B:** Convert to HTTP transport, implement multi-tenant OAuth, deploy to the public internet, submit as a remote connector to Anthropic

Both would have been significant work. Path B especially — we're talking about standing up a hosted service with OAuth per user, handling Kroger's TOS around being a multi-tenant intermediary, etc.

**Both were unnecessary.**

The user's intuition was sharper than mine. They asked: *"I have downloaded other MCP servers and they're just GitHub repos?"*

Yes. They are. Most MCP servers in the wild are exactly that.

Then they pointed out: *"Cowork is working right now with your implementation."*

Here's what I didn't know: **Claude Cowork can reach local stdio MCP servers through the Claude Desktop bridge.** If you register your server in Claude Desktop, Cowork sessions can use it too. No HTTP server, no hosting, no OAuth rewrite. One config file edit:

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
{
  "mcpServers": {
    "kroger": {
      "command": "python3",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "KROGER_CLIENT_ID": "...",
        "KROGER_CLIENT_SECRET": "...",
        "KROGER_REDIRECT_URI": "http://localhost:8000/callback"
      }
    }
  }
}
```

Restart Desktop. Now it works in Cowork. Done.

**Lesson:** Before you commit to a complex architecture, find someone using the platform in anger and ask *"is there a simpler path?"* I had a plausible-sounding mental model (*"Cowork runs in the cloud, so it must need a cloud-hosted MCP"*) and didn't check it. The assumption was wrong, and building on it would have wasted days.

---

## The client landscape, demystified

Here's the map that would have saved us time, written plainly:

### Claude Code (terminal)
- Reads `.mcp.json` in your project root
- Can run **stdio** servers (local subprocess)
- Can connect to **remote** servers (HTTP/SSE URL)
- Use this for: project-scoped MCP servers, development

### Claude Desktop (app)
- Reads `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- Can run **stdio** servers (local subprocess)
- Can connect to **remote** servers (via `mcp-remote` proxy or native)
- Use this for: user-scoped MCP servers that you want available in any session

### Claude Cowork (web/cloud)
- **Bridges to your local Claude Desktop** if you're signed in on the same account
- Therefore: any MCP server registered in Desktop is available in Cowork
- Can ALSO connect directly to remote MCP connectors
- Use this for: delegating long-running work to the cloud while still using your local tools

### The MCP Registry (registry.modelcontextprotocol.io)
- **A catalog.** Not a runtime, not a gatekeeper.
- Lists published MCP servers so clients can discover them
- Required if you want your server to show up in discovery UIs
- Not required for clients to *use* your server if they know the install command

### When you'd need a remote HTTP MCP server
Only if:
- You're building a **product** where users who aren't you need to use your server
- You need **server-side state** (a database, a queue, background jobs)
- You want Cowork to use it **even when your laptop is off**

For a personal integration — stdio is fine. Forever.

---

## The path I'd recommend if you're starting today

1. **Decide what the server exposes.** 3–5 tools usually covers a real integration.
2. **Install the MCP Python SDK:** `pip install mcp`
3. **Write `server.py`** using `FastMCP` and the `@mcp.tool()` decorator. One Python file.
4. **Smoke test with stdio** — pipe an `initialize` + `tools/list` request in, verify your tools appear.
5. **Register it locally:**
   - For Claude Code: drop `.mcp.json` in the project
   - For Claude Desktop (and therefore Cowork): edit `claude_desktop_config.json`
6. **Restart the client.** Test that Claude can actually call your tools.
7. **Polish the repo:** README, `.gitignore` (for secrets!), LICENSE. Push to GitHub.
8. **Stop there** unless someone else actually asks to use it.

If someone does want to use it: they `git clone`, follow your README, and edit their own config. That's the distribution model. It's fine.

If you later want broader distribution, *then* look at PyPI and the MCP Registry. Not before.

---

## Things we built right the first time (worth copying)

Plan mode forced some early decisions that never needed revisiting:

- **Token storage in `~/.kroger-mcp/`**, overridable via env var. Made the server work from any CWD.
- **Two credential modes:** `.env` file OR inline `env` block in the MCP config. Users pick.
- **Lazy API client initialization.** The server starts fast and only authenticates when a tool is called.
- **Read-only `shopping_list_to_cart` that returns matches for review** — Claude asks the user before adding. The destructive version requires an explicit second tool call.

None of those were accidents. They came from the planning document written before any code.

---

## Honest summary

The code was straightforward. The **context of where the code runs** is what tripped us up. MCP as a protocol is simple; the client ecosystem (Code vs. Desktop vs. Cowork vs. Registry) is where you have to actually know the landscape.

If you're reading this and thinking about building an MCP server: **your first version should be a single Python file on GitHub.** That's a complete, legitimate, useful MCP server. Everything else is optional polish.

Don't let yourself get talked into Path B before you've tried Path A.

---

*Written as a retrospective collaboration between the author and Claude. The Claude in this story made the mistakes, and the author caught them — which is the normal and correct direction for that feedback loop.*
