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

# আপনার অরিজিনাল ফাইল থেকে ইমপোর্ট করা হলো
from config import ADMINS, API_HASH, API_ID, BOT_TOKEN
from redis_db import db
from send_media import VideoSender
from terabox import get_data

bot = TelegramClient("main", API_ID, API_HASH)
log = logging.getLogger(__name__)

# ================= ডামি ওয়েব সার্ভার (Render) =================
async def handle_ping(request):
    return web.Response(text="All-in-One Bot is running beautifully!")

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

# সুপার আনশর্টনার (সর্ট লিংক থেকে আসল লিংক বের করবে)
def get_real_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'}
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
        return response.url
    except Exception:
        return url

# প্রফেশনাল টেলিগ্রাম প্রগ্রেস বার (শুধুমাত্র TikTok/YT এর জন্য, Terabox এর নিজস্ব বার আছে)
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
    eta_seconds = (total_mb - curr_mb) / speed if speed > 0 else 0
    m, s = divmod(int(eta_seconds), 60)
    eta_str = f"{m:02d}:{s:02d}s"
    
    text = (
        f"📤 **Uploading Video...**\n\n"
        f"[{bar}] **{percent:.1f}%**\n\n"
        f"📦 **Size:** `{curr_mb:.2f} MB / {total_mb:.2f} MB`\n"
        f"🚀 **Speed:** `{speed:.2f} MB/s`\n"
        f"⏳ **Time Left:** `{eta_str}`"
    )
    try:
        await msg.edit(text)
    except Exception:
        pass

# ================= মেইন ভিডিও ডাউনলোডার =================
@bot.on(events.NewMessage(incoming=True, func=lambda m: m.is_private and m.text and not m.text.startswith("/")))
async def get_message(m: Message):
    if db.get(f"paystate_{m.sender_id}"):
        return

    raw_url = extract_url(m.text)
    if not raw_url:
        return

    hm = await m.reply("🔍 **Processing Link...**\nলিংক যাচাই করা হচ্ছে...")

    # যেকোনো সর্ট লিংক থেকে আসল লিংক বের করা
    url = get_real_url(raw_url)

    # VIP ও Daily Limit চেক
    is_vip = db.get(f"vip_{m.sender_id}")
    if not is_vip and m.sender_id not in ADMINS:
        today = time.strftime("%Y-%m-%d")
        usage_key = f"usage_{m.sender_id}_{today}"
        current_usage = int(db.get(usage_key) or 0)
        if current_usage >= 5:
            return await hm.edit("⚠️ **Daily Limit Reached!**\n\nআপনি আজকের ৫টি ফ্রি ভিডিও ডাউনলোড করে ফেলেছেন। আনলিমিটেড ডাউনলোডের জন্য /start দিয়ে প্রিমিয়াম কিনুন।")
        db.incr(usage_key)
        db.expire(usage_key, 86400)

    try:
        terabox_domains = ["terabox", "1024tera", "4funbox", "mirrobox", "nephobox", "momerybox", "tibibox", "freeterabox", "terasharefile", "terafileshare", "teraboxapp"]
        
        if any(domain in url.lower() for domain in terabox_domains):
            # ==============================================
            # আপনার অরিজিনাল Terabox ও FastTelethon সিস্টেম
            # ==============================================
            try:
                data = get_data(url)
            except Exception:
                return await hm.edit("❌ Sorry! Terabox API is dead or maybe your link is broken.")
            
            if not data:
                return await hm.edit("❌ Sorry! Terabox API is dead or maybe your link is broken.")
                
            # ৫শ এমবি ফাইলের সাইজ লিমিট (ফ্রি ইউজারদের জন্য)
            if data.get("sizebytes") and int(data["sizebytes"]) > 524288000 and m.sender_id not in ADMINS and not is_vip:
                return await hm.edit(f"⚠️ **File is too big!**\nফ্রি ইউজাররা সর্বোচ্চ 500MB ডাউনলোড করতে পারবেন।\nDirect Link: {data['direct_link']}")

            # আপনার send_media.py এর VideoSender কল করা হলো
            sender = VideoSender(
                client=bot,
                data=data,
                message=m,
                edit_message=hm,
                url=url,
            )
            asyncio.create_task(sender.send_video())
            
        else:
            # ==============================================
            # YouTube, FB, TikTok, IG এর জন্য (All in One)
            # ==============================================
            await hm.edit("📥 **Downloading Video to Server...**\nসার্ভারে ভিডিও ডাউনলোড হচ্ছে...")
            if not os.path.exists("downloads"):
                os.makedirs("downloads")

            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': f'downloads/{m.sender_id}_%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
                }
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                title = info.get('title', 'Downloaded Video')

            # অডিও ডাউনলোডের জন্য লিংকটি Redis এ সেভ করা (২৪ ঘণ্টার জন্য)
            db.set(f"aud_{m.id}", url, ex=86400)
            btn = [[Button.inline("🎧 Download Audio (MP3)", data=f"audio_{m.id}")]]

            start_time = time.time()
            
            # টেলিগ্রামে পাঠানো এবং লাইভ প্রগ্রেস বার দেখানো
            await bot.send_file(
                m.chat_id,
                file=file_path,
                caption=f"🎬 **{title}**\n\n📥 Downloaded via VIP Bot",
                reply_to=m.id,
                buttons=btn,
                progress_callback=lambda curr, tot: bot.loop.create_task(progress_bar(curr, tot, hm, start_time, hm.id))
            )
            
            await hm.delete()
            if os.path.exists(file_path):
                os.remove(file_path)

    except Exception as e:
        await hm.edit(f"❌ **Failed!**\nভিডিওটি ডাউনলোড করা যায়নি। লিংকটি হয়তো প্রাইভেট বা ভুল।\n`{str(e)[:50]}`")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

# ================= অডিও জেনারেটর বাটন =================
@bot.on(events.CallbackQuery(pattern=b"audio_"))
async def extract_audio(e):
    msg_id = e.data.decode().split("_")[1]
    url = db.get(f"aud_{msg_id}")
    
    if not url:
        return await e.answer("⚠️ লিংকটির মেয়াদ শেষ! দয়া করে ভিডিওর লিংকটি আবার দিন।", alert=True)
    
    await e.answer("অডিও জেনারেট হচ্ছে, দয়া করে অপেক্ষা করুন...", alert=False)
    hm = await e.reply("🎧 **অডিও সার্ভারে ডাউনলোড হচ্ছে...**")
    
    try:
        if not os.path.exists("downloads"):
            os.makedirs("downloads")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': f'downloads/audio_{e.sender_id}_%(id)s.%(ext)s',
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_path = ydl.prepare_filename(info)

        start_time = time.time()
        await bot.send_file(
            e.chat_id,
            file=audio_path,
            caption=f"🎵 **{info.get('title', 'Audio')}**\n\n🎧 Downloaded via VIP Bot",
            reply_to=e.message.id,
            progress_callback=lambda curr, tot: bot.loop.create_task(progress_bar(curr, tot, hm, start_time, hm.id))
        )
        
        await hm.delete()
        if os.path.exists(audio_path):
            os.remove(audio_path)

    except Exception as ex:
        await hm.edit(f"❌ **অডিও জেনারেট করতে সমস্যা হয়েছে!**\nহয়তো ভিডিওটিতে কোনো অডিও নেই।")

bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
