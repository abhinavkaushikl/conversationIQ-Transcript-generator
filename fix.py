#!/usr/bin/env python3
"""
Improved websocket checker.

- Probes TCP connect to a list of hosts/ports.
- Sends a raw HTTP "Upgrade: websocket" request and prints the exact response.
- Only attempts websockets.connect() if the raw response looks like a websocket handshake (101 or Upgrade header).
- Clear logging + helpful tips.
"""
import asyncio
import socket
import logging
import sys
import os
from websockets import connect as ws_connect

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HOSTS = ["127.0.0.1", "localhost"]
PORT = 8080           # change if you want to target a different default
PATH = "ws/twilio"    # no leading slash (we add it when we format)
RAW_TIMEOUT = 2.0     # seconds to wait for raw response read

def tcp_connect(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if TCP connect succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def raw_upgrade_probe(host: str, port: int, path: str, timeout: float = RAW_TIMEOUT) -> str | None:
    """
    Send a raw HTTP WebSocket upgrade GET and return the bytes response (decoded).
    Returns None on connection failure.
    """
    req = (
        f"GET /{path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: probe_test_key==\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("utf-8")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.sendall(req)
        # read up to 8k bytes (usually enough to see headers)
        resp = b""
        try:
            resp = s.recv(8192)
        except socket.timeout:
            # some servers may not respond quickly — we still return whatever we got
            pass
        finally:
            s.close()
        return resp.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug(f"raw_upgrade_probe connection error: {e}")
        return None

async def try_websocket(uri: str) -> tuple[bool,str]:
    """Attempt websockets.connect, return (success, message)."""
    try:
        async with ws_connect(uri, close_timeout=5, open_timeout=3, ping_interval=None, ping_timeout=None) as ws:
            # try a ping/pong roundtrip if server accepts
            try:
                await ws.ping()
            except Exception:
                pass
            return True, "connected"
    except Exception as e:
        return False, str(e)

async def check():
    # First find a reachable host:port
    reachable = None
    for host in HOSTS:
        if tcp_connect(host, PORT):
            logger.debug(f"Port {PORT} is open on {host}")
            reachable = host
            break

    if not reachable:
        print(f"\n❌ Port {PORT} is not open on any host in {HOSTS}")
        print("\nStart your server (example):")
        print(f"1. cd {os.path.dirname(os.path.dirname(__file__))}")
        print("2. source venv/bin/activate")
        print("3. PYTHONPATH=$PYTHONPATH:/Users/abhinavkaushik/conversiq_transcript_pipeline python converseiq_transcript_service/app.py")
        return False

    host = reachable
    uri_base = f"ws://{host}:{PORT}/{PATH}"
    print(f"\nDetected open TCP on {host}:{PORT}. Now sending a raw HTTP Upgrade probe to see server response...")

    raw = raw_upgrade_probe(host, PORT, PATH)
    if raw is None:
        print("\n❌ Raw probe failed (could not connect or timed out).")
        print(" - Is there a proxy or TLS terminating before the application?")
        return False

    # Print a readable truncated raw response (but enough context)
    print("\n--- RAW SERVER RESPONSE (first 2000 bytes) ---")
    to_show = raw[:2000]
    # show CRLF explicitly to be clear
    print(to_show.replace("\r", "\\r"))
    print("--- END RAW RESPONSE ---\n")

    # Inspect response for expected websocket handshake hints
    lower = raw.lower()
    if "101 switching protocols" in lower or "upgrade: websocket" in lower:
        print("Server raw response indicates a websocket handshake (101/Upgrade present). Attempting websockets.connect() now...")
        ok, msg = await try_websocket(uri_base)
        if ok:
            print(f"\n✅ Successfully connected to {uri_base}")
            return True
        else:
            print(f"\n❌ websockets.connect failed for {uri_base}")
            print("   Error:", msg)
            # show suggestion: maybe TLS or proxy mismatch
            if "ssl" in msg.lower() or "certificate" in msg.lower():
                print("   Hint: server may expect wss:// (TLS) rather than ws://. Try wss:// or configure TLS.")
            return False
    else:
        print("Server did NOT return a websocket handshake (101/Upgrade header).")
        # Give hints based on common responses
        if raw.startswith("HTTP/1.1") or raw.startswith("HTTP/2"):
            # show status code line
            first_line = raw.splitlines()[0] if raw.splitlines() else "<no response line>"
            print(f" - Server responded with: {first_line}")
            if "200" in first_line:
                print("   Hint: This path is probably served by plain HTTP (200 OK) not a websocket endpoint.")
            elif "404" in first_line:
                print("   Hint: Path probably not found (404). Verify the websocket route '/{PATH}' exists on the server.")
            else:
                print("   Hint: The server responded with a regular HTTP status. Ensure the server has a websocket route at this path.")
        else:
            print(" - The response looks non-HTTP or binary; possibly a TLS endpoint or a non-HTTP service on that port.")
            print("   Hint: If you're running TLS, try wss:// or run the raw probe against the TLS endpoint using openssl s_client.")
        # Extra common suggestions
        print("\nSuggested next steps:")
        print(" 1) Verify your server has a websocket handler registered at exactly '/{}'.".format(PATH))
        print(" 2) If using a reverse proxy (nginx/Caddy), ensure it forwards Upgrade/Connection headers.")
        print(" 3) If server expects wss://, test with wss:// or dial TLS first (openssl s_client).")
        return False

if __name__ == "__main__":
    try:
        ok = asyncio.run(check())
        if not ok:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled by user")
        sys.exit(1)
