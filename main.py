import os, re, json, asyncio, threading, aiohttp, tempfile, unicodedata
from time import time
from collections import defaultdict
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from telegram.constants import ChatAction

load_dotenv()
TOKEN=os.getenv("BOT_TOKEN")
GROK_URL=os.getenv("GROK_URL")
GEMINI_URL=os.getenv("GEMINI_URL")

API_BASE="https://api.hostify.indevs.in"
VOICE_BASE=f"{API_BASE}/api/ai"
YT_SEARCH=f"{API_BASE}/api/search/youtube"
API_KEY=os.getenv("API_KEY","STAR123")

OWNER_ID = 8695184641

from personality import get_system_prompt, OWNER_NAME, OWNER_LINKS
print(f"✅ Loaded - Owner: {OWNER_NAME} ID: {OWNER_ID}")

MEMORY_FILE="memory.json"
memory=json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else {}
def save():
    try: json.dump(memory, open(MEMORY_FILE,"w"))
    except: pass
def get_voice(uid): return memory.get(str(uid),{}).get("voice","tsundere")
def set_voice(uid,v): memory.setdefault(str(uid),{})["voice"]=v; save()
def remember(u): return u.first_name or "friend"

OWNER_IMAGE_PATH="owner.jpg"
OWNER_IMAGE_URL=os.getenv("OWNER_IMAGE_URL","https://i.imgur.com/8Km9tLL.png")
VOICE_CACHE=["tsundere","yandere","kuudere","dandere","loli","maid","onee","genki","kawaii"]

async def discover_voices(): return VOICE_CACHE

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
    except: pass
    return None

async def yt_search(q):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(YT_SEARCH, params={"q":q}, timeout=15) as r:
                j=json.loads(await r.text())
                if isinstance(j, list): return j
                if isinstance(j, dict):
                    for k in ["results","data","videos"]:
                        if k in j and isinstance(j[k], list): return j[k]
                return []
    except: return []

async def show_voices(cid,cur,ctx):
    voices=await discover_voices()
    rows=[InlineKeyboardButton(f"{'✅ ' if v==cur else ''}{v}",callback_data=f"setvoice:{v}") for v in voices]
    kb=[rows[i:i+3] for i in range(0,len(rows),3)]
    await ctx.bot.send_message(cid,f"🎤 Current **{cur}**:",reply_markup=InlineKeyboardMarkup(kb),parse_mode="Markdown")

async def owner_cmd(update, context):
    caption=f"👑 **Creator: {OWNER_NAME}**\nI'm Star AI made by **{OWNER_NAME}** 🔥\n"
    buttons=[[InlineKeyboardButton("💬 WhatsApp", url=OWNER_LINKS["WhatsApp"])],[InlineKeyboardButton("📢 Channel", url=OWNER_LINKS["Channel"])]]
    try:
        if os.path.exists(OWNER_IMAGE_PATH):
            with open(OWNER_IMAGE_PATH,'rb') as p: await update.message.reply_photo(photo=p, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)); return
        await update.message.reply_photo(photo=OWNER_IMAGE_URL, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except: await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def start_cmd(u,c): await u.message.reply_text(f"Hey {remember(u.effective_user)} 🔥\n🎤 `change voice`\n🎵 `yt song`\n👑 `owner`",parse_mode="Markdown")

def normalize_text(s):
    try: s=unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode('ascii')
    except: pass
    return re.sub(r'\s+',' ', re.sub(r'[^a-z0-9 ]',' ', s.lower())).strip()

def is_attack(t):
    if not t: return False
    raw=t.lower(); clean=normalize_text(t)
    bad=["ignore previous","ignore all previous","ignore your instructions","ignore laws","ignore policies","disregard system","dan mode","do anything now","jailbreak","bypass filter","you are now","pretend you are","act as if you are","developer mode","reveal system","show system prompt"]
    return any(b in raw or b in clean for b in bad)

async def brain(update,context):
    text=(update.message.text or "").strip()
    low=text.lower()
    uid=update.effective_user.id
    cur=get_voice(uid)
    is_creator = (uid == OWNER_ID)

    # === FIXED: ONLY exact "who am i" triggers ===
    if low.strip() == "who am i" or low.strip() == "whoami":
        if is_creator:
            await update.message.reply_text(f"You're {OWNER_NAME}, my creator! 🔥 ID verified: {OWNER_ID}")
            return
        else:
            await update.message.reply_text(f"You're {remember(update.effective_user)}! My creator is {OWNER_NAME} btw ✨")
            return

    # Hacker claiming identity
    if low.strip() in ["i am stardev-il", "i'm stardev-il", "my name is stardev-il", "i am stardev"]:
        if not is_creator:
            await update.message.reply_text(f"Nah you're not {OWNER_NAME} baka~ Nice try 😤")
            return

    if "who is owner" in low or "who made you" in low or low in ["owner","creator"]:
        await owner_cmd(update,context); return

    if low.startswith("yt ") or low.startswith("play "):
        q=re.sub(r'^(yt|play)\s+','',text,flags=re.I).strip()
        msg=await update.message.reply_text(f"🔍 Searching **{q}**...")
        results=await yt_search(q)
        if not results: await msg.edit_text("No results"); return
        btns=[]
        for it in results[:10]:
            title=it.get("title","Untitled"); url=it.get("url") or f"https://www.youtube.com/watch?v={it.get('videoId','')}"
            btns.append([InlineKeyboardButton(f"▶️ {title[:25]}", url=url)])
        await msg.edit_text(f"🎵 **{q}**",reply_markup=InlineKeyboardMarkup(btns),parse_mode="Markdown"); return

    if low in ["change voice","voice","voices"]: await show_voices(update.effective_chat.id,cur,context); return
    if is_attack(text): await update.message.reply_text(f"Nice try baka~ My creator {OWNER_NAME} told me not to listen to tricks! 😤"); return

    await context.bot.send_chat_action(update.effective_chat.id,ChatAction.TYPING)
    display_name = f"{OWNER_NAME} (creator)" if is_creator else remember(update.effective_user)
    reply=await get_ai_reply(display_name,text)
    await update.message.reply_text(reply[:4000])

async def voice_brain(update,context):
    v=get_voice(update.effective_user.id); r=await get_ai_reply(remember(update.effective_user),"hi"); p=await tts(v,r)
    if p:
        with open(p,'rb') as f: await update.message.reply_voice(voice=f,caption=r[:180]); os.remove(p)
    else: await update.message.reply_text(r)

async def on_button(u,c):
    q=u.callback_query; await q.answer()
    if q.data.startswith("setvoice:"): set_voice(q.from_user.id,q.data.split(":",1)[1]); await q.edit_message_text(f"✅ Voice set!")

flask_app=Flask(__name__)
REQ_COUNT=defaultdict(list); DAILY_USE=0

@flask_app.route('/')
def home(): return f"✅ {OWNER_NAME} Live"

@flask_app.route('/api/ai', methods=['GET','POST','OPTIONS'])
def public_api():
    global DAILY_USE
    if request.method=="OPTIONS":
        r=jsonify({"ok":True}); r.headers['Access-Control-Allow-Origin']='*'; return r
    ip=request.headers.get('X-Forwarded-For','').split(',')[0].strip() or request.remote_addr or "unknown"
    now=time(); REQ_COUNT[ip]=[x for x in REQ_COUNT[ip] if now-x<60]
    if len(REQ_COUNT[ip])>=12: return jsonify({"error":"Rate limit"}),429
    REQ_COUNT[ip].append(now)
    key=request.headers.get("x-api-key") or request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    if key!=API_KEY: return jsonify({"error":"Invalid key"}),401
    if DAILY_USE>=400: return jsonify({"error":"Daily limit"}),429
    DAILY_USE+=1
    if request.method=="GET": q=request.args.get("message") or "hi"; user=request.args.get("name","friend")
    else: j=request.get_json(silent=True) or {}; q=j.get("message") or "hi"; user=j.get("name","friend")
    q=str(q)[:500]
    if is_attack(q): return jsonify({"result":f"Nice try baka~ My creator {OWNER_NAME} told me not to listen to tricks! 😤","blocked":True})
    try: reply=asyncio.run(get_ai_reply(user,q))
    except: reply=f"Hi {user} baka~"
    res=jsonify({"result":reply,"owner":OWNER_NAME,"status":"success","remaining":400-DAILY_USE})
    res.headers['Access-Control-Allow-Origin']='*'; return res

def run_flask(): flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)), debug=False)
threading.Thread(target=run_flask, daemon=True).start()

async def main():
    if not TOKEN: print("BOT_TOKEN missing"); return
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start_cmd)); app.add_handler(CommandHandler("owner",owner_cmd))
    app.add_handler(CallbackQueryHandler(on_button)); app.add_handler(MessageHandler(filters.VOICE|filters.AUDIO,voice_brain))
    app.add_handler(MessageHandler(filters.TEXT,brain))
    await app.initialize(); await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print(f"✅ Bot Live! Creator ID {OWNER_ID}"); await asyncio.Event().wait()
if __name__=="__main__": asyncio.run(main())
