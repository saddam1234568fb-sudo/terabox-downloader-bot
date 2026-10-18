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

# ================= Config & Database =================
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8868874895"))

import redis
db = redis.Redis.from_url(REDIS_URL, decode_responses=True)

bot = TelegramClient("bot_session", API_ID, API_HASH)
log = logging.getLogger(__name__)

# ================= ডামি ওয়েব সার্ভার (Render) =================
async def handle_ping(request):
    return web.Response(text="Universal Downloader Bot is Running Perfectly!")

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

# সুপার আনশর্টনার
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

async def check_force_sub(user_id):
    if user_id == ADMIN_ID: return True
    fs_chat_id = get_setting("fs_chat_id", "none")
    if fs_chat_id == "none" or not fs_chat_id.startswith("-"): return True
    try:
        participant = await bot.get_permissions(int(fs_chat_id), user_id)
        if participant.is_banned: return False
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
    
    text = (f"📤 **Uploading... / আপলোড হচ্ছে...**\n\n"
            f"[{bar}] **{percent:.1f}%**\n\n"
            f"📦 **Size:** `{curr_mb:.2f} MB / {total_mb:.2f} MB`\n"
            f"🚀 **Speed:** `{speed:.2f} MB/s`")
    try: await msg.edit(text)
    except: pass

# ================= START COMMAND =================
@bot.on(events.NewMessage(pattern="/start", incoming=True, func=lambda x: x.is_private))
async def start_cmd(m: Message):
    user_id = m.sender_id
    if db.get(f"banned_{user_id}"):
        return await m.reply("🚫 **You are banned from using this bot.**")
        
    if not await check_force_sub(user_id):
        fs_name = get_setting("fs_name", "Our Channel")
        fs_url = get_setting("fs_url", "https://t.me/")
        return await m.reply(
            f"⚠️ **Please join our channel first!**\nবটটি ব্যবহার করতে আগে আমাদের চ্যানেলে জয়েন করুন।",
            buttons=[
                [Button.url(f"📢 Join {fs_name}", url=fs_url)],
                [Button.url("🔄 Check Again", url=f"https://t.me/{bot.me.username}?start=start")]
            ]
        )

    await m.reply(
        "👋 **Welcome to Universal Downloader!**\n\n"
        "Send me any link from **YouTube, TikTok, Facebook, Instagram, Twitter** and I will download it for you.\n\n"
        "যেকোনো সোশ্যাল মিডিয়ার লিংক দিন, আমি ডাউনলোড করে দিব।",
        buttons=[
            [Button.inline("💎 VIP Premium", data="vip_menu")],
            [Button.inline("📊 My Status", data="my_status")]
        ]
    )

# ================= মেইন লিংক প্রসেসর =================
@bot.on(events.NewMessage(incoming=True, func=lambda m: m.is_private and m.text and not m.text.startswith("/")))
async def process_link(m: Message):
    user_id = m.sender_id
    if db.get(f"banned_{user_id}"): return
    
    if not await check_force_sub(user_id):
        fs_name = get_setting("fs_name", "Our Channel")
        fs_url = get_setting("fs_url", "https://t.me/")
        return await m.reply(f"⚠️ **Join Required!**\nবট ব্যবহার করতে আগে আমাদের চ্যানেলে জয়েন করুন।", buttons=[[Button.url(f"📢 Join {fs_name}", url=fs_url)]])

    is_vip = db.get(f"vip_{user_id}")
    daily_limit = get_setting("daily_limit", "5")
    if not is_vip and daily_limit != "0" and user_id != ADMIN_ID:
        today = time.strftime("%Y-%m-%d")
        usage_key = f"usage_{user_id}_{today}"
        if int(db.get(usage_key) or 0) >= int(daily_limit):
            return await m.reply("⚠️ **Daily Limit Reached!**\n\nআপনার আজকের ফ্রি লিমিট শেষ। আনলিমিটেড ডাউনলোডের জন্য ভিআইপি কিনুন।", buttons=[[Button.inline("💎 Buy VIP", data="vip_menu")]])
        db.incr(usage_key)
        db.expire(usage_key, 86400)

    url = extract_url(m.text)
    if not url: return

    hm = await m.reply("🔍 **Scanning Video Details... / তথ্য খোঁজা হচ্ছে...**")
    real_url = get_real_url(url)

    try:
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True, 
            'nocheckcertificate': True,
            'force_ipv4': True, 
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}, 'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}}
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(real_url, download=False)
            
        title = info.get('title', 'Unknown Video')
        duration = info.get('duration_string', 'Unknown')
        uploader = info.get('uploader', 'Unknown Owner')
        thumb = info.get('thumbnail', '')
        
        db.set(f"vidurl_{m.id}", real_url, ex=3600)
        
        caption = (f"🎬 **Title:** `{title[:60]}...`\n"
                   f"👤 **Owner:** `{uploader}`\n"
                   f"⏱ **Duration:** `{duration}`\n\n"
                   f"👇 **Select Download Quality / কোয়ালিটি বেছে নিন:**")
        
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
        await hm.edit(f"❌ **Failed!**\nভিডিওটি পাওয়া যায়নি। লিংকটি হয়তো প্রাইভেট বা ভুল।\n`{str(e)[:50]}`")

# ================= বাটনে ক্লিক করলে ডাউনলোড শুরু =================
@bot.on(events.CallbackQuery(pattern=b"dl_"))
async def download_handler(e):
    data = e.data.decode().split("_")
    msg_id = data[1]
    quality = data[2]
    
    url = db.get(f"vidurl_{msg_id}")
    if not url: return await e.answer("⚠️ Link Expired! Please send the link again.", alert=True)
    
    await e.answer("Downloading... Please wait!", alert=False)
    hm = await e.reply("⏳ **Downloading to Server... / সার্ভারে ডাউনলোড হচ্ছে...**")
    
    if not os.path.exists("downloads"): os.makedirs("downloads")
    
    try:
        file_path = ""
        base_opts = {
            'outtmpl': f'downloads/{e.sender_id}_%(id)s.%(ext)s',
            'quiet': True, 'nocheckcertificate': True, 'force_ipv4': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}, 'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}}
        }
        
        if quality == "audio":
            base_opts['format'] = 'bestaudio/best'
            base_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        elif quality == "thumb":
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                thumb_url = info.get('thumbnail')
            if thumb_url:
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
            caption=f"✅ **{title}**\n\n📥 Downloaded via Premium Bot",
            reply_to=e.message_id,
            progress_callback=lambda curr, tot: bot.loop.create_task(progress_bar(curr, tot, hm, start_time, hm.id))
        )
        await hm.delete()
        if os.path.exists(file_path): os.remove(file_path)

    except Exception as ex:
        await hm.edit(f"❌ **Download Failed!**\nভিডিওটি ডাউনলোড করা সম্ভব হয়নি। Error: `{str(ex)[:40]}`")
        if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)

# ================= ADMIN SYSTEM =================
@bot.on(events.NewMessage(pattern=r"/ban (\d+)", from_users=[ADMIN_ID]))
async def ban_user(m):
    target = m.pattern_match.group(1)
    db.set(f"banned_{target}", "1")
    await m.reply(f"🚫 **User `{target}` BANNED.**")

@bot.on(events.NewMessage(pattern=r"/unban (\d+)", from_users=[ADMIN_ID]))
async def unban_user(m):
    target = m.pattern_match.group(1)
    db.delete(f"banned_{target}")
    await m.reply(f"✅ **User `{target}` UNBANNED.**")

@bot.on(events.NewMessage(pattern="/admin", from_users=[ADMIN_ID]))
async def admin_panel(m):
    limit = get_setting("daily_limit", "5")
    limit_txt = "Unlimited" if limit == "0" else f"{limit} / day"
    
    text = (f"👑 **Ultimate Admin Panel**\n\n📊 **Daily Limit:** {limit_txt}\n\nCommands:\n`/ban userid` - ব্লক করুন\n`/unban userid` - আনব্লক করুন\n")
    buttons = [
        [Button.inline("📢 Setup Force Sub", data="admin_fs_setup")],
        [Button.inline("⚙️ Set Daily Limit", data="admin_limit")],
    ]
    await m.reply(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern="admin_limit", func=lambda e: e.sender_id == ADMIN_ID))
async def admin_limit_setup(e):
    db.set(f"adminstate_{e.sender_id}", "daily_limit")
    await e.reply("⚙️ **Set Daily Limit:**\nলিমিট বন্ধ করতে `0` লিখে পাঠান।")

@bot.on(events.CallbackQuery(pattern="admin_fs_setup", func=lambda e: e.sender_id == ADMIN_ID))
async def admin_fs_setup(e):
    db.set(f"adminstate_{e.sender_id}", "fs_name")
    await e.reply("📢 **Force Sub Setup (Step 1/3):**\nপ্রথমে চ্যানেল/গ্রুপের **নাম** লিখুন। বন্ধ করতে `none` লিখুন।")

@bot.on(events.NewMessage(incoming=True, from_users=[ADMIN_ID]))
async def admin_state_handler(m: Message):
    state = db.get(f"adminstate_{m.sender_id}")
    if not state: return
    if m.text == "/cancel":
        db.delete(f"adminstate_{m.sender_id}")
        return await m.reply("❌ Cancelled.")

    if state == "fs_name":
        if m.text.lower() == "none":
            db.set("settings_fs_chat_id", "none")
            db.delete(f"adminstate_{m.sender_id}")
            return await m.reply("✅ Force Subscribe Turned OFF.")
        db.set("settings_fs_name", m.text)
        db.set(f"adminstate_{m.sender_id}", "fs_url")
        await m.reply("🔗 **Step 2/3:**\nএবার চ্যানেলের **Link (URL)** দিন:")
    elif state == "fs_url":
        db.set("settings_fs_url", m.text)
        db.set(f"adminstate_{m.sender_id}", "fs_chat_id")
        await m.reply("🆔 **Step 3/3:**\nসবশেষে চ্যানেলের **Chat ID** দিন (যেমন: -100123456789):")
    elif state == "fs_chat_id":
        db.set("settings_fs_chat_id", m.text)
        db.delete(f"adminstate_{m.sender_id}")
        await m.reply("✅ **Force Subscribe Successfully Set!**")
    else:
        db.set(f"settings_{state}", m.text)
        db.delete(f"adminstate_{m.sender_id}")
        await m.reply(f"✅ Successfully updated **{state}** to: {m.text}")

# ================= SERVER START =================
bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
