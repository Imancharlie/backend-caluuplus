"""Standalone Gemini connectivity test for Mr. Caluu.

Loads GEMINI_API_KEY / GEMINI_MODEL from .env.production (no Django needed),
then:
  1. Prints the key fingerprint (masked) so we can sanity-check its format.
  2. Lists available models (verifies auth).
  3. Sends a minimal generate_content request (verifies inference).
  4. Sends a streaming request (verifies SSE path used by the chatbot).

Run:  .venv/Scripts/python.exe test_gemini_connection.py
"""
import os
import sys


def load_env(path=".env.production"):
    if not os.path.exists(path):
        print(f"[!] {path} not found")
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def mask(secret: str) -> str:
    if not secret:
        return "<empty>"
    if len(secret) <= 10:
        return secret[:2] + "****"
    return f"{secret[:6]}...{secret[-4:]} (len={len(secret)})"


def main():
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

    print("=" * 60)
    print("GEMINI CONNECTION TEST")
    print("=" * 60)
    print(f"API key : {mask(key)}")
    print(f"Model   : {model}")
    if key.startswith("AIza"):
        print("Key format: standard Google AI Studio key (AIza...) OK")
    elif key.startswith("AQ."):
        print("Key format: WARNING - starts with 'AQ.' which is NOT a standard")
        print("            Gemini API key (those start with 'AIza'). This is")
        print("            likely an OAuth/service token and may be rejected.")
    else:
        print("Key format: unrecognized prefix")
    print("-" * 60)

    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        print(f"[FAIL] google-genai not importable: {e}")
        sys.exit(1)

    if not key:
        print("[FAIL] No GEMINI_API_KEY set.")
        sys.exit(1)

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))

    # Step 1: list models (auth check)
    print("[1] Listing models (auth check)...")
    try:
        names = []
        for m in client.models.list():
            names.append(getattr(m, "name", str(m)))
            if len(names) >= 15:
                break
        print(f"    OK - {len(names)} model(s) visible. Sample:")
        for n in names[:15]:
            print(f"      - {n}")
    except Exception as e:
        print(f"    [FAIL] models.list error: {type(e).__name__}: {e}")

    # Step 2: minimal generate_content
    print("-" * 60)
    print(f"[2] generate_content with model='{model}'...")
    try:
        resp = client.models.generate_content(
            model=model,
            contents="Reply with exactly the word: PONG",
            config=types.GenerateContentConfig(max_output_tokens=10, temperature=0.0),
        )
        print(f"    OK - response.text = {resp.text!r}")
        um = getattr(resp, "usage_metadata", None)
        if um:
            print(f"    usage: in={getattr(um,'prompt_token_count',None)} "
                  f"out={getattr(um,'candidates_token_count',None)}")
    except Exception as e:
        print(f"    [FAIL] generate_content error: {type(e).__name__}: {e}")

    # Step 3: streaming
    print("-" * 60)
    print("[3] generate_content_stream...")
    try:
        chunks = []
        for chunk in client.models.generate_content_stream(
            model=model,
            contents="Count from 1 to 5.",
            config=types.GenerateContentConfig(max_output_tokens=50),
        ):
            t = getattr(chunk, "text", None) or ""
            if t:
                chunks.append(t)
        print(f"    OK - {len(chunks)} chunk(s). Joined: {''.join(chunks)!r}")
    except Exception as e:
        print(f"    [FAIL] streaming error: {type(e).__name__}: {e}")

    print("=" * 60)


if __name__ == "__main__":
    main()
