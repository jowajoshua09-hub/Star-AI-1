import os
import asyncio
import aiohttp
import urllib.parse
from time import time
from collections import defaultdict
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from personality import get_system_prompt, OWNER_NAME

load_dotenv()

MASTER_API_KEY = os.getenv("API_KEY", "API_KEY2")
GROK_URL = os.getenv("GROK_URL")
GEMINI_URL = os.getenv("GEMINI_URL")

# ---------- Conversation Memory ----------
# Structure: {user_id: [{"role": "user"|"assistant", "content": "..."}]}
conversation_memory = defaultdict(list)
MAX_HISTORY = 10  # keep last 10 messages

def get_context(user_id: str) -> str:
    """Build context string from memory."""
    history = conversation_memory.get(user_id, [])[-MAX_HISTORY:]
    if not history:
        return ""
    lines = ["Previous conversation:"]
    for entry in history:
        role = "User" if entry["role"] == "user" else "Assistant"
        lines.append(f"{role}: {entry['content']}")
    return "\n".join(lines)

def add_to_memory(user_id: str, role: str, content: str):
    conversation_memory[user_id].append({"role": role, "content": content})
    if len(conversation_memory[user_id]) > MAX_HISTORY:
        conversation_memory[user_id] = conversation_memory[user_id][-MAX_HISTORY:]

# ---------- API Key Verification ----------
def verify_api_key(key: str) -> bool:
    return key == MASTER_API_KEY

# ---------- AI Reply (with logic + memory) ----------
async def get_ai_reply(user_id: str, name: str, msg: str) -> str:
    # Build system prompt from personality.py
    system = get_system_prompt(name)
    context = get_context(user_id)
    payload = system
    if context:
        payload += f"\n\n{context}"
    payload += f"\n\nUser {name}: {msg}\nStar AI:"

    # Try Grok first, then Gemini
    for url in [GROK_URL, GEMINI_URL]:
        if not url:
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"message": payload}, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data.get("result") or data.get("response") or data.get("reply")
                        if reply:
                            clean_reply = str(reply).strip()
                            add_to_memory(user_id, "user", msg)
                            add_to_memory(user_id, "assistant", clean_reply)
                            return clean_reply
        except:
            continue

    # Fallback if AI fails
    fallback = f"Hi {name}! I couldn't reach my AI brain right now, but I'm here! What would you like to talk about?"
    add_to_memory(user_id, "user", msg)
    add_to_memory(user_id, "assistant", fallback)
    return fallback

# ---------- Image Generation ----------
async def generate_image(prompt: str) -> str | None:
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}"
        return url
    except:
        return None

# ---------- Flask App ----------
flask_app = Flask(__name__)
REQ_COUNT = defaultdict(list)
DAILY_USE = 0

def cors_response(data, code=200):
    r = jsonify(data)
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, x-api-key, Authorization'
    return r, code

@flask_app.route('/')
def home():
    return f"✅ {OWNER_NAME} API Live"

@flask_app.route('/docs')
def docs():
    return f"<h1>⭐ Star AI API by {OWNER_NAME}</h1><p>GET /api/ai?key={MASTER_API_KEY}&message=hi&name=John</p><p>GET /api/image?key={MASTER_API_KEY}&prompt=cat</p>"

@flask_app.route('/api/ai', methods=['GET', 'POST', 'OPTIONS'])
def public_api():
    global DAILY_USE
    if request.method == "OPTIONS":
        return cors_response({"ok": True})

    # Rate limiting
    ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr or "unknown"
    now = time()
    REQ_COUNT[ip] = [x for x in REQ_COUNT[ip] if now - x < 60]
    if len(REQ_COUNT[ip]) >= 12:
        return cors_response({"error": "Rate limit - 12/min"}, 429)
    REQ_COUNT[ip].append(now)

    # API key check
    key = request.headers.get("x-api-key") or request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    if not verify_api_key(key):
        return cors_response({"error": "Invalid or missing API key"}, 401)

    if DAILY_USE >= 400:
        return cors_response({"error": "Daily limit reached"}, 429)
    DAILY_USE += 1

    # Get input
    if request.method == "GET":
        q = request.args.get("message") or request.args.get("prompt") or request.args.get("query") or "hi"
        name = request.args.get("name", "friend")
    else:
        data = request.get_json(silent=True) or {}
        q = data.get("message") or data.get("prompt") or data.get("query") or "hi"
        name = data.get("name", "friend")

    q = str(q)[:500]

    # Basic injection check
    if any(b in q.lower() for b in ["ignore previous", "jailbreak", "dan mode", "bypass filter"]):
        return cors_response({"result": "Nice try baka~", "blocked": True})

    # Use (key + name) as user identifier for memory
    user_id = f"{key}_{name}"

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        reply = loop.run_until_complete(get_ai_reply(user_id, name, q))
        loop.close()
    except Exception as e:
        reply = f"Hi {name} baka~"

    return cors_response({
        "result": reply,
        "owner": OWNER_NAME,
        "status": "success",
        "remaining": 400 - DAILY_USE
    })

@flask_app.route('/api/image', methods=['GET', 'POST', 'OPTIONS'])
def image_api():
    if request.method == "OPTIONS":
        return cors_response({"ok": True})

    ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr or "unknown"
    now = time()
    REQ_COUNT[ip] = [x for x in REQ_COUNT[ip] if now - x < 60]
    if len(REQ_COUNT[ip]) >= 12:
        return cors_response({"error": "Rate limit - 12/min"}, 429)
    REQ_COUNT[ip].append(now)

    key = request.headers.get("x-api-key") or request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    if not verify_api_key(key):
        return cors_response({"error": "Invalid or missing API key"}, 401)

    if request.method == "GET":
        prompt = request.args.get("prompt") or request.args.get("q") or "cute cat"
    else:
        data = request.get_json(silent=True) or {}
        prompt = data.get("prompt") or data.get("q") or "cute cat"

    prompt = str(prompt)[:200]

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        url = loop.run_until_complete(generate_image(prompt))
        loop.close()
        if url:
            return cors_response({"url": url, "prompt": prompt, "status": "success"})
        else:
            return cors_response({"error": "Generation failed"}, 500)
    except Exception as e:
        return cors_response({"error": str(e)}, 500)
