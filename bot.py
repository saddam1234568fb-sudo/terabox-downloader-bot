import logging
import time
import asyncio
from telethon import Button
from telethon.sync import TelegramClient, events
from telethon.tl.custom.message import Message

from config import API_HASH, API_ID, BOT_TOKEN, BOT_USERNAME
from redis_db import db
from tools import is_user_on_chat

log = logging.getLogger(__name__)

bot = TelegramClient("bot", API_ID, API_HASH)

# ================= কনফিগারেশন =================
ADMIN_ID = 8868874895  # আপনার অ্যাডমিন আইডি

def get_setting(key, default):
    val = db.get(f"settings_{key}")
    return val if val else default

# ================= 1. START & FORCE SUB =================
@bot.on(events.NewMessage(pattern="/start(.*)", incoming=True, func=lambda x: x.is_private))
async def start_cmd(m: Message):
    user_id = m.sender_id
    db.sadd("all_users", user_id) # ইউজার কাউন্ট করার জন্য
    
    force_link = get_setting("force_link", "https://t.me/RoldexVerse")
    if force_link != "none":
        channel_username = force_link.replace("https://t.me/", "@")
        check_if = await is_user_on_chat(bot, channel_username, user_id)
        if not check_if:
            return await m.reply(
                "⚠️ **Please join our channel to use this bot!**\nবটটি ব্যবহার করতে অনুগ্রহ করে আমাদের চ্যানেলে জয়েন করুন।",
                buttons=[
                    [Button.url("📢 Join Channel", url=force_link)],
                    [Button.url("🔄 Check Again", url=f"https://t.me/{BOT_USERNAME}?start=start")]
                ]
            )

    # Welcome Message
    default_welcome = "👋 **Welcome / স্বাগতম!**\n\nSend me any video link from YouTube, Facebook, TikTok, Terabox etc. and I will download it for you!\n\nযেকোনো ভিডিওর লিংক দিন, আমি ডাউনলোড করে দিব।"
    welcome_msg = get_setting("welcome_msg", default_welcome)
    support_link = get_setting("support_link", "https://t.me/ItsSaddam9")

    is_vip = db.get(f"vip_{user_id}")
    status = "👑 VIP Member" if is_vip else "🆓 Free User"

    await m.reply(
        f"{welcome_msg}\n\n📊 Status: **{status}**",
        link_preview=False,
        buttons=[
            [Button.inline("💎 Buy Premium / প্রিমিয়াম কিনুন", data="buy_vip")],
            [Button.url("👨‍💻 Support / সাপোর্ট", url=support_link)]
        ]
    )

# ================= 2. VIP & PAYMENT SYSTEM =================
@bot.on(events.CallbackQuery(pattern="buy_vip"))
async def buy_vip_menu(e):
    price_1 = get_setting("price_1", "50")
    price_3 = get_setting("price_3", "120")
    price_life = get_setting("price_life", "300")
    
    text = "💎 **Premium VIP Packages:**\nSelect a package to unlock unlimited fast downloads / আনলিমিটেড ডাউনলোডের জন্য প্যাকেজ বেছে নিন:"
    buttons = [
        [Button.inline(f"1 Month - {price_1} BDT", data=f"pay_1_{price_1}")],
        [Button.inline(f"3 Months - {price_3} BDT", data=f"pay_3_{price_3}")],
        [Button.inline(f"Lifetime - {price_life} BDT", data=f"pay_life_{price_life}")],
        [Button.inline("🔙 Back", data="main_menu")]
    ]
    await e.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"pay_"))
async def pay_method_menu(e):
    data = e.data.decode().split("_")
    pkg = data[1]
    price = data[2]
    
    text = f"📦 Package: **{pkg.capitalize()}**\n💰 Amount to Pay: **{price} BDT/USD**\n\n💳 **Select Payment Method / পেমেন্ট মাধ্যম সিলেক্ট করুন:**"
    buttons = [
        [Button.inline("🔴 bKash", data=f"checkout_bkash_{pkg}_{price}"), Button.inline("🟠 Nagad", data=f"checkout_nagad_{pkg}_{price}")],
        [Button.inline("🟣 Rocket", data=f"checkout_rocket_{pkg}_{price}"), Button.inline("🟡 Binance", data=f"checkout_binance_{pkg}_{price}")],
        [Button.inline("🔙 Back", data="buy_vip")]
    ]
    await e.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"checkout_"))
async def checkout_page(e):
    data = e.data.decode().split("_")
    method = data[1]
    pkg = data[2]
    price = data[3]
    
    num = get_setting(f"{method}_num", "01985664862" if method != "binance" else "your_binance_pay_id")
    
    text = f"💳 **{method.capitalize()} Payment**\n\n"
    text += f"1️⃣ Send **{price}** to this {method.capitalize()} number/ID:\n👉 `{num}`\n\n"
    text += "2️⃣ After sending money, send your **Transaction ID (TrxID) OR Screenshot** here.\nটাকা পাঠানোর পর ট্রানজেকশন আইডি বা স্ক্রিনশট লিখে এখানে সেন্ড করুন।"
    
    # পেমেন্ট স্টেটে রাখা
    db.set(f"paystate_{e.sender_id}", f"{method}_{pkg}_{price}")
    
    await e.edit(text, buttons=[[Button.inline("❌ Cancel", data="main_menu")]])

@bot.on(events.CallbackQuery(pattern="main_menu"))
async def back_main(e):
    db.delete(f"paystate_{e.sender_id}")
    await start_cmd(e)

# ================= 3. RECEIVE PAYMENT PROOF =================
@bot.on(events.NewMessage(incoming=True, func=lambda x: x.is_private and not x.text.startswith("/")))
async def receive_payment_proof(m: Message):
    user_id = m.sender_id
    state = db.get(f"paystate_{user_id}")
    
    if state:
        method, pkg, price = state.split("_")
        db.delete(f"paystate_{user_id}") # স্টেট ডিলিট
        
        caption = f"🔔 **NEW PAYMENT PROOF**\n\n👤 User: [{m.sender.first_name}](tg://user?id={user_id})\n🆔 ID: `{user_id}`\n📦 Pkg: {pkg} | 💰 Price: {price}\n💳 Method: {method.capitalize()}\n📝 TrxID/Msg: {m.text if m.text else 'Screenshot Attached'}"
        
        btn = [
            [Button.inline("✅ Approve", data=f"approve_{user_id}_{pkg}"), Button.inline("❌ Reject", data=f"reject_{user_id}")]
        ]
        
        await m.reply("⏳ **Your payment proof is sent to the Admin. Please wait for verification.**\nআপনার পেমেন্ট অ্যাডমিনের কাছে পাঠানো হয়েছে, দয়া করে অপেক্ষা করুন।")
        
        # Send to Admin
        if m.media:
            await bot.send_file(ADMIN_ID, m.media, caption=caption, buttons=btn)
        else:
            await bot.send_message(ADMIN_ID, caption, buttons=btn)

# ================= 4. ADMIN PANEL =================
@bot.on(events.NewMessage(pattern="/admin", from_users=[ADMIN_ID]))
async def admin_panel(m: Message):
    total_users = db.scard("all_users")
    
    text = f"🛠 **অ্যাডমিন প্যানেল**\n\n👥 Total Users: {total_users}\n"
    buttons = [
        [Button.inline("⚙️ Settings (Number/Price/Links)", data="admin_settings")],
        [Button.inline("📢 Broadcast", data="admin_broadcast")],
        [Button.inline("👑 VIP Members List", data="admin_vip_list")]
    ]
    await m.reply(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern="admin_settings", from_users=[ADMIN_ID]))
async def admin_settings(e):
    text = "⚙️ **Settings / সেটিংস:**\nWhat do you want to change?"
    buttons = [
        [Button.inline("🔴 bKash", data="set_bkash_num"), Button.inline("🟠 Nagad", data="set_nagad_num")],
        [Button.inline("🟣 Rocket", data="set_rocket_num"), Button.inline("🟡 Binance", data="set_binance_num")],
        [Button.inline("💰 Change Prices", data="set_prices"), Button.inline("📝 Welcome Msg", data="set_welcome_msg")],
        [Button.inline("📢 Force Sub Link", data="set_force_link"), Button.inline("📞 Support Link", data="set_support_link")],
        [Button.inline("🔙 Back", data="back_admin")]
    ]
    await e.edit(text, buttons=buttons)

# Settings Handlers (Dynamic Input via Redis State)
@bot.on(events.CallbackQuery(pattern=b"set_", from_users=[ADMIN_ID]))
async def ask_setting_input(e):
    setting_key = e.data.decode().replace("set_", "")
    db.set(f"adminstate_{e.sender_id}", setting_key)
    await e.reply(f"✍️ Please send the new value for **{setting_key}**:\n(Send /cancel to cancel)")

@bot.on(events.NewMessage(incoming=True, from_users=[ADMIN_ID]))
async def save_admin_input(m: Message):
    state = db.get(f"adminstate_{m.sender_id}")
    if state:
        if m.text == "/cancel":
            db.delete(f"adminstate_{m.sender_id}")
            return await m.reply("❌ Cancelled.")
        
        db.set(f"settings_{state}", m.text)
        db.delete(f"adminstate_{m.sender_id}")
        await m.reply(f"✅ Successfully updated **{state}** to:\n{m.text}")

# ================= 5. ADMIN APPROVE/REJECT =================
@bot.on(events.CallbackQuery(pattern=b"approve_", from_users=[ADMIN_ID]))
async def approve_payment(e):
    data = e.data.decode().split("_")
    user_id = int(data[1])
    pkg = data[2]
    
    # Calculate expiry
    expiry = time.time()
    if pkg == "1": expiry += 30 * 86400
    elif pkg == "3": expiry += 90 * 86400
    elif pkg == "life": expiry += 3650 * 86400 # 10 years
    
    db.set(f"vip_{user_id}", expiry)
    await e.edit(f"✅ Approved User `{user_id}` for {pkg} package.")
    
    try:
        await bot.send_message(user_id, f"🎉 **Congratulations! / অভিনন্দন!**\n\nYour payment has been verified. You are now a Premium VIP Member! 👑\nEnjoy unlimited downloads without any delay.")
    except:
        pass

@bot.on(events.CallbackQuery(pattern=b"reject_", from_users=[ADMIN_ID]))
async def reject_payment(e):
    user_id = int(e.data.decode().split("_")[1])
    await e.edit(f"❌ Rejected User `{user_id}`.")
    try:
        await bot.send_message(user_id, "❌ **Payment Verification Failed / পেমেন্ট ভেরিফাই হয়নি!**\n\nPlease provide valid TrxID or contact support.\nসঠিক TrxID দিন অথবা সাপোর্টে যোগাযোগ করুন।")
    except:
        pass

@bot.on(events.CallbackQuery(pattern="back_admin", from_users=[ADMIN_ID]))
async def back_to_admin(e):
    await admin_panel(e)

# ================= 6. BROADCAST SYSTEM =================
@bot.on(events.CallbackQuery(pattern="admin_broadcast", from_users=[ADMIN_ID]))
async def ask_broadcast(e):
    db.set(f"adminstate_{e.sender_id}", "broadcast")
    await e.reply("📢 Send the message or media you want to broadcast to all users:\n(Send /cancel to abort)")

@bot.on(events.NewMessage(incoming=True, from_users=[ADMIN_ID]))
async def execute_broadcast(m: Message):
    state = db.get(f"adminstate_{m.sender_id}")
    if state == "broadcast" and m.text != "/cancel":
        db.delete(f"adminstate_{m.sender_id}")
        users = db.smembers("all_users")
        await m.reply(f"🚀 Broadcasting to {len(users)} users...")
        
        sent = 0
        for u in users:
            try:
                if m.media:
                    await bot.send_file(int(u), m.media, caption=m.text)
                else:
                    await bot.send_message(int(u), m.text)
                sent += 1
                await asyncio.sleep(0.05) # Safe limit
            except:
                pass
        await m.reply(f"✅ Broadcast finished. Sent to {sent} users.")

bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
