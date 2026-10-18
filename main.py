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

# Config
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8868874895"))

import redis
db = redis.Redis.from_url(REDIS_URL, decode_responses=True)

bot = TelegramClient("bot_session", API_ID, API_HASH)
log = logging.getLogger(__name__)

# ================= ডামি ওয়েব সার্ভার =================
async def handle_ping(request):
    return web.Response(text="Ultimate Downloader Bot is Running!")

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

# সুপার আনশর্টনার (Facebook Share ও TikTok লিংকের সমাধান)
def get_real_url(url):
    try:
        # Instagram এর লগিন পেজ এড়াতে এটি স্কিপ
        if "instagram.com" in url:
            return url
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        final_url = response.url
        
        if "login" in final_url.lower() and "facebook.com" not in url.lower():
            return url
        return final_url
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
    if msg_id in last_update_time and (now - last_update_time[msg_id]) < 2.5 and current < total: return
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

# ================= মেইন লিংক প্রসেসর =================
@bot.on(events.NewMessage(incoming=True, func=lambda m: m.is_private and m.text and not m.text.startswith("/")))
async def process_link(m: Message):
    user_id = m.sender_id
    if db.get(f"banned_{user_id}"): return
    
    if not await check_force_sub(user_id):
        fs_name = get_setting("fs_name", "Our Channel")
        fs_url = get_setting("fs_url", "https://t.me/")
        return await m.reply(f"⚠️ **Join Required!**", buttons=[[Button.url(f"📢 Join {fs_name}", url=fs_url)]])

    url = extract_url(m.text)
    if not url: return

    hm = await m.reply("🔍 **Scanning Video Details... / তথ্য খোঁজা হচ্ছে...**")
    
    # আসল লিংক বের করা (Facebook share/TikTok vt সমাধান)
    real_url = get_real_url(url)

    try:
        # TikTok এর জন্য স্পেশাল ডাইরেক্ট API (No yt-dlp)
        if "tiktok.com" in real_url.lower():
            api_req = requests.get(f"https://www.tikwm.com/api/?url={real_url}", timeout=15).json()
            if api_req.get("code") == 0:
                data = api_req["data"]
                title = data.get("title", "TikTok Video")
                uploader = data.get("author", {}).get("nickname", "Unknown")
                duration = str(data.get("duration", 0)) + " Sec"
                thumb = data.get("cover")
                
                db.set(f"direct_vid_{m.id}", data.get("play"), ex=3600)
                db.set(f"direct_aud_{m.id}", data.get("music"), ex=3600)
                db.set(f"direct_thumb_{m.id}", thumb, ex=3600)
            else:
                return await hm.edit("❌ **Failed!** টিকটক ভিডিওটি পাওয়া যায়নি।")

        else:
            # YouTube, FB, IG এর জন্য yt-dlp
            ydl_opts = {
                'quiet': True, 'no_warnings': True, 'nocheckcertificate': True,
                'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(real_url, download=False)
            
            title = info.get('title', 'Unknown Video')
            duration = info.get('duration_string', 'Unknown')
            uploader = info.get('uploader', 'Unknown Owner')
            thumb = info.get('thumbnail', '')
            db.set(f"vidurl_{m.id}", real_url, ex=3600)

        # UI ব্যানার
        caption = (f"🎬 **Title:** `{title[:60]}...`\n"
                   f"👤 **Owner:** `{uploader}`\n"
                   f"⏱ **Duration:** `{duration}`\n\n"
                   f"👇 **Select Download Quality:**")
        
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
        await hm.edit(f"❌ **Failed!**\nলিংকটি হয়তো প্রাইভেট বা ভুল।\n`{str(e)[:50]}`")

# ================= বাটনে ক্লিক করলে ডাউনলোড শুরু =================
@bot.on(events.CallbackQuery(pattern=b"dl_"))
async def download_handler(e):
    data = e.data.decode().split("_")
    msg_id = data[1]
    quality = data[2]
    
    direct_vid = db.get(f"direct_vid_{msg_id}")
    yt_url = db.get(f"vidurl_{msg_id}")
    
    if not direct_vid and not yt_url:
        return await e.answer("⚠️ Link Expired! Please send the link again.", alert=True)
    
    await e.answer("Downloading... Please wait!", alert=False)
    hm = await e.reply("⏳ **Downloading to Server... / সার্ভারে ডাউনলোড হচ্ছে...**")
    
    if not os.path.exists("downloads"): os.makedirs("downloads")
    file_path = f"downloads/{e.sender_id}_{msg_id}.mp4"

    try:
        # TIKTOK DIRECT API DOWNLOAD
        if direct_vid:
            if quality == "audio":
                dl_url = db.get(f"direct_aud_{msg_id}")
                file_path = file_path.replace(".mp4", ".mp3")
            elif quality == "thumb":
                dl_url = db.get(f"direct_thumb_{msg_id}")
                await bot.send_file(e.chat_id, file=dl_url, caption="🖼 **Thumbnail Downloaded**")
                return await hm.delete()
            else:
                dl_url = direct_vid

            r = requests.get(dl_url, stream=True)
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()
            
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            bot.loop.create_task(progress_bar(downloaded, total_size, hm, start_time, hm.id))
            title = "TikTok Video"

        # YOUTUBE/FB DOWNLOAD
        else:
            base_opts = {
                'outtmpl': f'downloads/{e.sender_id}_%(id)s.%(ext)s',
                'quiet': True, 'nocheckcertificate': True,
                'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            }
            if quality == "audio":
                base_opts['format'] = 'bestaudio/best'
                base_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
            elif quality == "thumb":
                with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                    info = ydl.extract_info(yt_url, download=False)
                await bot.send_file(e.chat_id, file=info.get('thumbnail'), caption="🖼 **Thumbnail Downloaded**")
                return await hm.delete()
            elif quality == "max":
                base_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            else:
                base_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'

            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(yt_url, download=True)
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
        await hm.edit(f"❌ **Download Failed!**\nভিডিওটি ডাউনলোড করা সম্ভব হয়নি। Error: `{str(ex)[:40]}`")
        if os.path.exists(file_path): os.remove(file_path)

# ================= ADMIN SYSTEM =================
@bot.on(events.NewMessage(pattern="/admin", from_users=[ADMIN_ID]))
async def admin_panel(m):
    limit = get_setting("daily_limit", "5")
    limit_txt = "Unlimited" if limit == "0" else f"{limit} / day"
    
    text = (f"👑 **Ultimate Admin Panel**\n\n📊 **Daily Limit:** {limit_txt}\n\nCommands:\n`/ban userid` - ব্লক করুন\n`/unban userid` - আনব্লক করুন\n")
    buttons = [[Button.inline("📢 Setup Force Sub", data="admin_fs_setup")], [Button.inline("⚙️ Set Daily Limit", data="admin_limit")]]
    await m.reply(text, buttons=buttons)

# (বাকি অ্যাডমিন কমান্ডগুলো আগের মতই আছে...)
bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
