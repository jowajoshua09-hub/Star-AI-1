import os, asyncio, aiohttp, urllib.parse, random
from collections import defaultdict
from time import time
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from personality import get_system_prompt, OWNER_NAME

load_dotenv()

# YOUR 3 ENVS ON RENDER
STAR_API_KEY = os.getenv("STAR_API_KEY", os.getenv("API_KEY", "StarAI_9Kx4vLqW_8zT!"))
GROK_URL = os.getenv("GROK_URL")
GEMINI_URL = os.getenv("GEMINI_URL")

print(f"✅ Config Loaded | STAR_KEY={STAR_API_KEY[:6]}... | GROK={bool(GROK_URL)} GEMINI={bool(GEMINI_URL)}")

# ---------- Memory for Telegram ----------
conversation_memory = defaultdict(list)
MAX_HISTORY = 10

def get_context(user_id: str):
    hist = conversation_memory.get(user_id, [])[-MAX_HISTORY:]
    if not hist: return ""
    return "\n".join([f"{'User' if h['role']=='user' else 'Assistant'}: {h['content']}" for h in hist])

def add_memory(user_id, role, content):
    conversation_memory[user_id].append({"role": role, "content": content})
    if len(conversation_memory[user_id]) > MAX_HISTORY:
        conversation_memory[user_id] = conversation_memory[user_id][-MAX_HISTORY:]

# ---------- CORE AI FUNCTION - USED BY TELEGRAM BOT ----------
async def get_ai_reply(user_id: str, name: str, msg: str) -> str:
    system = get_system_prompt(name)
    context = get_context(user_id)
    full_prompt = f"{system}\n\n{context}\n\nUser {name}: {msg}\nStar AI:"

    for url in [GROK_URL, GEMINI_URL]:
        if not url:
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"message": full_prompt}, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data.get("result") or data.get("response") or data.get("reply") or data.get("text")
                        if reply and len(str(reply).strip()) > 1:
                            clean = str(reply).strip()
                            add_memory(user_id, "user", msg)
                            add_memory(user_id, "assistant", clean)
                            return clean
                    else:
                        txt = await resp.text()
                        print(f"Upstream {url} status {resp.status}: {txt[:300]}")
        except Exception as e:
            print(f"Upstream {url} failed: {e}")
            continue

    fallback = f"Hey {name}! My upstream is napping. Check GROK_URL / GEMINI_URL on Render."
    add_memory(user_id, "user", msg)
    add_memory(user_id, "assistant", fallback)
    return fallback

def generate_image_url(prompt: str) -> str:
    prompt = str(prompt).strip()[:600] or "cute cat"
    enc = urllib.parse.quote(prompt)
    seed = random.randint(1, 9999999)
    return f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&seed={seed}&nologo=true&enhance=true"

# ---------- FLASK FOR VERCEL SITE ----------
flask_app = Flask(__name__)
REQ_COUNT = defaultdict(list)

def cors_response(data, code=200):
    r = jsonify(data)
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, x-api-key'
    return r, code

@flask_app.route('/')
def home():
    return f"✅ {OWNER_NAME} API | STAR_KEY set={bool(STAR_API_KEY)} | GROK={bool(GROK_URL)} GEMINI={bool(GEMINI_URL)}", 200

@flask_app.route('/api/ai', methods=['GET','POST','OPTIONS'])
def public_api():
    if request.method == 'OPTIONS':
        return cors_response({"ok": True})

    # Rate limit
    ip = request.headers.get('X-Forwarded-For','').split(',')[0] or request.remote_addr or "anon"
    now = time()
    REQ_COUNT[ip] = [t for t in REQ_COUNT[ip] if now - t < 60]
    if len(REQ_COUNT[ip]) >= 20:
        return cors_response({"error":"Rate limit 20/min"}, 429)
    REQ_COUNT[ip].append(now)

    # Verify STAR AI KEY - this is your single key
    key = request.args.get("key") or request.headers.get("x-api-key") or (request.get_json(silent=True) or {}).get("key")
    if key!= STAR_API_KEY:
        # Allow Telegram bot internal calls (no key but has user_id)
        if not key and request.args.get("message"):
            pass # allow for testing without key
        else:
            return cors_response({"error": f"Invalid STAR_API_KEY. Use key={STAR_API_KEY}"}, 401)

    q = request.args.get("message") or request.args.get("prompt") or (request.get_json(silent=True) or {}).get("message") or "hi"
    name = request.args.get("name") or (request.get_json(silent=True) or {}).get("name") or "friend"

    # Image via same endpoint
    if q.lower().strip().startswith(("imagine","draw","generate image")):
        prompt = q.lower().replace("imagine","").replace("draw","").replace("generate image","").strip() or "cat"
        url = generate_image_url(prompt)
        return cors_response({"result": prompt, "image": url, "url": url, "status":"success"})

    # Text - reuse same get_ai_reply as Telegram
    user_id = f"vercel_{name}_{ip}"
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        reply = loop.run_until_complete(get_ai_reply(user_id, name, q))
        loop.close()
    except Exception as e:
        print(f"Loop error: {e}")
        reply = f"Error: {e}"

    return cors_response({"result": reply, "status":"success"})

@flask_app.route('/api/image', methods=['GET','POST','OPTIONS'])
def image_api():
    if request.method == 'OPTIONS': return cors_response({"ok": True})
    prompt = request.args.get("prompt") or (request.get_json(silent=True) or {}).get("prompt") or "cat"
    url = generate_image_url(prompt)
    return cors_response({"url": url, "image": url, "prompt": prompt})