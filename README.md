# Kroger MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server for the [Kroger Public API](https://developer.kroger.com/). Lets Claude (or any MCP client) search Kroger products, find stores, and add items to your Kroger cart.

Built for use with [Claude Code](https://claude.com/claude-code), Claude Desktop, Claude Cowork (via the Desktop bridge), or any MCP-compatible client.

## Features

- **`kroger_search_products`** — Search products at a specific Kroger store
- **`kroger_find_stores`** — Find nearby Kroger stores by ZIP code
- **`kroger_add_to_cart`** — Add items by UPC to your Kroger cart
- **`kroger_shopping_list_to_cart`** — Match a list of ingredient names to Kroger products (returns matches for review before adding)

## Installation

### 1. Clone and install dependencies

```bash
git clone https://github.com/pattpjy/kroger-mcp.git
cd kroger-mcp
pip install -r requirements.txt
```

### 2. Get Kroger API credentials

1. Sign up at [developer.kroger.com](https://developer.kroger.com/)
2. Create an application with:
   - **Redirect URI:** `http://localhost:8000/callback`
   - **Scopes:** `product.compact` and `cart.basic:write`
3. Copy your **Client ID** and **Client Secret**

### 3. Configure `.env`

```bash
cp .env.example .env
# edit .env and paste your Client ID and Secret
```

### 4. Authorize your Kroger account (one-time)

Cart operations require user OAuth. Search and store lookup don't.

```bash
python kroger_auth.py
```

This prints a URL — open it, log in, click Authorize, then paste the `code=...` value back into the terminal. Tokens are saved to `~/.kroger-mcp/` and auto-refresh.

## MCP Client Configuration

You have two ways to supply credentials: a `.env` file next to the server (shown in the installation steps above), or inline via the `env` block in your MCP client config (shown below). The `env` block is useful when you don't want a `.env` file on disk.

### Claude Code

Add to your project's `.mcp.json` (or run `claude mcp add`):

```json
{
  "mcpServers": {
    "kroger": {
      "command": "python3",
      "args": ["/absolute/path/to/kroger-mcp/server.py"]
    }
  }
}
```

### Claude Desktop

Edit `claude_desktop_config.json`:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "kroger": {
      "command": "python3",
      "args": ["/absolute/path/to/kroger-mcp/server.py"],
      "env": {
        "KROGER_CLIENT_ID": "your_client_id",
        "KROGER_CLIENT_SECRET": "your_secret",
        "KROGER_REDIRECT_URI": "http://localhost:8000/callback"
      }
    }
  }
}
```

The `env` block is optional — if you've set up a `.env` file next to `server.py`, you can omit it.

### Claude Cowork

Cowork can use the Kroger tools through the **Claude Desktop bridge**. Any MCP server registered in your local Claude Desktop config is automatically available inside your Cowork sessions — no separate hosting or remote URL needed. Just complete the Claude Desktop setup above, and restart Desktop.

Restart Claude Code/Desktop after updating the config.

## Usage Examples

Once connected, ask Claude:

- "Find Kroger stores near 80205"
- "Search Kroger for chicken breast at store 01400376"
- "Add this shopping list to my Kroger cart: chicken breast, jasmine rice, broccoli"

The `shopping_list_to_cart` tool returns matches for review — Claude will show them to you and ask before actually adding to cart.

## Tool Reference

### `kroger_search_products`
| Param | Type | Required | Description |
|---|---|---|---|
| `term` | string | yes | Search term (e.g. "chicken breast") |
| `location_id` | string | yes | Kroger store location ID |
| `limit` | int | no (5) | Max results |

### `kroger_find_stores`
| Param | Type | Required | Description |
|---|---|---|---|
| `zip_code` | string | yes | US ZIP code |
| `limit` | int | no (5) | Max results |

### `kroger_add_to_cart`
| Param | Type | Required | Description |
|---|---|---|---|
| `items` | array of `{upc, quantity}` | yes | Items to add |

### `kroger_shopping_list_to_cart`
| Param | Type | Required | Description |
|---|---|---|---|
| `items` | array of strings | yes | Ingredient names |
| `location_id` | string | yes | Kroger store location ID |
| `quantity` | int | no (1) | Default qty per item |

Returns matches with prices, plus items that couldn't be found. Does NOT auto-add to cart.

## Token Storage

Tokens are saved to `~/.kroger-mcp/` by default. Override with the `KROGER_TOKEN_DIR` env var.

The user token auto-refreshes via the refresh_token. If the refresh token expires (typically after a few months), re-run `python kroger_auth.py`.

## Limitations

- The Kroger Cart API only supports **adding** items. Removing or modifying quantities must be done on kroger.com or in the Kroger app.
- Product search works best with specific terms ("boneless skinless chicken breast" beats "chicken").
- Prices and availability require a `location_id` — they're store-specific.

## Retrospective

If you're new to MCP and wondering where to start — read [RETRO.md](RETRO.md). It's a candid writeup of what worked, what didn't, and the detours we took building this. Aimed at people who aren't sure how Claude Code, Desktop, Cowork, and the MCP Registry fit together.

## License

MIT — see [LICENSE](LICENSE).

## Credits

Built on the [`kroger-api`](https://pypi.org/project/kroger-api/) Python library and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
