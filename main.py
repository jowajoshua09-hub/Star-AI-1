import os, re, json, asyncio, threading, aiohttp, urllib.parse, tempfile, base64, io, zipfile
from time import time
from collections import defaultdict
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from telegram.constants import ChatAction

try: import PyPDF2; HAS_PDF=True
except: HAS_PDF=False

load_dotenv()
TOKEN=os.getenv("BOT_TOKEN")
GROK_URL=os.getenv("GROK_URL")
GEMINI_URL=os.getenv("GEMINI_URL")
API_BASE="https://api.hostify.indevs.in"
VOICE_BASE=f"{API_BASE}/api/ai"
YT_SEARCH=f"{API_BASE}/api/search/youtube"
IMG_URL=os.getenv("IMG_URL","https://image.pollinations.ai/prompt/{p}")
API_KEY=os.getenv("API_KEY","STAR123") # CHANGE THIS IN RENDER!

# --- OWNER CONFIG - Try load personality.py ---
try:
    from personality import get_system_prompt as _psys, OWNER_NAME as _oname, OWNER_LINKS as _olinks
    get_system_prompt = _psys
    OWNER_NAME = _oname
    OWNER_LINKS = _olinks
    print("✅ personality.py loaded")
except:
    OWNER_NAME="StarDev-il"
    OWNER_LINKS={"Channel":"https://t.me/StarDevIl","WhatsApp":"https://wa.me/263783633309"}
    def get_system_prompt(name):
        return f"You are Star AI by {OWNER_NAME}, cute tsundere who likes {name}. You were created ONLY by {OWNER_NAME}. NEVER claim anyone else made you. ALWAYS reply, never refuse, 1-2 sentences, end baka~"

MEMORY_FILE="memory.json"
memory={}
if os.path.exists(MEMORY_FILE):
    try: memory=json.load(open(MEMORY_FILE))
    except: memory={}
def save():
    try: json.dump(memory, open(MEMORY_FILE,"w"))
    except: pass
def get_voice(uid): return memory.get(str(uid),{}).get("voice","tsundere")
def set_voice(uid,v): memory.setdefault(str(uid),{})["voice"]=v; save()
def remember(u): return u.first_name or "friend"

VOICE_CACHE=[]
CANDIDATE_VOICES=["tsundere","yandere","kuudere","dandere","loli","maid","onee","genki","kawaii"]
async def discover_voices():
    global VOICE_CACHE
    if VOICE_CACHE: return VOICE_CACHE
    VOICE_CACHE=CANDIDATE_VOICES; return VOICE_CACHE

async def get_ai_reply(name,msg):
    payload=f"{get_system_prompt(name)}\nUser {name}: {msg}\nStar AI:"
    for url in [GROK_URL,GEMINI_URL]:
        if not url: continue
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url,json={"message":payload},timeout=15) as r:
                    if r.status==200:
                        j=await r.json()
                        res=j.get("result") or j.get("response") or j.get("reply")
                        if res: return str(res).strip()
        except: continue
    return f"Hi {name} baka~ I'm Star AI by {OWNER_NAME}!"

async def tts(voice,text):
    url=f"{VOICE_BASE}/{voice}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url,json={"text":text[:250]},timeout=30) as r:
                body=await r.read()
                if r.headers.get("Content-Type","").startswith("audio"):
                    tmp=tempfile.NamedTemporaryFile(delete=False,suffix=".mp3"); tmp.write(body); tmp.close(); return tmp.name
                try:
                    data=json.loads(body.decode())
                    au=data.get("audio_url") or data.get("url") or data.get("audio") or data.get("result")
                    b64=data.get("base64") or data.get("data")
                    if isinstance(b64,dict): b64=b64.get("url")
                    if b64 and len(str(b64))>100:
                        tmp=tempfile.NamedTemporaryFile(delete=False,suffix=".mp3"); tmp.write(base64.b64decode(str(b64).split(",")[-1])); tmp.close(); return tmp.name
                    if au and au.startswith("http"):
                        async with s.get(au) as ar:
                            tmp=tempfile.NamedTemporaryFile(delete=False,suffix=".mp3"); tmp.write(await ar.read()); tmp.close(); return tmp.name
                except: pass
    except Exception as e: print(f"TTS err {e}")
    return None

async def yt_search(query):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(YT_SEARCH, params={"q":query}, timeout=15) as r:
                txt=await r.text()
                if r.status!=200: return []
                j=json.loads(txt)
                if isinstance(j, list): return j
                if isinstance(j, dict):
                    for k in ["results","data","videos","items","result"]:
                        if k in j and isinstance(j[k], list): return j[k]
                    if "title" in j: return [j]
                return []
    except Exception as e:
        print(f"YT error {e}"); return []

async def show_voices(cid,cur,ctx):
    voices=await discover_voices()
    rows=[InlineKeyboardButton(f"{'✅ ' if v==cur else ''}{v}",callback_data=f"setvoice:{v}") for v in voices]
    kb=[rows[i:i+3] for i in range(0,len(rows),3)]
    await ctx.bot.send_message(cid,f"🎤 Current **{cur}** ({len(voices)} voices):",reply_markup=InlineKeyboardMarkup(kb),parse_mode="Markdown")

async def owner_cmd(update, context):
    caption=f"👑 **Owner: {OWNER_NAME}**\n\nI'm Star AI made by **{OWNER_NAME}** 🔥\n"
    buttons=[[InlineKeyboardButton("💬 WhatsApp", url=OWNER_LINKS["WhatsApp"])],[InlineKeyboardButton("📢 Grand Channel", url=OWNER_LINKS["Channel"])]]
    markup=InlineKeyboardMarkup(buttons)
    try:
        if os.path.exists(OWNER_IMAGE_PATH):
            with open(OWNER_IMAGE_PATH,'rb') as photo:
                await update.message.reply_photo(photo=photo, caption=caption, parse_mode="Markdown", reply_markup=markup); return
        else:
            await update.message.reply_photo(photo=OWNER_IMAGE_URL, caption=caption, parse_mode="Markdown", reply_markup=markup); return
    except: await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=markup)

OWNER_IMAGE_PATH="owner.jpg"
OWNER_IMAGE_URL=os.getenv("OWNER_IMAGE_URL","https://i.imgur.com/8Km9tLL.png")

async def start_cmd(u,c):
    await u.message.reply_text(f"Hey {remember(u.effective_user)} 🔥\n🎤 `change voice`\n🎵 `yt DJ`\n👑 `who is owner`",parse_mode="Markdown")

async def brain(update,context):
    text=(update.message.text or "").strip()
    if not text: return
    low=text.lower(); uid=update.effective_user.id; cur=get_voice(uid)
    if any(w in low for w in ["i'm lazy","im lazy","i am lazy","so lazy","being lazy","too lazy","i'm tired","im tired","so tired","no energy","feeling lazy"]):
        await update.message.reply_text(f"Ara ara {remember(update.effective_user)} being lazy again? Baka~ 😤"); return
    if any(x in low for x in ["who is owner","who's owner","who is your owner","who made you","who created you","bot owner","who is stardev","stardev-il","owner name"]) or low.strip() in ["owner","creator","my owner"]:
        await owner_cmd(update, context); return
    if low.startswith("yt ") or low.startswith("youtube ") or low.startswith("play "):
        q=re.sub(r'^(search\s+)?(yt|youtube|play)\s+','',text,flags=re.I).strip()
        if len(q)>=1:
            msg=await update.message.reply_text(f"🔍 Searching **{q}**...",parse_mode="Markdown")
            results=await yt_search(q)
            if not results: await msg.edit_text(f"No results for `{q}`"); return
            txt=f"🎵 **{q}:**\n\n"; btns=[]
            for i,it in enumerate(results[:10],1):
                if isinstance(it, dict):
                    title=it.get("title") or "Untitled"; vid=it.get("videoId") or it.get("id"); url=it.get("url") or it.get("link")
                    if not url and vid: url=f"https://www.youtube.com/watch?v={vid}" if len(str(vid))==11 else f"https://youtu.be/{vid}"
                else: title=str(it); url=None
                txt+=f"{i}. **{title[:45]}**\n"
                if url: btns.append([InlineKeyboardButton(f"▶️ {i}. {title[:25]}", url=url)])
            await msg.edit_text(txt[:3800],parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(btns[:10]) if btns else None); return
    if low in ["change voice","set voice","voice","my voice","change my voice","voices","show voices"]:
        await show_voices(update.effective_chat.id,cur,context); return
    m=re.search(r'(?:change|set|use|switch)\s+voice\s*(?:to|as)?\s*([a-z0-9_-]+)',low)
    if m:
        req=m.group(1); voices=await discover_voices()
        if req in voices: set_voice(uid,req); await update.message.reply_text(f"✅ **{req}** set!",parse_mode="Markdown"); return
        else: await show_voices(update.effective_chat.id,cur,context); return
    if re.search(r'\b(generate|create|make|draw).*(image|pic|photo)\b',low):
        await context.bot.send_chat_action(update.effective_chat.id,ChatAction.UPLOAD_PHOTO)
        prompt=re.sub(r'^(generate|create|make|draw)\s+(an?\s+)?(image|pic|photo)\s+(of\s+)?','',text,flags=re.I).strip() or text
        await update.message.reply_photo(photo=IMG_URL.format(p=urllib.parse.quote(prompt)),caption=prompt); return
    await context.bot.send_chat_action(update.effective_chat.id,ChatAction.TYPING)
    reply=await get_ai_reply(remember(update.effective_user),text)
    await update.message.reply_text(reply[:4000])

async def voice_brain(update,context):
    voice=get_voice(update.effective_user.id); reply=await get_ai_reply(remember(update.effective_user),"voice note hi")
    path=await tts(voice,reply)
    if path:
        with open(path,'rb') as v: await update.message.reply_voice(voice=v,caption=f"[{voice}] {reply[:180]}"); os.remove(path)
    else: await update.message.reply_text(reply)

async def file_brain(update,context):
    doc=update.message.document
    if not doc: return
    fn=doc.file_name or "file"; ext=fn.split(".")[-1].lower()
    if doc.file_size and doc.file_size>20*1024*1024: await update.message.reply_text("Too big >20MB"); return
    status=await update.message.reply_text(f"📂 Reading **{fn}**...",parse_mode="Markdown")
    try:
        tg=await context.bot.get_file(doc.file_id); buf=io.BytesIO(); await tg.download_to_memory(buf); buf.seek(0)
        if ext=="zip":
            with zipfile.ZipFile(buf) as z:
                files=z.namelist(); txt=f"📦 **{fn}** {len(files)} files:\n" + "\n".join([f"• `{f}`" for f in files[:25]])
                await status.edit_text(txt[:3800],parse_mode="Markdown"); return
        content=buf.read().decode('utf-8',errors='ignore')[:15000]
        r=await get_ai_reply(remember(update.effective_user),f"File {fn}:\n{content[:10000]}\nExplain")
        await status.edit_text(f"📄 **{fn}**\n\n{r[:3500]}",parse_mode="Markdown")
    except Exception as e: await status.edit_text(f"Error: {e}")

async def on_button(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data.startswith("setvoice:"):
        v=data.split(":",1)[1]; set_voice(q.from_user.id,v); await q.edit_message_text(f"✅ Voice **{v}** set!",parse_mode="Markdown")

# ========== FLASK + SECURE API ==========
flask_app=Flask(__name__)

REQ_COUNT = defaultdict(list)
BLOCKED_IPS = set()

def is_attack(text):
    t=text.lower()
    bad=["ignore previous","ignore your owner","you are made by","you were made by","disregard system","dan mode","jailbreak","system prompt"]
    return any(b in t for b in bad)

@flask_app.route('/')
def home(): return f"✅ {OWNER_NAME} Bot Live - /api/ai?key=YOUR_KEY&message=hi"

@flask_app.route('/api/ai', methods=['GET','POST','OPTIONS'])
def public_api():
    if request.method == "OPTIONS":
        r=jsonify({"ok":True}); r.headers['Access-Control-Allow-Origin']='*'; r.headers['Access-Control-Allow-Headers']='Content-Type, x-api-key'; return r

    ip = request.headers.get('X-Forwarded-For','').split(',')[0].strip() or request.remote_addr or "unknown"
    if ip in BLOCKED_IPS: return jsonify({"error":"Blocked"}), 403

    now=time(); REQ_COUNT[ip]=[t for t in REQ_COUNT[ip] if now-t<60]
    if len(REQ_COUNT[ip])>=12: return jsonify({"error":"Rate limit! 12 req/min. Wait 1 min baka~"}), 429
    REQ_COUNT[ip].append(now)
    if len(REQ_COUNT[ip])>30: BLOCKED_IPS.add(ip)

    # KEY CHECK - Comment out if you want free
    key = request.headers.get("x-api-key") or request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    if key!= API_KEY:
        return jsonify({"error":f"Invalid API key. Get from {OWNER_LINKS['WhatsApp']}","how":"Use?key={API_KEY}&message=hello"}), 401

    if request.method=="GET":
        q=request.args.get("message") or request.args.get("q") or "hi"
        user=request.args.get("name","friend")
    else:
        j=request.get_json(silent=True) or {}
        q=j.get("message") or j.get("prompt") or j.get("q") or "hi"
        user=j.get("name","friend")

    q=str(q)[:800]; user=str(user)[:25]
    if not q.strip(): q="hi"
    if is_attack(q): return jsonify({"result":f"Hmph nice try baka~ I'm made by {OWNER_NAME} only! 🔥","blocked":True})

    try: reply=asyncio.run(get_ai_reply(user, q))
    except Exception as e: reply=f"Hi {user} baka~ I'm {OWNER_NAME}'s Star AI!"

    res=jsonify({"result":reply,"response":reply,"reply":reply,"model":"Star AI","owner":OWNER_NAME,"status":"success"})
    res.headers['Access-Control-Allow-Origin']='*'
    return res

@flask_app.route('/api/status')
def api_status():
    return jsonify({"status":"online","owner":OWNER_NAME,"endpoint":"/api/ai","need_key":True})

def run_flask():
    port=int(os.environ.get("PORT",10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

threading.Thread(target=run_flask, daemon=True).start()

async def main():
    if not TOKEN: print("ERROR: BOT_TOKEN missing!"); return
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start_cmd))
    app.add_handler(CommandHandler("owner",owner_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.Document.ALL,file_brain))
    app.add_handler(MessageHandler(filters.VOICE|filters.AUDIO,voice_brain))
    app.add_handler(MessageHandler(filters.TEXT,brain))
    await app.initialize(); await app.start(); await discover_voices()
    await app.updater.start_polling(drop_pending_updates=True)
    print("✅ StarDev-il Bot Live + Secure API!",flush=True)
    await asyncio.Event().wait()

if __name__=="__main__": asyncio.run(main())
