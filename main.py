import asyncio
import logging
import time
import os
import re
import requests
from aiohttp import web
import yt_dlp
from telethon import Button
from telethon.sync import TelegramClient, events
from telethon.tl.custom.message import Message
from telethon.errors.rpcerrorlist import UserNotParticipantError

# Config - 환경 변수 থেকে ডাটা নেওয়া
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Redis Setup
import redis
db = redis.Redis.from_url(REDIS_URL, decode_responses=True)

ADMIN_ID = int(os.environ.get("ADMIN_ID", "8868874895"))

bot = TelegramClient("bot_session", API_ID, API_HASH)
log = logging.getLogger(__name__)

# ================= ডামি ওয়েব সার্ভার (Render) =================
async def handle_ping(request):
    return web.Response(text="Ultimate Social Media Downloader Bot is Running!")

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', handle_ping)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

loop = bot.loop
loop.create_task(start_web_server())

# ================= টুলস ও ফাংশন =================
def extract_url(text):
    url_pattern = re.compile(r'(https?://[^\s]+)')
    match = url_pattern.search(text)
    return match.group(1) if match else None

# সুপার আনশর্টনার (Facebook ও অন্যান্য লিংকের জন্য)
def get_real_url(url):
    try:
        if "facebook.com/share" in url or "fb.watch" in url:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            return response.url
        return url
    except Exception:
        return url

def get_setting(key, default):
    val = db.get(f"settings_{key}")
    return val if val else default

# Force Join চেকার
async def check_force_sub(user_id):
    if user_id == ADMIN_ID: return True
    fs_chat_id = get_setting("fs_chat_id", "none")
    
    if fs_chat_id == "none" or not fs_chat_id.startswith("-"):
        return True
        
    try:
        participant = await bot.get_permissions(int(fs_chat_id), user_id)
        if participant.is_banned:
            return False
        return True
    except Exception:
        return False

# প্রগ্রেস বার
last_update_time = {}
async def progress_bar(current, total, msg, start_time, msg_id):
    global last_update_time
    now = time.time()
    
    if msg_id in last_update_time and (now - last_update_time[msg_id]) < 2.5 and current < total:
        return
    last_update_time[msg_id] = now
    
    percent = (current / total) * 100 if total > 0 else 0
    filled = int(percent / 10)
    bar = '▰' * filled + '▱' * (10 - filled)
    
    curr_mb = current / (1024 * 1024)
    total_mb = total / (1024 * 1024)
    elapsed = now - start_time
    speed = curr_mb / elapsed if elapsed > 0 else 0
    
    text = (
        f"📤 **Uploading... / আপলোড হচ্ছে...**\n\n"
        f"[{bar}] **{percent:.1f}%**\n\n"
        f"📦 **Size:** `{curr_mb:.2f} MB / {total_mb:.2f} MB`\n"
        f"🚀 **Speed:** `{speed:.2f} MB/s`"
    )
    try: await msg.edit(text)
    except: pass

# ================= মেইন লিংক প্রসেসর (UI & MetaData) =================
@bot.on(events.NewMessage(incoming=True, func=lambda m: m.is_private and m.text and not m.text.startswith("/")))
async def process_link(m: Message):
    user_id = m.sender_id
    if db.get(f"banned_{user_id}"): return
    
    if not await check_force_sub(user_id):
        fs_name = get_setting("fs_name", "Our Channel")
        fs_url = get_setting("fs_url", "https://t.me/")
        return await m.reply(
            f"⚠️ **Join Required!**\nবট ব্যবহার করতে আগে আমাদের চ্যানেলে জয়েন করুন।",
            buttons=[[Button.url(f"📢 Join {fs_name}", url=fs_url)]]
        )

    is_vip = db.get(f"vip_{user_id}")
    daily_limit = get_setting("daily_limit", "5") 
    
    if not is_vip and daily_limit != "0" and user_id != ADMIN_ID:
        today = time.strftime("%Y-%m-%d")
        usage_key = f"usage_{user_id}_{today}"
        if int(db.get(usage_key) or 0) >= int(daily_limit):
            return await m.reply("⚠️ **Daily Limit Reached!**\n\nআপনার আজকের ফ্রি লিমিট শেষ। আনলিমিটেড ডাউনলোডের জন্য ভিআইপি কিনুন।", buttons=[[Button.inline("💎 Buy VIP", data="vip_menu")]])
        db.incr(usage_key)
        db.expire(usage_key, 86400)

    raw_url = extract_url(m.text)
    if not raw_url: return

    hm = await m.reply("🔍 **Scanning Video Details... / তথ্য খোঁজা হচ্ছে...**")
    url = get_real_url(raw_url)

    # Anti-Bot Bypass Options
    ydl_opts = {
        'quiet': True, 
        'no_warnings': True, 
        'nocheckcertificate': True,
        'force_ipv4': True, 
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        'extractor_args': {
            'youtube': {'player_client': ['android', 'web']},
            'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        title = info.get('title', 'Unknown Video')
        duration = info.get('duration_string', 'Unknown')
        uploader = info.get('uploader', 'Unknown Owner')
        thumb = info.get('thumbnail', '')
        
        db.set(f"vidurl_{m.id}", url, ex=3600)
        
        caption = (
            f"🎬 **Title:** `{title[:60]}...`\n"
            f"👤 **Owner:** `{uploader}`\n"
            f"⏱ **Duration:** `{duration}`\n\n"
            f"👇 **Select Download Quality / কোয়ালিটি বেছে নিন:**"
        )
        
        buttons = [
            [Button.inline("🎥 360p", data=f"dl_{m.id}_360"), Button.inline("🎥 720p (HD)", data=f"dl_{m.id}_720")],
            [Button.inline("🌟 1080p (FHD)", data=f"dl_{m.id}_1080"), Button.inline("🔥 4K / Max", data=f"dl_{m.id}_max")],
            [Button.inline("🎧 Audio (MP3)", data=f"dl_{m.id}_audio"), Button.inline("🖼 Photo/Thumb", data=f"dl_{m.id}_thumb")]
        ]
        
        await hm.delete()
        if thumb:
            await bot.send_file(m.chat_id, file=thumb, caption=caption, buttons=buttons, reply_to=m.id)
        else:
            await m.reply(caption, buttons=buttons)

    except Exception as e:
        await hm.edit(f"❌ **Failed!**\nভিডিওটি পাওয়া যায়নি। লিংকটি হয়তো প্রাইভেট বা ভুল।\nError: `{str(e)[:50]}`")

# ================= বাটনে ক্লিক করলে ডাউনলোড শুরু =================
@bot.on(events.CallbackQuery(pattern=b"dl_"))
async def download_handler(e):
    data = e.data.decode().split("_")
    msg_id = data[1]
    quality = data[2]
    
    url = db.get(f"vidurl_{msg_id}")
    if not url:
        return await e.answer("⚠️ Link Expired! Please send the link again.", alert=True)
    
    await e.answer("Downloading... Please wait!", alert=False)
    hm = await e.reply("⏳ **Downloading to Server... / সার্ভারে ডাউনলোড হচ্ছে...**")
    
    if not os.path.exists("downloads"): os.makedirs("downloads")
    
    # Download Engine setup with Anti-Bot Bypass
    base_opts = {
        'outtmpl': f'downloads/{e.sender_id}_%(id)s.%(ext)s',
        'quiet': True, 
        'nocheckcertificate': True, 
        'force_ipv4': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        'extractor_args': {
            'youtube': {'player_client': ['android', 'web']},
            'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}
        }
    }
    
    try:
        file_path = ""
        if quality == "audio":
            base_opts['format'] = 'bestaudio/best'
            base_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        elif quality == "thumb":
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                thumb_url = info.get('thumbnail')
            await bot.send_file(e.chat_id, file=thumb_url, caption="🖼 **Thumbnail Downloaded**")
            return await hm.delete()
        elif quality == "max":
            base_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        else:
            base_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'

        with yt_dlp.YoutubeDL(base_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if quality == "audio": file_path = file_path.rsplit('.', 1)[0] + '.mp3'
            title = info.get('title', 'Video')

        start_time = time.time()
        await bot.send_file(
            e.chat_id,
            file=file_path,
            caption=f"✅ **{title}**\n\n📥 Downloaded via VIP Bot",
            reply_to=e.message_id,
            progress_callback=lambda curr, tot: bot.loop.create_task(progress_bar(curr, tot, hm, start_time, hm.id))
        )
        
        await hm.delete()
        if os.path.exists(file_path): os.remove(file_path)

    except Exception as ex:
        await hm.edit(f"❌ **Download Failed!**\nহয়তো এই কোয়ালিটিটি ভিডিওটিতে নেই। অন্য কোয়ালিটি ট্রাই করুন।")
        if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)


# (বাকি অ্যাডমিন প্যানেল ও স্টার্ট কমান্ডের কোডগুলো আগের মতোই থাকবে, ফাইলের নিচে যুক্ত করে নিবেন...)
