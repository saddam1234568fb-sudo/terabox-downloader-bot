async def handle_message(m: Message):
    # --- পেমেন্ট স্টেটে থাকলে ইগনোর করবে ---
    if db.get(f"paystate_{m.sender_id}"):
        return 
    # ---------------------------------------
    
    url = get_urls_from_string(m.text)
    # বাকি সব আগের মতই থাকবে...
import asyncio
import logging
import time

import humanreadable as hr
from telethon.sync import TelegramClient, events
from telethon.tl.custom.message import Message

from config import ADMINS, API_HASH, API_ID, BOT_TOKEN, HOST, PASSWORD, PORT
from redis_db import db
from send_media import VideoSender
from terabox import get_data
from tools import extract_code_from_url, get_urls_from_string

bot = TelegramClient("main", API_ID, API_HASH)

log = logging.getLogger(__name__)


@bot.on(
    events.NewMessage(
        incoming=True,
        outgoing=False,
        func=lambda message: message.text
        and get_urls_from_string(message.text)
        and message.is_private,
    )
)
async def get_message(m: Message):
    asyncio.create_task(handle_message(m))


async def handle_message(m: Message):
    url = get_urls_from_string(m.text)
    if not url:
        return await m.reply("Please enter a valid url.")
    hm = await m.reply("Sending you the media wait...")
    is_spam = db.get(m.sender_id)
    if is_spam and m.sender_id not in ADMINS:
        ttl = db.ttl(m.sender_id)
        t = hr.Time(str(ttl), default_unit=hr.Time.Unit.SECOND)
        return await hm.edit(
            f"You are spamming.\n**Please wait {
                t.to_humanreadable()} and try again.**",
            parse_mode="markdown",
        )
    if_token_avl = db.get(f"active_{m.sender_id}")
    if not if_token_avl and m.sender_id not in ADMINS:
        return await hm.edit(
            "Your account is deactivated. send /gen to get activate it again."
        )
    shorturl = extract_code_from_url(url)
    if not shorturl:
        return await hm.edit("Seems like your link is invalid.")
    fileid = db.get_key(shorturl)
    if fileid:
        uid = db.get_key(f"mid_{fileid}")
        if uid:
            check = await VideoSender.forward_file(
                file_id=fileid, message=m, client=bot, edit_message=hm, uid=uid
            )
            if check:
                return
    try:
        data = get_data(url)
    except Exception:
        return await hm.edit("Sorry! API is dead or maybe your link is broken.")
    if not data:
        return await hm.edit("Sorry! API is dead or maybe your link is broken.")
    db.set(m.sender_id, time.monotonic(), ex=60)

    if int(data["sizebytes"]) > 524288000 and m.sender_id not in ADMINS:
        return await hm.edit(
            f"Sorry! File is too big.\n**I can download only 500MB and this file is of {
                data['size']}.**\nRather you can download this file from the link below:\n{data['url']}",
            parse_mode="markdown",
        )

    sender = VideoSender(
        client=bot,
        data=data,
        message=m,
        edit_message=hm,
        url=url,
    )
    asyncio.create_task(sender.send_video())

# --- Render এর জন্য Dummy Web Server ---
from aiohttp import web
import os

async def handle_ping(request):
    return web.Response(text="Bot is running on Render!")

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', handle_ping)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# বটের ইভেন্ট লুপের সাথে ওয়েব সার্ভার রান করা
loop = bot.loop
loop.create_task(start_web_server())
# --------------------------------------

bot.start(bot_token=BOT_TOKEN)

bot.run_until_disconnected()
