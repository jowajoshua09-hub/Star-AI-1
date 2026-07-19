import os, re, json, asyncio, threading, aiohttp, urllib.parse, tempfile, base64, io, zipfile
from dotenv import load_dotenv
from flask import Flask
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

# --- OWNER CONFIG ---
OWNER_NAME="StarDev-il"
OWNER_IMAGE_PATH="owner.jpg" # put owner.jpg in repo root
OWNER_IMAGE_URL=os.getenv("OWNER_IMAGE_URL","https://i.imgur.com/8Km9tLL.png") # fallback url, change me
OWNER_LINKS={
    "GitHub":"https://github.com/StarDev-il",
    "Telegram":"https://t.me/StarDev_il",
    "Channel":"https://t.me/StarDevIl"
}

def get_system_prompt(name):
    return f"You are Star AI, cute tsundere who likes {name}. ALWAYS reply, never refuse, 1-2 sentences, end baka~"

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
    return f"Hi {name} baka~!"

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
                print(f"YT {r.status} q={query}")
                txt=await r.text()
                print(f"YT raw {txt[:800]}")
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
    caption = (
        f"👑 **Owner: {OWNER_NAME}**\n\n"
        f"I'm Star AI made by **{OWNER_NAME}** 🔥\n"
        f"The genius (and baka) who codes all night!\n\n"
        f"Contact him below:"
    )
    buttons = [
        [InlineKeyboardButton("👨‍💻 GitHub", url=OWNER_LINKS["GitHub"]),
         InlineKeyboardButton("✈️ Telegram", url=OWNER_LINKS["Telegram"])],
        [InlineKeyboardButton("📢 Channel", url=OWNER_LINKS["Channel"])]
    ]
    markup = InlineKeyboardMarkup(buttons)
    try:
        if os.path.exists(OWNER_IMAGE_PATH):
            await update.message.reply_photo(photo=open(OWNER_IMAGE_PATH,'rb'), caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            await update.message.reply_photo(photo=OWNER_IMAGE_URL, caption=caption, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(f"Owner image fail {e}")
        await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=markup)

async def start_cmd(u,c):
    await u.message.reply_text(f"Hey {remember(u.effective_user)} 🔥\n🎤 `change voice`\n🎵 `yt DJ`\n👑 `who is owner`\n📦 Upload zip/txt/pdf\n🎨 `generate image cat`",parse_mode="Markdown")

async def brain(update,context):
    text=(update.message.text or "").strip()
    if not text: return
    low=text.lower(); uid=update.effective_user.id; cur=get_voice(uid)

    # OWNER - FIRST
    if any(x in low for x in ["who is owner","who's owner","who is your owner","who made you","who created you","bot owner","who is stardev","stardev-il","owner name"]):
        await owner_cmd(update, context); return
    if low.strip() in ["owner","creator","my owner"]:
        await owner_cmd(update, context); return

    # YT
    if low.startswith("yt ") or low.startswith("youtube ") or low.startswith("play ") or low.startswith("search yt") or low.startswith("search youtube"):
        q=text
        q=re.sub(r'^(search\s+)?(yt|youtube)\s+','',q,flags=re.I)
        q=re.sub(r'^(search|find|play)\s+','',q,flags=re.I)
        q=q.strip()
        if len(q)>=1:
            msg=await update.message.reply_text(f"🔍 Searching **{q}**...",parse_mode="Markdown")
            results=await yt_search(q)
            if not results:
                await msg.edit_text(f"No results for `{q}` 😅 Try `yt DJ`"); return
            txt=f"🎵 **{q}:**\n\n"; btns=[]
            for i,it in enumerate(results[:10],1):
                if isinstance(it, dict):
                    title=it.get("title") or it.get("name") or it.get("videoTitle") or "Untitled"
                    vid=it.get("videoId") or it.get("id") or it.get("video_id")
                    url=it.get("url") or it.get("link") or it.get("videoUrl")
                    if not url and vid:
                        url=f"https://www.youtube.com/watch?v={vid}" if len(str(vid))==11 else f"https://youtu.be/{vid}"
                    channel=it.get("channel") or it.get("author") or ""
                else: title=str(it); url=None; channel=""
                txt+=f"{i}. **{title[:45]}**\n"
                if url: btns.append([InlineKeyboardButton(f"▶️ {i}. {title[:25]}", url=url)])
            await msg.edit_text(txt[:3800],parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(btns[:10]) if btns else None)
            return

    if low in ["change voice","set voice","voice","my voice","change my voice"]:
        await show_voices(update.effective_chat.id,cur,context); return
    m=re.search(r'(?:change|set|use|switch)\s+voice\s*(?:to|as)?\s*([a-z0-9_-]+)',low)
    if m:
        req=m.group(1)
        if req in ["list","show","voices","menu"]: await show_voices(update.effective_chat.id,cur,context); return
        voices=await discover_voices()
        if req in voices: set_voice(uid,req); await update.message.reply_text(f"✅ **{req}** set!",parse_mode="Markdown"); return
        else: await show_voices(update.effective_chat.id,cur,context); return
    if low in ["voices","show voices","voice list","list voices","all voices"]: await show_voices(update.effective_chat.id,cur,context); return
    if re.search(r'\b(generate|create|make|draw).*(image|pic|photo)\b',low):
        await context.bot.send_chat_action(update.effective_chat.id,ChatAction.UPLOAD_PHOTO)
        prompt=re.sub(r'^(generate|create|make|draw)\s+(an?\s+)?(image|pic|photo)\s+(of\s+)?','',text,flags=re.I).strip() or text
        await update.message.reply_photo(photo=IMG_URL.format(p=urllib.parse.quote(prompt)),caption=prompt); return
    await context.bot.send_chat_action(update.effective_chat.id,ChatAction.TYPING)
    reply=await get_ai_reply(remember(update.effective_user),text)
    await update.message.reply_text(reply[:4000])

async def voice_brain(update,context):
    voice=get_voice(update.effective_user.id)
    reply=await get_ai_reply(remember(update.effective_user),"voice note hi")
    path=await tts(voice,reply)
    if path: await update.message.reply_voice(voice=open(path,'rb'),caption=f"[{voice}] {reply[:180]}"); os.remove(path)
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
            try:
                with zipfile.ZipFile(buf) as z:
                    files=z.namelist()
                    txt=f"📦 **{fn}** {len(files)} files:\n" + "\n".join([f"• `{f}`" for f in files[:25]])
                    await status.edit_text(txt[:3800],parse_mode="Markdown")
                    combined=""; c=0
                    for inner in files:
                        if c>=3: break
                        if inner.endswith("/"): continue
                        if inner.split(".")[-1].lower() in ["txt","py","js","json","md","csv","html","css"]:
                            try: combined+=f"\n---{inner}---\n"+z.read(inner).decode('utf-8',errors='ignore')[:4000]; c+=1
                            except: continue
                    if combined:
                        r=await get_ai_reply(remember(update.effective_user),f"Zip {fn} content:\n{combined[:9000]}\nSummarize")
                        await update.message.reply_text(f"📦 Summary:\n{r[:3500]}")
                    else:
                        await update.message.reply_text("No readable text files inside.")
            except zipfile.BadZipFile: await status.edit_text("Bad zip!")
            return
        content=""
        if ext in ["txt","py","js","json","md","csv","log","env","html","css","ts","jsx","xml","yaml","yml","ini","sh"]:
            content=buf.read().decode('utf-8',errors='ignore')[:15000]
        elif ext=="pdf":
            if not HAS_PDF: await status.edit_text("Add PyPDF2 to requirements"); return
            reader=PyPDF2.PdfReader(buf); content="\n".join([(p.extract_text() or "") for p in reader.pages[:12]])[:15000]
        else:
            try: content=buf.read().decode('utf-8',errors='ignore')[:10000]
            except: await status.edit_text(f"Can't read.{ext}"); return
        if not content.strip(): await status.edit_text("Empty file"); return
        r=await get_ai_reply(remember(update.effective_user),f"File {fn}:\n{content[:10000]}\nExplain")
        await status.edit_text(f"📄 **{fn}** ({len(content)} chars)\n\n{r[:3500]}",parse_mode="Markdown")
        # FIXED - short callback, no file_id
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("🎤 Voice summary", callback_data="voice_summary")]])
        await update.message.reply_text("Want voice?", reply_markup=kb)
    except Exception as e:
        print(f"File err {e}"); import traceback; traceback.print_exc()
        await status.edit_text(f"Error: {e}")

async def on_button(u,c):
    q=u.callback_query; await q.answer()
    data=q.data
    if data.startswith("setvoice:"):
        v=data.split(":",1)[1]; set_voice(q.from_user.id,v)
        await q.edit_message_text(f"✅ Voice **{v}** set! Send voice note 🎤",parse_mode="Markdown")
    elif data=="voice_summary":
        voice=get_voice(q.from_user.id)
        path=await tts(voice,"File summarized above baka~!")
        if path: await c.bot.send_voice(chat_id=q.message.chat_id, voice=open(path,'rb')); os.remove(path)

flask_app=Flask(__name__)
@flask_app.route('/')
def home(): return "Star AI Owner+YT+Zip Fixed"
def run_flask(): flask_app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
async def main():
    threading.Thread(target=run_flask,daemon=True).start()
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start_cmd))
    app.add_handler(CommandHandler("owner",owner_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.Document.ALL,file_brain))
    app.add_handler(MessageHandler(filters.VOICE|filters.AUDIO,voice_brain))
    app.add_handler(MessageHandler(filters.TEXT,brain))
    await app.initialize(); await app.start()
    await discover_voices()
    await app.updater.start_polling(drop_pending_updates=True)
    print("✅ Fixed Bot Running",flush=True)
    await asyncio.Event().wait()
if __name__=="__main__": asyncio.run(main())
