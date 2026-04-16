#!/usr/bin/env python3
"""
Kroger OAuth2 Authentication Setup

One-time OAuth2 authorization flow needed for cart operations. Generates an
authorization URL, waits for the user to log in and authorize, then exchanges
the code for access + refresh tokens. Tokens auto-refresh after this.

Usage:
    python kroger_auth.py            # full auth flow
    python kroger_auth.py --status   # check current auth state
    python kroger_auth.py --verify   # try refreshing existing token

Reads credentials from .env (KROGER_CLIENT_ID, KROGER_CLIENT_SECRET,
KROGER_REDIRECT_URI). Saves tokens to $KROGER_TOKEN_DIR (defaults to
~/.kroger-mcp/).
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env():
    cwd_env = Path.cwd() / ".env"
    script_env = Path(__file__).resolve().parent / ".env"
    for candidate in (cwd_env, script_env):
        if candidate.exists():
            load_dotenv(candidate)
            return

_load_env()

_TOKEN_DIR = Path(os.getenv("KROGER_TOKEN_DIR", Path.home() / ".kroger-mcp")).expanduser()
_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
USER_TOKEN_FILE = str(_TOKEN_DIR / "user_token.json")

# kroger-api uses relative paths for token storage; switch CWD into the token dir
os.chdir(_TOKEN_DIR)

from kroger_api import KrogerAPI


def check_credentials():
    client_id = os.getenv("KROGER_CLIENT_ID")
    client_secret = os.getenv("KROGER_CLIENT_SECRET")
    redirect_uri = os.getenv("KROGER_REDIRECT_URI", "http://localhost:8000/callback")

    if not client_id or not client_secret:
        print("ERROR: Kroger API credentials not found.")
        print()
        print("Create a .env file in the project root with:")
        print("  KROGER_CLIENT_ID=your_client_id")
        print("  KROGER_CLIENT_SECRET=your_secret")
        print("  KROGER_REDIRECT_URI=http://localhost:8000/callback")
        print()
        print("Get your credentials at: https://developer.kroger.com/")
        sys.exit(1)

    return client_id, client_secret, redirect_uri


def check_existing_token():
    token_file = Path(USER_TOKEN_FILE)
    if token_file.exists():
        try:
            with open(token_file) as f:
                token_data = json.load(f)
            if "refresh_token" in token_data:
                return token_data
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def do_auth_flow(client_id, client_secret, redirect_uri):
    api = KrogerAPI(client_id, client_secret, redirect_uri)
    scope = "product.compact cart.basic:write"
    auth_url = api.client.get_authorization_url(scope=scope)

    print("=" * 60)
    print("KROGER AUTHORIZATION")
    print("=" * 60)
    print()
    print("Step 1: Open this URL in your browser:")
    print()
    print(f"  {auth_url}")
    print()
    print("Step 2: Log in to your Kroger account and click 'Authorize'")
    print()
    print("Step 3: After redirect, copy the 'code' parameter from the URL.")
    print(f"  It will look like: {redirect_uri}?code=XXXXXX")
    print("  Copy just the XXXXXX part.")
    print()

    auth_code = input("Paste the authorization code here: ").strip()
    if not auth_code:
        print("No code provided. Exiting.")
        sys.exit(1)

    try:
        token_info = api.client.get_token_with_authorization_code(auth_code)
        print()
        print(f"SUCCESS! Tokens saved to {USER_TOKEN_FILE}")
        print("You can now use cart operations. The token will auto-refresh.")
        return token_info
    except Exception as e:
        print(f"\nERROR: Failed to get tokens: {e}")
        print("Make sure the authorization code is correct and hasn't expired.")
        sys.exit(1)


def verify_token(client_id, client_secret, redirect_uri):
    api = KrogerAPI(client_id, client_secret, redirect_uri)
    existing = check_existing_token()
    if existing and "refresh_token" in existing:
        try:
            api.client.token_info = existing
            api.client.token_file = USER_TOKEN_FILE
            new_token = api.client.refresh_token(existing["refresh_token"])
            print("Existing token refreshed successfully!")
            return new_token
        except Exception:
            print("Existing token is expired. Starting fresh authorization...")
            return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Kroger OAuth2 Authentication Setup")
    parser.add_argument("--verify", action="store_true",
                        help="Just verify/refresh existing token without full auth flow")
    parser.add_argument("--status", action="store_true",
                        help="Check if credentials and tokens are configured")
    args = parser.parse_args()

    client_id, client_secret, redirect_uri = check_credentials()

    if args.status:
        print(f"Client ID: {client_id[:8]}...{client_id[-4:]}")
        print(f"Redirect URI: {redirect_uri}")
        print(f"Token directory: {_TOKEN_DIR}")
        existing = check_existing_token()
        if existing:
            print(f"Token file: Found ({USER_TOKEN_FILE})")
            print(f"Has refresh token: {'refresh_token' in existing}")
        else:
            print("Token file: Not found — run auth flow first")
        return

    if args.verify:
        result = verify_token(client_id, client_secret, redirect_uri)
        if result:
            return

    result = verify_token(client_id, client_secret, redirect_uri)
    if result:
        return

    do_auth_flow(client_id, client_secret, redirect_uri)


if __name__ == "__main__":
    main()
