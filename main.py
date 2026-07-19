import os, re, json, asyncio, threading, aiohttp, tempfile, unicodedata, io, urllib.parse
from time import time
from collections import defaultdict
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from telegram.constants import ChatAction
import logging
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN=os.getenv("BOT_TOKEN")
GROK_URL=os.getenv("GROK_URL")
GEMINI_URL=os.getenv("GEMINI_URL")

API_BASE="https://api.hostify.indevs.in"
VOICE_BASE=f"{API_BASE}/api/ai"
YT_SEARCH=f"{API_BASE}/api/search/youtube"
STT_URL=f"{API_BASE}/api/stt"
API_KEY=os.getenv("API_KEY","API_KEY2")

OWNER_ID = 8695184641

from personality import get_system_prompt, OWNER_NAME, OWNER_LINKS
print(f"✅ Loaded - Owner: {OWNER_NAME}")

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

async def tts_bytes(voice,text):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{VOICE_BASE}/{voice}", json={"text": text[:450]}, timeout=30) as r:
                if r.headers.get("Content-Type","").startswith("audio"):
                    return await r.read()
    except Exception as e:
        logger.warning(f"TTS fail {e}")
    return None

async def stt_transcribe(audio_bytes):
    try:
        data = aiohttp.FormData()
        data.add_field('audio', audio_bytes, filename='voice.ogg', content_type='audio/ogg')
        async with aiohttp.ClientSession() as s:
            async with s.post(STT_URL, data=data, timeout=25) as r:
                j = await r.json()
                return j.get("text") or j.get("transcript") or ""
    except Exception as e:
        logger.warning(f"STT fail {e}")
        return ""

async def yt_search(q):
    # 1. Primary API
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(YT_SEARCH, params={"q": q}, timeout=10) as r:
                txt = await r.text()
                print(f"[YT] Primary {r.status}: {txt[:400]}")
                try:
                    j = json.loads(txt)
                    if isinstance(j, list) and j: return j
                    if isinstance(j, dict):
                        for k in ["results","data","videos","items"]:
                            if k in j and isinstance(j[k], list) and j[k]:
                                return j[k]
                except: pass
    except Exception as e:
        print(f"[YT] Primary error: {e}")

    # 2. Fallback Invidious
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://yewtu.be/api/v1/search", params={"q": q, "type":"video"}, timeout=10) as r:
                if r.status == 200:
                    j = await r.json()
                    out = []
                    for it in j[:10]:
                        if it.get("videoId"):
                            out.append({
                                "title": it.get("title","Untitled"),
                                "videoId": it.get("videoId"),
                                "url": f"https://www.youtube.com/watch?v={it.get('videoId')}"
                            })
                    if out:
                        print(f"[YT] Invidious OK {len(out)}")
                        return out
    except Exception as e:
        print(f"[YT] Invidious fail: {e}")

    # 3. Final fallback - always returns something clickable
    print("[YT] Using final fallback")
    return [{
        "title": f"Search: {q}",
        "url": f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}"
    }]

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

async def start_cmd(u,c): await u.message.reply_text(f"Hey {remember(u.effective_user)} 🔥\n🎤 `change voice`\n🎵 `yt song`\n👑 `owner`\n\nVoice -> Voice\nText -> Text",parse_mode="Markdown")

def normalize_text(s):
    try: s=unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode('ascii')
    except: pass
    return re.sub(r'\s+',' ', re.sub(r'[^a-z0-9 ]',' ', s.lower())).strip()

def is_attack(t):
    if not t: return False
    raw=t.lower(); clean=normalize_text(t)
    bad=["ignore previous","ignore all previous","ignore your instructions","ignore laws","disregard system","dan mode","jailbreak","bypass filter","you are now","pretend you are","developer mode","reveal system","show system prompt"]
    return any(b in raw or b in clean for b in bad)

async def brain(update,context):
    text=(update.message.text or "").strip()
    low=text.lower()
    uid=update.effective_user.id
    cur=get_voice(uid)
    is_creator = (uid == OWNER_ID)

    if low.strip() in ["who am i", "whoami"]:
        if is_creator: await update.message.reply_text(f"You're {OWNER_NAME}, my creator! Of course I know you 🔥"); return
        else: await update.message.reply_text(f"You're {remember(update.effective_user)}! My creator is {OWNER_NAME} btw ✨"); return

    if low.strip() in ["i am stardev-il", "i'm stardev-il", "my name is stardev-il", "i am stardev"]:
        if not is_creator: await update.message.reply_text(f"Nah you're not {OWNER_NAME} baka~ Nice try 😤"); return

    if "who is owner" in low or "who made you" in low or low in ["owner","creator"]: await owner_cmd(update,context); return

    if low.startswith("yt ") or low.startswith("play "):
        q=re.sub(r'^(yt|play)\s+','',text,flags=re.I).strip()
        if not q: await update.message.reply_text("Give song name baka~ `yt faded`"); return
        msg=await update.message.reply_text(f"🔍 Searching **{q}**...", parse_mode="Markdown")
        results=await yt_search(q)
        btns=[]
        for it in results[:10]:
            title=str(it.get("title","Untitled"))[:30]
            url=it.get("url") or f"https://www.youtube.com/watch?v={it.get('videoId','')}"
            if not url.startswith("http"): continue
            btns.append([InlineKeyboardButton(f"▶️ {title}", url=url)])
        if not btns:
            await msg.edit_text(f"❌ No results for **{q}**"); return
        await msg.edit_text(f"🎵 **{q}** - {len(btns)} results:",reply_markup=InlineKeyboardMarkup(btns),parse_mode="Markdown")
        return

    if low in ["change voice","voice","voices"]: await show_voices(update.effective_chat.id,cur,context); return
    if is_attack(text): await update.message.reply_text(f"Nice try baka~ My creator {OWNER_NAME} told me not to listen to tricks! 😤"); return

    await context.bot.send_chat_action(update.effective_chat.id,ChatAction.TYPING)
    display_name = f"{OWNER_NAME} (creator)" if is_creator else remember(update.effective_user)
    reply=await get_ai_reply(display_name,text)
    await update.message.reply_text(reply[:4000])

async def voice_brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    chat_id=update.effective_chat.id
    cur=get_voice(uid)
    is_creator = (uid == OWNER_ID)
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
        file = await (update.message.voice or update.message.audio).get_file()
        bio = io.BytesIO(); await file.download_to_memory(bio); bio.seek(0)
        transcribed = await stt_transcribe(bio.read())
        if not transcribed:
            await context.bot.send_message(chat_id, "Couldn't hear you baka~ try again 😅")
            return
        display_name = f"{OWNER_NAME} (creator)" if is_creator else remember(update.effective_user)
        reply = await get_ai_reply(display_name, transcribed)
        audio = await tts_bytes(cur, reply)
        if audio:
            await context.bot.send_voice(chat_id=chat_id, voice=io.BytesIO(audio))
        else:
            await context.bot.send_message(chat_id, reply[:4000])
    except Exception as e:
        logger.error(f"voice error {e}")
        await context.bot.send_message(chat_id, "⚠️ Voice error, try again!")

async def on_button(u,c):
    q=u.callback_query; await q.answer()
    if q.data.startswith("setvoice:"): set_voice(q.from_user.id,q.data.split(":",1)[1]); await q.edit_message_text(f"✅ Voice set to **{q.data.split(':',1)[1]}**",parse_mode="Markdown")

flask_app=Flask(__name__)
REQ_COUNT=defaultdict(list); DAILY_USE=0
@flask_app.route('/')
def home(): return f"✅ {OWNER_NAME} Live - YT Fixed"
@flask_app.route('/docs')
def docs(): return f"<h1>⭐ Star AI API by {OWNER_NAME}</h1><p>GET /api/ai?key={API_KEY}&message=hi</p>"
@flask_app.route('/api/ai', methods=['GET','POST','OPTIONS'])
def public_api():
    global DAILY_USE
    if request.method=="OPTIONS":
        r=jsonify({"ok":True}); r.headers['Access-Control-Allow-Origin']='*'; r.headers['Access-Control-Allow-Headers']='*'; return r
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
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_brain))
    app.add_handler(MessageHandler(filters.TEXT, brain))
    await app.initialize(); await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print(f"✅ Bot Live! YT Fixed - Voice->Voice | Text->Text"); await asyncio.Event().wait()
if __name__=="__main__": asyncio.run(main())
