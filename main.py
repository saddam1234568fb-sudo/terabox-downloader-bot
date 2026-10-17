import asyncio
import logging
import time
import os
import re
from aiohttp import web
import yt_dlp
from telethon.sync import TelegramClient, events
from telethon.tl.custom.message import Message

from config import ADMINS, API_HASH, API_ID, BOT_TOKEN
from redis_db import db
from send_media import VideoSender
from terabox import get_data

bot = TelegramClient("main", API_ID, API_HASH)
log = logging.getLogger(__name__)

# যেকোনো লিংক বের করার জেনেরিক ফাংশন (Terabox এর লিমিটেশন বাইপাস)
def extract_url(text):
    url_pattern = re.compile(r'(https?://[^\s]+)')
    match = url_pattern.search(text)
    return match.group(1) if match else None

# --- Render এর জন্য Dummy Web Server ---
async def handle_ping(request):
    return web.Response(text="All-in-One Bot is running on Render!")

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
# --------------------------------------

@bot.on(events.NewMessage(incoming=True, func=lambda m: m.is_private and m.text and not m.text.startswith("/")))
async def get_message(m: Message):
    # ১. পেমেন্ট স্টেটে থাকলে ইগনোর করবে (bot.py যেন কাজ করতে পারে)
    if db.get(f"paystate_{m.sender_id}"):
        return

    # ২. যেকোনো লিংক বের করা
    url = extract_url(m.text)
    if not url:
        return

    hm = await m.reply("⏳ **Processing your link... Please wait.**\nভিডিওটি প্রসেস করা হচ্ছে, দয়া করে অপেক্ষা করুন...")

    # ৩. VIP ও Daily Limit চেক (ফ্রি ইউজাররা দিনে ৫টি ভিডিও নামাতে পারবে)
    is_vip = db.get(f"vip_{m.sender_id}")
    if not is_vip and m.sender_id not in ADMINS:
        today = time.strftime("%Y-%m-%d")
        usage_key = f"usage_{m.sender_id}_{today}"
        current_usage = int(db.get(usage_key) or 0)
        if current_usage >= 5:
            return await hm.edit("⚠️ **Daily Limit Reached!**\n\nআপনি আজকের ৫টি ফ্রি ভিডিও ডাউনলোড করে ফেলেছেন। আনলিমিটেড ডাউনলোডের জন্য /start দিয়ে প্রিমিয়াম কিনুন।")
        db.incr(usage_key)
        db.expire(usage_key, 86400) # ২৪ ঘণ্টা পর রিসেট হবে

    # ৪. ডাউনলোড লজিক
    try:
        if "terabox" in url.lower() or "1024tera" in url.lower() or "nephobox" in url.lower() or "mirrobox" in url.lower():
            # Terabox এর জন্য আপনার আগের স্ক্রিপ্ট ব্যবহার হবে
            data = get_data(url)
            if not data:
                return await hm.edit("❌ Sorry! Terabox API is dead or link is broken.")
            
            sender = VideoSender(client=bot, data=data, message=m, edit_message=hm, url=url)
            asyncio.create_task(sender.send_video())
            
        else:
            # YouTube, FB, TikTok, IG এর জন্য yt-dlp ব্যবহার হবে
            await hm.edit("⏳ **Downloading using All-in-One Engine...**")
            
            if not os.path.exists("downloads"):
                os.makedirs("downloads")

            file_path = ""
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': f'downloads/{m.sender_id}_%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
            }

            # ভিডিও ডাউনলোড করা
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                title = info.get('title', 'Downloaded Video')

            await hm.edit("📤 **Uploading your video to Telegram...**\nটেলিগ্রামে ভিডিও আপলোড করা হচ্ছে...")
            
            # টেলিগ্রামে পাঠানো
            await bot.send_file(
                m.chat_id,
                file=file_path,
                caption=f"🎬 **{title}**\n\n📥 Downloaded via Premium Bot",
                reply_to=m.id
            )
            
            await hm.delete()
            
            # মেমোরি ক্লিয়ার করার জন্য ডাউনলোড করা ফাইল ডিলিট করা
            if os.path.exists(file_path):
                os.remove(file_path)

    except Exception as e:
        await hm.edit(f"❌ **Failed!**\nভিডিওটি ডাউনলোড করা যায়নি। লিংকটি হয়তো প্রাইভেট বা ভুল।\n`{str(e)[:40]}`")
        # এরর হলে ফাইল ডিলিট করা
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
