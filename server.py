#!/usr/bin/env python3
"""
Kroger MCP Server

A Model Context Protocol server that exposes the Kroger Public API as MCP tools:
  - kroger_search_products: Search products at a Kroger store
  - kroger_find_stores: Find nearby Kroger stores by ZIP
  - kroger_add_to_cart: Add items to user's Kroger cart
  - kroger_shopping_list_to_cart: Match shopping list items to Kroger products

Uses stdio transport. See README.md for installation and configuration.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration: load .env (search CWD then script directory)
# ---------------------------------------------------------------------------

def _load_env():
    """Load .env from CWD or script directory (CWD wins if both exist)."""
    cwd_env = Path.cwd() / ".env"
    script_env = Path(__file__).resolve().parent / ".env"
    for candidate in (cwd_env, script_env):
        if candidate.exists():
            load_dotenv(candidate)
            return

_load_env()

# Token storage directory (default: ~/.kroger-mcp/)
# Override with KROGER_TOKEN_DIR env var.
_TOKEN_DIR = Path(os.getenv("KROGER_TOKEN_DIR", Path.home() / ".kroger-mcp")).expanduser()
_TOKEN_DIR.mkdir(parents=True, exist_ok=True)

USER_TOKEN_FILE = str(_TOKEN_DIR / "user_token.json")
CLIENT_TOKEN_FILE = str(_TOKEN_DIR / "client_token.json")

# Switch CWD into the token dir so kroger-api's relative-path token storage works
os.chdir(_TOKEN_DIR)

from kroger_api import KrogerAPI
from kroger_api.token_storage import load_token


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _get_credentials():
    client_id = os.getenv("KROGER_CLIENT_ID")
    client_secret = os.getenv("KROGER_CLIENT_SECRET")
    redirect_uri = os.getenv("KROGER_REDIRECT_URI", "http://localhost:8000/callback")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing KROGER_CLIENT_ID or KROGER_CLIENT_SECRET. "
            "Create a .env file with these values. See README.md for setup."
        )
    return client_id, client_secret, redirect_uri


# ---------------------------------------------------------------------------
# API helpers (cached per-session)
# ---------------------------------------------------------------------------

_client_api = None  # for search / stores (client credentials)
_user_api = None    # for cart (user token)


def _get_client_api():
    """Get a KrogerAPI with client credentials (for search & stores)."""
    global _client_api
    if _client_api is None:
        cid, secret, redirect = _get_credentials()
        _client_api = KrogerAPI(cid, secret, redirect)
        _client_api.client.get_token_with_client_credentials(scope="product.compact")
    return _client_api


def _get_user_api():
    """Get a KrogerAPI with user auth (for cart operations)."""
    global _user_api
    if _user_api is None:
        cid, secret, redirect = _get_credentials()
        token_info = load_token(USER_TOKEN_FILE)
        if not token_info:
            raise RuntimeError(
                f"No user token found at {USER_TOKEN_FILE}. "
                "Run `python kroger_auth.py` to authorize your Kroger account first."
            )
        api = KrogerAPI(cid, secret, redirect)
        api.client.token_info = token_info
        api.client.token_file = USER_TOKEN_FILE
        if not api.client.test_token(token_info):
            raise RuntimeError(
                "Kroger user token is expired and could not be refreshed. "
                "Run `python kroger_auth.py` to re-authenticate."
            )
        _user_api = api
    return _user_api


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("Kroger")


@mcp.tool()
def kroger_search_products(term: str, location_id: str, limit: int = 5) -> str:
    """Search for products at a Kroger store.

    Args:
        term: Search term (e.g. "chicken breast", "jasmine rice")
        location_id: Kroger store location ID (use kroger_find_stores to get one)
        limit: Max number of results (default 5)

    Returns:
        JSON list of matching products with name, brand, UPC, price, and size.
    """
    api = _get_client_api()
    results = api.product.search_products(
        term=term, location_id=location_id, limit=limit
    )
    products = results.get("data", [])
    if not products:
        return json.dumps({"results": [], "message": f"No products found for '{term}'"})

    formatted = []
    for p in products:
        entry = {
            "description": p.get("description", "Unknown"),
            "brand": p.get("brand", ""),
            "upc": p.get("upc", ""),
        }
        items = p.get("items", [])
        if items:
            price = items[0].get("price", {})
            regular = price.get("regular", 0)
            promo = price.get("promo", 0)
            entry["price_regular"] = regular
            entry["price_promo"] = promo if promo and promo < regular else None
            entry["size"] = items[0].get("size", "")
        formatted.append(entry)

    return json.dumps({"results": formatted})


@mcp.tool()
def kroger_find_stores(zip_code: str, limit: int = 5) -> str:
    """Find Kroger stores near a ZIP code.

    Args:
        zip_code: US ZIP code to search near
        limit: Max number of results (default 5)

    Returns:
        JSON list of nearby stores with name, location_id, and address.
    """
    api = _get_client_api()
    results = api.location.search_locations(zip_code=zip_code, limit=limit)
    stores = results.get("data", [])
    if not stores:
        return json.dumps({"stores": [], "message": f"No stores found near {zip_code}"})

    formatted = []
    for s in stores:
        addr = s.get("address", {})
        formatted.append({
            "name": s.get("name", "Unknown"),
            "location_id": s.get("locationId", ""),
            "address": f"{addr.get('addressLine1', '')}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zipCode', '')}",
        })

    return json.dumps({"stores": formatted})


@mcp.tool()
def kroger_add_to_cart(items: list[dict]) -> str:
    """Add items to the user's Kroger cart by UPC.

    Args:
        items: List of objects, each with "upc" (string) and "quantity" (int).
               Example: [{"upc": "0001111041700", "quantity": 1}]

    Returns:
        Success or error message.
    """
    if not items:
        return json.dumps({"error": "No items provided"})

    for item in items:
        if "upc" not in item or "quantity" not in item:
            return json.dumps({"error": f"Each item needs 'upc' and 'quantity'. Got: {item}"})

    api = _get_user_api()
    api.cart.add_to_cart(items)
    return json.dumps({
        "success": True,
        "message": f"Added {len(items)} item(s) to your Kroger cart.",
        "items_added": items,
    })


@mcp.tool()
def kroger_shopping_list_to_cart(
    items: list[str], location_id: str, quantity: int = 1
) -> str:
    """Search Kroger for each item in a shopping list and return matches.

    This does NOT add to cart automatically. It returns the best match for each
    item so the user can review before calling kroger_add_to_cart.

    Args:
        items: List of ingredient/product names (e.g. ["chicken breast", "jasmine rice", "broccoli"])
        location_id: Kroger store location ID
        quantity: Default quantity per item (default 1)

    Returns:
        JSON with matched items (including UPC and price) and items not found.
    """
    api = _get_client_api()
    matched = []
    not_found = []

    for item_name in items:
        try:
            results = api.product.search_products(
                term=item_name, location_id=location_id, limit=3
            )
            products = results.get("data", [])
        except Exception:
            products = []

        if not products:
            not_found.append(item_name)
            continue

        options = []
        for p in products:
            entry = {
                "description": p.get("description", "Unknown"),
                "brand": p.get("brand", ""),
                "upc": p.get("upc", ""),
            }
            items_data = p.get("items", [])
            if items_data:
                price = items_data[0].get("price", {})
                entry["price"] = price.get("promo") or price.get("regular", 0)
                entry["size"] = items_data[0].get("size", "")
            options.append(entry)

        matched.append({
            "search_term": item_name,
            "quantity": quantity,
            "options": options,
        })

    total_estimate = 0
    for m in matched:
        if m["options"]:
            best_price = m["options"][0].get("price", 0) or 0
            total_estimate += best_price * m["quantity"]

    return json.dumps({
        "matched": matched,
        "not_found": not_found,
        "estimated_total": round(total_estimate, 2),
        "summary": f"{len(matched)} items matched, {len(not_found)} not found",
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
