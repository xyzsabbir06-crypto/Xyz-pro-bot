import logging
import sqlite3
import os
import asyncio
import datetime
import json
import urllib.request
import urllib.error
import urllib.parse
import base64
import io
import wave
import re
import time
import shutil
import secrets
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
import psutil

# ==========================================
# ⚙️ CONFIGURATION (Railway Environment Variables)
# ==========================================
# Railway-তে Variables সেট করলে এখানে অটোমেটিক বসে যাবে
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")  
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))                        
INITIAL_GEMINI_KEY = os.getenv("INITIAL_GEMINI_KEY", "YOUR_GEMINI_API_KEY_HERE") 
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "YOUR_IMGBB_API_KEY_HERE") 

# Railway Volume Path Setup (ডাটা সেভ রাখার জন্য)
DB_DIR = "/app/data" if os.path.exists("/app/data") else "."
DB_PATH = os.path.join(DB_DIR, "voice_bot.db")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==========================================
# 🎛️ BUTTON SYSTEM 
# ==========================================
def _btn(text: str, style: str) -> dict:
    return {"text": text, "style": style}

def _reply_kb(rows: list[list[dict]], persistent: bool = True) -> str:
    return json.dumps({
        "keyboard": rows,
        "resize_keyboard": True,
        "is_persistent": persistent,
    }, ensure_ascii=False)

# ==========================================
# 🗄️ DATABASE SETUP
# ==========================================
def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT, username TEXT, reg_date TEXT,
        lang TEXT DEFAULT 'en', is_banned INTEGER DEFAULT 0, ban_reason TEXT,
        cnt_voice INTEGER DEFAULT 0, cnt_tiktok INTEGER DEFAULT 0, 
        cnt_img INTEGER DEFAULT 0, cnt_file INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE, status TEXT DEFAULT 'active'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS uploaded_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_code TEXT UNIQUE,
        owner_id INTEGER, 
        from_chat_id INTEGER, 
        message_id INTEGER, 
        title TEXT, 
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS force_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER, chat_id INTEGER, title TEXT, 
        username TEXT, invite_link TEXT, is_private INTEGER
    )''')
    
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_status', 'on')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('owner_link', 'https://t.me/YourUsername')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('channel_link', 'https://t.me/YourChannel')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_join_photo', '')")
    
    if IMGBB_API_KEY and IMGBB_API_KEY != "YOUR_IMGBB_API_KEY_HERE":
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('imgbb_api_key', ?)", (IMGBB_API_KEY,))
    if INITIAL_GEMINI_KEY and INITIAL_GEMINI_KEY != "YOUR_GEMINI_API_KEY_HERE":
        c.execute("INSERT OR IGNORE INTO api_keys (api_key) VALUES (?)", (INITIAL_GEMINI_KEY,))
        
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🌐 TRANSLATIONS
# ==========================================
VOICE_OPTIONS = {
    'Kore': '👩 Kore (Female)',
    'Aoede': '👩 Aoede (Female)',
    'Puck': '👨 Puck (Male)',
    'Charon': '👨 Charon (Male)',
    'Fenrir': '👨 Fenrir (Male)'
}

TR = {
    'en': {
        'welcome': (
            "✨ <b>WELCOME TO XYZ PRO</b> ✨\n\n👤 <b>Name:</b> {name}\n🆔 <b>User ID:</b> <code>{user_id}</code>\n🤖 <b>Bot:</b> @{bot_username}\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n🌟 <b>FEATURES</b>\n├ ⚡ Instant downloads\n├ 🎬 HD video • no watermark\n├ 🎵 MP3 audio extraction\n├ 🖼️ Image to URL converter\n├ 🎙️ Text to AI Voice\n├ 📤 File Upload & Sharing\n├ 🔗 Force Join Channels\n└ 🆓 100% free forever\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n👇 <i>Use the buttons below to begin</i>"
        ),
        'btn_tiktok': "⬇️ DOWNLOAD TIKTOK VIDEO",
        'btn_img2url': "🖼️ IMAGE 2 URL",
        'btn_voice': "🎙️ TEXT TO AI VOICE",
        'btn_upload': "📤 UPLOAD MENU",
        'btn_force_join': "🔗 FORCE JOIN CHANNELS",
        'btn_lang': "🌐 LANGUAGE",
        'btn_owner': "👑 OWNER",
        'btn_channel': "📢 OFFICIALS CHANNEL",
        'btn_back': "🔙 Back",
        'btn_back_user': "🔙 Main Menu",
        'btn_upload_action': "📤 UPLOAD FILE",
        'btn_my_file': "📁 MY FILE",
        'btn_add_channel': "➕ ADD CHANNEL",
        'btn_del_channel': "❌ DELETE CHANNEL",
        'btn_list_channel': "📋 CHANNEL LIST",
        
        'send_tiktok': "🔗 <b>SEND ME A TIKTOK LINK</b>\n━━━━━━━━━━━━━━━━━━\n\nPaste any public TikTok video URL below.\n\n<i>Example:</i>\n<code>https://www.tiktok.com/@user/video/123456</code>",
        'choose_format': "🎯 <b>What do you want?</b>", 'btn_video': "🎬 VIDEO", 'btn_music': "🎵 MUSIC",
        'processing': "⏳ <b>Processing...</b>\n<i>Please wait a moment.</i>",
        'error': "❌ <b>Error:</b> {error}",
        
        'send_voice_text': "📝 <b>Send me the text you want to convert to voice.</b>",
        'choose_voice': "🎙️ <b>Please select a voice:</b>",
        'success_voice': "✅ <b>Voice Generated Successfully!</b>",
        
        'send_image': "📸 <b>Send me the image you want to upload.</b>",
        'uploading_img': "⏫ <b>Uploading...</b>\n<i>Creating your link...</i>",
        'choose_expiry': "⏳ <b>Choose Expiry Time:</b>",
        'btn_1d': "1 Day", 'btn_3d': "3 Days", 'btn_7d': "7 Days", 'btn_unlimited': "♾ Unlimited",
        'img_success': "✅ <b>Image Uploaded!</b>\n\n🔗 <b>Your URL:</b>\n<code>{url}</code>\n\n⏳ <b>Expires:</b> {expiry}",
        'btn_copy_url': "📋 Copy URL",
        
        'upload_prompt': "📤 <b>Upload Anything!</b>\n\nYou can send text, voice, audio, video, document, photo, or even forward a message from any chat. I will store it and give you a deep link.",
        'upload_success': "✅ <b>File Stored Successfully!</b>\n\n🔗 <b>Your Deep Link:</b>\n<code>{link}</code>\n\n<i>Share this link. Users will get this exact file when they click it.</i>",
        'btn_copy_link': "📋 Copy Link",
        'my_files_empty': "📭 You haven't uploaded any files yet.",
        'my_file_details': "📄 <b>Title:</b> {title}\n🔗 <b>Link:</b> <code>{link}</code>",
        
        'add_channel_prompt': "➕ <b>Add Force Join Channel</b>\n\n1. Add me (@{bot_username}) as an Admin in your channel.\n2. Make sure I have <b>'Invite Users via Link'</b> permission.\n3. Forward any message from that channel here.\n\n<i>Note: You can also send the channel username (e.g., @mychannel) if it's public.</i>",
        'channel_added': "✅ <b>Channel Added Successfully!</b>\n\n📢 Title: {title}\n🆔 ID: <code>{cid}</code>",
        'channel_failed': "❌ Could not verify channel. Make sure I am an admin with 'Invite Users' permission there.",
        'no_channels': "📭 You haven't added any channels yet.",
        'channel_list': "📋 <b>Your Added Channels</b>\n\n",
        'del_channel_prompt': "❌ <b>Delete Channel</b>\n\nClick the channel below to delete it:",
        'channel_deleted': "✅ Channel deleted successfully.",
        
        'force_join_msg': (
            "📁 XYZ PRO 𝗕𝗢𝗧\n\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📢 𝗙𝗥𝗘𝗘 𝗙𝗜𝗟𝗘 𝗦𝗘𝗥𝗩𝗜𝗖𝗘\n"
            "━━━━━━━━━━━━━━━━━━\n\n\n"
            "📌 𝗙𝗜𝗟𝗘 𝗣𝗔𝗢𝗔𝗥 𝗡𝗜𝗬𝗢𝗠\n\n"
            "🔹 ① Join every channel below.\n"
            "🔹 ② After joining, press the Verify button.\n\n"
            "━━━━━━━━━━━━━━━━━━"
        ),
        'btn_verified': "Verified ✅",
        'verify_fail_missing': "❌ You haven't joined: {channels}.\nPlease join them first!",
        'verify_success': "✅ Verification successful! Here is your file.",
        
        'owner_info': "👑 <b>Owner Info</b>\n\nClick below to contact owner.",
        'contact_owner': "📞 Contact Owner",
        'lang_changed': "✅ Language changed to English.",
        
        'admin_panel': "👑 <b>Admin Panel</b>",
        'btn_stats': "📊 Stats", 'btn_users': "👥 All Users", 'btn_broadcast': "📢 Broadcast",
        'btn_api': "🔑 API Keys", 'btn_imgbb': "🖼️ ImgBB Key", 'btn_toggle_bot': "⚙️ Bot ON/OFF",
        'btn_set_owner': "🔗 Set Owner Link", 'btn_set_channel': "📢 Set Channel Link",
        'btn_fj_photo': "🖼️ FORCE JOIN PHOTO",
        'btn_set_fj_msg_en': "📝 FJ Msg (EN)",
        'btn_set_fj_msg_bn': "📝 FJ Msg (BN)",
        'add_api': "➕ Add API Key", 'delete_api': "❌ Delete API Key", 'view_api': "👁 View APIs",
        'send_api': "🔑 Send the Gemini API Key (or click Back to cancel):",
        'send_imgbb_key': "🖼️ Send your ImgBB API Key (or click Back to cancel):",
        'send_fj_photo': "🖼️ Send the photo you want to show on the Force Join page.",
        'send_fj_msg_en': "📝 Send the new Force Join Message (English):",
        'send_fj_msg_bn': "📝 Send the new Force Join Message (Bengali):",
        'fj_msg_updated': "✅ Force Join Message updated!",
        'fj_photo_updated': "✅ Force Join Photo updated!",
        'imgbb_key_updated': "✅ ImgBB API Key updated!",
        'api_added': "✅ API Key added successfully!", 'api_deleted': "✅ API Key deleted!",
        'api_exist': "❌ This API Key already exists.", 'no_api': "❌ No API keys found.",
        'send_owner': "🔗 Send the new Owner Link:", 'send_channel': "📢 Send the new Channel Link:",
        'link_updated': "✅ Link updated successfully!",
        'banned': "🚫 You are banned. Reason: {reason}",
        
        'stats_msg': "📊 <b>Bot Statistics</b>\n\n👥 Total Users: {users}\n🎙️ Total Voices: {voices}\n🎬 Total TikToks: {tiktoks}\n🖼️ Total Images: {images}\n📤 Total Files: {files}\n📢 Total Channels: {channels}\n\n💻 <b>System</b>\n💾 Storage: {storage} MB used\n⚙️ RAM: {ram} MB used",
        'user_profile': "👤 <b>User Profile</b>\n\n📛 Name: {name}\n🔗 Username: @{username}\n🆔 ID: <code>{user_id}</code>\n📅 Joined: {reg_date}\n🚦 Status: {status}\n\n📊 <b>Activity</b>\n🎙️ Voices: {cnt_voice}\n🎬 TikToks: {cnt_tiktok}\n🖼️ Images: {cnt_img}\n📤 Files: {cnt_file}\n📢 Channels: {cnt_channels}\n\n{ban_reason}",
        'btn_ban': "🚫 BAN USER", 'btn_unban': "✅ UNBAN USER"
    },
    'bn': {
        'welcome': (
            "✨ <b>XYZ প্রো-তে স্বাগতম</b> ✨\n\n👤 <b>নাম:</b> {name}\n🆔 <b>ইউজার আইডি:</b> <code>{user_id}</code>\n🤖 <b>বট:</b> @{bot_username}\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n🌟 <b>ফিচারসমূহ</b>\n├ ⚡ দ্রুত ডাউনলোড\n├ 🎬 HD ভিডিও\n├ 🎵 MP3 অডিও\n├ 🖼️ ইমেজ টু ইউআরএল\n├ 🎙️ টেক্সট টু ভয়েস\n├ 📤 ফাইল আপলোড ও শেয়ার\n├ 🔗 ফোর্স জয়েন চ্যানেল\n└ 🆓 চিরকাল ফ্রি\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n👇 <i>শুরু করতে নিচের বাটনগুলো ব্যবহার করুন</i>"
        ),
        'btn_tiktok': "⬇️ টিকটক ভিডিও ডাউনলোড",
        'btn_img2url': "🖼️ ইমেজ ২ ইউআরএল",
        'btn_voice': "🎙️ টেক্সট টু এআই ভয়েস",
        'btn_upload': "📤 আপলোড মেনু",
        'btn_force_join': "🔗 ফোর্স জয়েন চ্যানেল",
        'btn_lang': "🌐 ভাষা",
        'btn_owner': "👑 মালিক",
        'btn_channel': "📢 অফিসিয়াল চ্যানেল",
        'btn_back': "🔙 পিছনে",
        'btn_back_user': "🔙 মেইন মেনু",
        'btn_upload_action': "📤 ফাইল আপলোড",
        'btn_my_file': "📁 আমার ফাইল",
        'btn_add_channel': "➕ চ্যানেল যোগ করুন",
        'btn_del_channel': "❌ চ্যানেল ডিলিট করুন",
        'btn_list_channel': "📋 চ্যানেল লিস্ট",
        
        'send_tiktok': "🔗 <b>টিকটক লিংক পাঠান</b>\n━━━━━━━━━━━━━━━━━━\n\nযেকোনো পাবলিক টিকটক ভিডিওর লিংক নিচে পেস্ট করুন।\n\n<i>উদাহরণ:</i>\n<code>https://www.tiktok.com/@user/video/123456</code>",
        'choose_format': "🎯 <b>আপনি কী চান?</b>", 'btn_video': "🎬 ভিডিও", 'btn_music': "🎵 মিউজিক",
        'processing': "⏳ <b>প্রসেস হচ্ছে...</b>\n<i>অনুগ্রহ করে অপেক্ষা করুন।</i>",
        'error': "❌ <b>এরর:</b> {error}",
        
        'send_voice_text': "📝 <b>যে টেক্সটটি ভয়েসে রূপান্তর করতে চান সেটি পাঠান।</b>",
        'choose_voice': "🎙️ <b>অনুগ্রহ করে একটি ভয়েস সিলেক্ট করুন:</b>",
        'success_voice': "✅ <b>ভয়েস সফলভাবে তৈরি হয়েছে!</b>",
        
        'send_image': "📸 <b>যে ছবিটি আপলোড করতে চান সেটি পাঠান।</b>",
        'uploading_img': "⏫ <b>আপলোড হচ্ছে...</b>\n<i>আপনার লিংক তৈরি হচ্ছে...</i>",
        'choose_expiry': "⏳ <b>লিংকের মেয়াদ নির্বাচন করুন:</b>",
        'btn_1d': "১ দিন", 'btn_3d': "৩ দিন", 'btn_7d': "৭ দিন", 'btn_unlimited': "♾ আনলিমিটেড",
        'img_success': "✅ <b>ছবি আপলোড সম্পন্ন!</b>\n\n🔗 <b>আপনার ইউআরএল:</b>\n<code>{url}</code>\n\n⏳ <b>মেয়াদ:</b> {expiry}",
        'btn_copy_url': "📋 ইউআরএল কপি করুন",
        
        'upload_prompt': "📤 <b>যেকোনো কিছু আপলোড করুন!</b>\n\nআপনি টেক্সট, ভয়েস, অডিও, ভিডিও, ডকুমেন্ট, ছবি বা যেকোনো চ্যাট থেকে ফরওয়ার্ড করা মেসেজ পাঠাতে পারেন। আমি এটি সেভ করে একটি ডিপ লিংক দেবো।",
        'upload_success': "✅ <b>ফাইল সেভ হয়েছে!</b>\n\n🔗 <b>আপনার ডিপ লিংক:</b>\n<code>{link}</code>\n\n<i>এই লিংকটি শেয়ার করুন। কেউ ক্লিক করলে তাকে হুবহু এই ফাইলটি দেওয়া হবে।</i>",
        'btn_copy_link': "📋 লিংক কপি করুন",
        'my_files_empty': "📭 আপনি এখনো কোনো ফাইল আপলোড করেননি।",
        'my_file_details': "📄 <b>নাম:</b> {title}\n🔗 <b>লিংক:</b> <code>{link}</code>",
        
        'add_channel_prompt': "➕ <b>ফোর্স জয়েন চ্যানেল যোগ করুন</b>\n\n১. বটকে (@{bot_username}) আপনার চ্যানেলে অ্যাডমিন করুন।\n২. বটকে অবশ্যই <b>'Invite Users via Link'</b> পারমিশন দিন।\n৩. সেই চ্যানেল থেকে যেকোনো একটি মেসেজ এখানে ফরওয়ার্ড করুন।\n\n<i>বিঃদ্রঃ চ্যানেল পাবলিক হলে শুধু ইউজারনেম দিলেও হবে (যেমন: @mychannel)।</i>",
        'channel_added': "✅ <b>চ্যানেল সফলভাবে যোগ হয়েছে!</b>\n\n📢 নাম: {title}\n🆔 আইডি: <code>{cid}</code>",
        'channel_failed': "❌ চ্যানেল ভেরিফাই করা যায়নি। আমি যেন অ্যাডমিন আছি এবং 'Invite Users' পারমিশন আছে তা নিশ্চিত করুন।",
        'no_channels': "📭 আপনি এখনো কোনো চ্যানেল যোগ করেননি।",
        'channel_list': "📋 <b>আপনার যোগ করা চ্যানেলসমূহ</b>\n\n",
        'del_channel_prompt': "❌ <b>চ্যানেল ডিলিট করুন</b>\n\nডিলিট করতে নিচের চ্যানেলে ক্লিক করুন:",
        'channel_deleted': "✅ চ্যানেল সফলভাবে ডিলিট হয়েছে।",
        
        'force_join_msg': (
            "📁 XYZ PRO 𝗕𝗢𝗧\n\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📢 𝗙𝗥𝗘𝗘 𝗙𝗜𝗟𝗘 𝗦𝗘𝗥𝗩𝗜𝗖𝗘\n"
            "━━━━━━━━━━━━━━━━━━\n\n\n"
            "📌 𝗙𝗜𝗟𝗘 𝗣𝗔𝗢𝗔𝗥 𝗡𝗜𝗬𝗢𝗠\n\n"
            "🔹 ① নিচের প্রতিটি চ্যানেলে Join করুন।\n"
            "🔹 ② Join সম্পন্ন হলে Verify বাটনে চাপুন।\n\n"
            "━━━━━━━━━━━━━━━━━━"
        ),
        'btn_verified': "Verified ✅",
        'verify_fail_missing': "❌ আপনি এখনো জয়েন করেননি: {channels}।\nঅনুগ্রহ করে আগে এগুলোতে জয়েন করুন!",
        'verify_success': "✅ ভেরিফিকেশন সফল! এই নিন আপনার ফাইল।",
        
        'owner_info': "👑 <b>মালিকের তথ্য</b>\n\nযোগাযোগ করতে নিচে ক্লিক করুন।",
        'contact_owner': "📞 মালিকের সাথে যোগাযোগ",
        'lang_changed': "✅ ভাষা বাংলায় পরিবর্তন করা হয়েছে।",
        
        'admin_panel': "👑 <b>অ্যাডমিন প্যানেল</b>",
        'btn_stats': "📊 স্ট্যাটস", 'btn_users': "👥 সব ইউজার", 'btn_broadcast': "📢 ব্রডকাস্ট",
        'btn_api': "🔑 এপিআই কি", 'btn_imgbb': "🖼️ ইমেজবিবি কি", 'btn_toggle_bot': "⚙️ বট অন/অফ",
        'btn_set_owner': "🔗 মালিকের লিংক", 'btn_set_channel': "📢 চ্যানেল লিংক",
        'btn_fj_photo': "🖼️ ফোর্স জয়েন ছবি",
        'btn_set_fj_msg_en': "📝 FJ মেসেজ (EN)",
        'btn_set_fj_msg_bn': "📝 FJ মেসেজ (BN)",
        'add_api': "➕ এপিআই কি যোগ করুন", 'delete_api': "❌ এপিআই কি ডিলিট করুন", 'view_api': "👁 এপিআই কি দেখুন",
        'send_api': "🔑 জেমিনি এপিআই কি পাঠান (বাতিল করতে পিছনে চাপুন):",
        'send_imgbb_key': "🖼️ ইমেজবিবি এপিআই কি পাঠান (বাতিল করতে পিছনে চাপুন):",
        'send_fj_photo': "🖼️ ফোর্স জয়েন পেজে যে ছবিটি দেখাতে চান সেটি পাঠান।",
        'send_fj_msg_en': "📝 নতুন ফোর্স জয়েন মেসেজ (ইংরেজি) পাঠান:",
        'send_fj_msg_bn': "📝 নতুন ফোর্স জয়েন মেসেজ (বাংলা) পাঠান:",
        'fj_msg_updated': "✅ ফোর্স জয়েন মেসেজ আপডেট হয়েছে!",
        'fj_photo_updated': "✅ ফোর্স জয়েন ছবি আপডেট হয়েছে!",
        'imgbb_key_updated': "✅ ইমেজবিবি এপিআই কি আপডেট হয়েছে!",
        'api_added': "✅ এপিআই কি যোগ হয়েছে!", 'api_deleted': "✅ এপিআই কি ডিলিট হয়েছে!",
        'api_exist': "❌ এই এপিআই কি আগে থেকেই আছে।", 'no_api': "❌ কোনো এপিআই কি নেই।",
        'send_owner': "🔗 নতুন মালিকের লিংক পাঠান:", 'send_channel': "📢 নতুন চ্যানেলের লিংক পাঠান:",
        'link_updated': "✅ লিংক আপডেট হয়েছে!",
        'banned': "🚫 আপনাকে ব্যান করা হয়েছে। কারণ: {reason}",
        
        'stats_msg': "📊 <b>বট স্ট্যাটিসটিক্স</b>\n\n👥 মোট ইউজার: {users}\n🎙️ মোট ভয়েস: {voices}\n🎬 মোট টিকটক: {tiktoks}\n🖼️ মোট ছবি: {images}\n📤 মোট ফাইল: {files}\n📢 মোট চ্যানেল: {channels}\n\n💻 <b>সিস্টেম</b>\n💾 স্টোরেজ: {storage} MB ব্যবহৃত\n⚙️ র‍্যাম: {ram} MB ব্যবহৃত",
        'user_profile': "👤 <b>ইউজার প্রোফাইল</b>\n\n📛 নাম: {name}\n🔗 ইউজারনেম: @{username}\n🆔 আইডি: <code>{user_id}</code>\n📅 জয়েন: {reg_date}\n🚦 স্ট্যাটাস: {status}\n\n📊 <b>অ্যাক্টিভিটি</b>\n🎙️ ভয়েস: {cnt_voice}\n🎬 টিকটক: {cnt_tiktok}\n🖼️ ছবি: {cnt_img}\n📤 ফাইল: {cnt_file}\n📢 চ্যানেল: {cnt_channels}\n\n{ban_reason}",
        'btn_ban': "🚫 ব্যান করুন", 'btn_unban': "✅ আনব্যান করুন"
    }
}

def get_lang(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id = ?", (uid,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 'en'

def tr(uid, key, **kwargs):
    lang = get_lang(uid)
    text = TR.get(lang, TR['en']).get(key, TR['en'].get(key, "Text not found"))
    if kwargs:
        try: return text.format(**kwargs)
        except KeyError: return text
    return text

def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_fj_msg(uid):
    lang = get_lang(uid)
    custom_msg = get_setting(f'force_join_msg_{lang}')
    if custom_msg:
        return custom_msg
    return tr(uid, 'force_join_msg')

def is_admin(user_id):
    return str(user_id) == str(OWNER_ID)

# ==========================================
# 🎛️ KEYBOARDS
# ==========================================
def main_reply_kb(chat_id):
    return _reply_kb([
        [_btn(tr(chat_id, 'btn_tiktok'), "success")],
        [_btn(tr(chat_id, 'btn_img2url'), "primary"), _btn(tr(chat_id, 'btn_voice'), "primary")],
        [_btn(tr(chat_id, 'btn_upload'), "success"), _btn(tr(chat_id, 'btn_force_join'), "primary")],
        [_btn(tr(chat_id, 'btn_lang'), "danger"), _btn(tr(chat_id, 'btn_owner'), "danger")],
        [_btn(tr(chat_id, 'btn_channel'), "primary")]
    ])

def upload_menu_kb(chat_id):
    return _reply_kb([
        [_btn(tr(chat_id, 'btn_upload_action'), "success"), _btn(tr(chat_id, 'btn_my_file'), "primary")],
        [_btn(tr(chat_id, 'btn_back'), "danger")]
    ])

def back_reply_kb(chat_id):
    return _reply_kb([[_btn(tr(chat_id, 'btn_back'), "danger")]])

def force_join_menu_kb(chat_id):
    return _reply_kb([
        [_btn(tr(chat_id, 'btn_add_channel'), "success"), _btn(tr(chat_id, 'btn_del_channel'), "danger")],
        [_btn(tr(chat_id, 'btn_list_channel'), "primary"), _btn(tr(chat_id, 'btn_back_user'), "danger")]
    ])

def tiktok_reply_kb(chat_id):
    return _reply_kb([
        [_btn(tr(chat_id, 'btn_video'), "success"), _btn(tr(chat_id, 'btn_music'), "primary")],
        [_btn(tr(chat_id, 'btn_back'), "danger")]
    ])

def expiry_reply_kb(chat_id):
    return _reply_kb([
        [_btn(tr(chat_id, 'btn_1d'), "primary"), _btn(tr(chat_id, 'btn_3d'), "primary")],
        [_btn(tr(chat_id, 'btn_7d'), "primary"), _btn(tr(chat_id, 'btn_unlimited'), "success")],
        [_btn(tr(chat_id, 'btn_back'), "danger")]
    ])

def lang_reply_kb(chat_id):
    return _reply_kb([
        [_btn("🇬🇧 ENGLISH", "primary"), _btn("🇧🇩 বাংলা", "primary")],
        [_btn(tr(chat_id, 'btn_back'), "danger")]
    ])

def voice_select_kb(chat_id):
    return _reply_kb([
        [_btn(VOICE_OPTIONS['Kore'], "primary"), _btn(VOICE_OPTIONS['Aoede'], "primary")],
        [_btn(VOICE_OPTIONS['Puck'], "primary"), _btn(VOICE_OPTIONS['Charon'], "primary")],
        [_btn(VOICE_OPTIONS['Fenrir'], "primary")],
        [_btn(tr(chat_id, 'btn_back'), "danger")]
    ])

def admin_reply_kb(chat_id):
    return _reply_kb([
        [_btn(tr(chat_id, 'btn_stats'), "success"), _btn(tr(chat_id, 'btn_users'), "primary")],
        [_btn(tr(chat_id, 'btn_broadcast'), "primary"), _btn(tr(chat_id, 'btn_api'), "danger")],
        [_btn(tr(chat_id, 'btn_imgbb'), "primary"), _btn(tr(chat_id, 'btn_set_owner'), "primary")],
        [_btn(tr(chat_id, 'btn_set_channel'), "primary"), _btn(tr(chat_id, 'btn_fj_photo'), "primary")],
        [_btn(tr(chat_id, 'btn_set_fj_msg_en'), "primary"), _btn(tr(chat_id, 'btn_set_fj_msg_bn'), "primary")],
        [_btn(tr(chat_id, 'btn_toggle_bot'), "danger")],
        [_btn(tr(chat_id, 'btn_back_user'), "success")]
    ])

# ==========================================
# 🎬 TIKTOK DOWNLOADER LOGIC
# ==========================================
TIKWM_ENDPOINT = "https://www.tikwm.com/api/"
SNAPTIK_ENDPOINT = "https://snaptik.app/abc2.php"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_MEDIA_BYTES = 48 * 1024 * 1024
MAX_VIDEO_SECONDS = 30 * 60

def http_request(url, *, method="GET", payload=None, headers=None, timeout=35, max_bytes=3*1024*1024):
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers: hdrs.update(headers)
    request = Request(url, data=payload, headers=hdrs, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            chunks, total = [], 0
            while total < max_bytes:
                chunk = response.read(min(64 * 1024, max_bytes - total))
                if not chunk: break
                chunks.append(chunk); total += len(chunk)
            return response.status, dict(response.headers.items()), b"".join(chunks)
    except HTTPError as error:
        body = error.read(1024)
        raise RuntimeError(f"HTTP {error.code}: {body.decode(errors='replace')[:180]}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Unreachable: {error}") from error

def json_request(url, *, method="GET", data=None, headers=None, timeout=35):
    body = json.dumps(data).encode() if data is not None else None
    hdrs = {"Content-Type": "application/json"} if data is not None else {}
    if headers: hdrs.update(headers)
    _, _, raw = http_request(url, method=method, payload=body, headers=hdrs, timeout=timeout)
    try: return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error: raise RuntimeError("Invalid JSON") from error

def normalize_url(value):
    candidate = value.strip()
    if not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname: return None
    if len(candidate) > 2048: return None
    return candidate

TIKTOK_DOMAINS = ("tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com")

def is_tiktok_url(url):
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return any(host == d or host.endswith(f".{d}") for d in TIKTOK_DOMAINS)

def _remote_url(v):
    return v if isinstance(v, str) and v.startswith(("http://", "https://")) else None

def _media_links(value):
    videos, audios = [], []
    if isinstance(value, dict):
        for key, nested in value.items():
            hint = key.lower()
            url = _remote_url(nested)
            if url:
                if any(w in hint for w in ("music", "audio", "mp3", "sound")):
                    audios.append(url)
                elif any(w in hint for w in ("play", "video", "mp4", "download", "hd", "url")) \
                        and not any(w in hint for w in ("cover", "avatar", "image", "thumb")):
                    videos.append(url)
            v2, a2 = _media_links(nested); videos.extend(v2); audios.extend(a2)
    elif isinstance(value, list):
        for nested in value:
            v2, a2 = _media_links(nested); videos.extend(v2); audios.extend(a2)
    return list(dict.fromkeys(videos)), list(dict.fromkeys(audios))

def _resolve_tikwm(source_url):
    endpoint = f"{TIKWM_ENDPOINT}?{urlencode({'url': source_url, 'hd': '1'})}"
    response = json_request(endpoint, timeout=45)
    if not isinstance(response, dict) or response.get("code") not in {0, "0", None}:
        msg = response.get("msg") if isinstance(response, dict) else ""
        raise RuntimeError(str(msg or "TikWM failed"))
    data = response.get("data")
    if not isinstance(data, dict): raise RuntimeError("TikWM no data")
    duration = int(data.get("duration") or 0)
    if duration > MAX_VIDEO_SECONDS:
        raise RuntimeError(f"Video is {duration // 60} min. Limit is {MAX_VIDEO_SECONDS // 60} min.")
    video_urls, audio_urls = _media_links(data)
    preferred_video = [_remote_url(data.get(k)) for k in ("hdplay", "play", "wmplay") if _remote_url(data.get(k))]
    preferred_audio = [_remote_url(data.get(k)) for k in ("music", "music_url", "mp3", "audio") if _remote_url(data.get(k))]
    videos = list(dict.fromkeys(preferred_video + video_urls))
    audios = list(dict.fromkeys(preferred_audio + audio_urls))
    if not videos: raise RuntimeError("No video URL")
    size_hint = 0
    for key in ("hd_size", "size", "wm_size"):
        try: size_hint = max(size_hint, int(data.get(key) or 0))
        except (TypeError, ValueError): pass
    return {"title": str(data.get("title") or "TikTok media"),
            "video_url": videos[0], "audio_url": audios[0] if audios else "", "size": size_hint}

def _resolve_snaptik(source_url):
    body = urlencode({"url": source_url}).encode()
    _, _, raw = http_request(SNAPTIK_ENDPOINT, method="POST", payload=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "Referer": "https://snaptik.app/"},
        timeout=45, max_bytes=4 * 1024 * 1024)
    try: response = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error: raise RuntimeError("SnapTik invalid JSON") from error
    if isinstance(response, dict) and response.get("success") is False:
        raise RuntimeError("SnapTik failed")
    videos, audios = _media_links(response)
    if not videos: raise RuntimeError("No video URL")
    title = "TikTok media"
    if isinstance(response, dict):
        title = str(response.get("title") or (response.get("data") or {}).get("title") or title)
    return {"title": title, "video_url": videos[0], "audio_url": audios[0] if audios else "", "size": 0}

def resolve_tiktok(source_url):
    last = None
    for resolver in (_resolve_tikwm, _resolve_snaptik):
        try: return resolver(source_url)
        except Exception as error: last = error
    raise RuntimeError(f"Resolve failed: {last}")

# ==========================================
# 🔑 AUTO API ROTATION SYSTEM (GEMINI)
# ==========================================
def get_active_api_key():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT api_key FROM api_keys WHERE status = 'active' LIMIT 1")
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def mark_key_limit(api_key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE api_keys SET status = 'limit_reached' WHERE api_key = ?", (api_key,))
    conn.commit()
    conn.close()

def pcm_to_wav(pcm_bytes, sample_rate=24000, channels=1, sampwidth=2):
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, 'wb') as wf:
        wf.setnchannels(channels); wf.setsampwidth(sampwidth); wf.setframerate(sample_rate); wf.writeframes(pcm_bytes)
    wav_buf.seek(0)
    return wav_buf.read()

def split_text(text, max_chars=400):
    sentences = re.split(r'(?<=[.!?।\n])\s+', text)
    chunks, current_chunk = [], ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chars:
            current_chunk += sentence + " "
        else:
            if current_chunk: chunks.append(current_chunk.strip())
            if len(sentence) > max_chars:
                for i in range(0, len(sentence), max_chars): chunks.append(sentence[i:i+max_chars].strip())
                current_chunk = ""
            else: current_chunk = sentence + " "
    if current_chunk: chunks.append(current_chunk.strip())
    return chunks

def get_gemini_tts_audio(text, voice_name):
    api_key = get_active_api_key()
    if not api_key: raise Exception("All API keys reached limit! Add new key in Admin Panel.")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    chunks = split_text(text, max_chars=400)
    all_pcm_bytes = b""
    
    for chunk in chunks:
        payload = {
            "contents": [{"parts": [{"text": f"Generate speech audio only. Read the transcript below aloud exactly as written.\n\nTRANSCRIPT:\n{chunk}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}}}
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = json.loads(response.read().decode('utf-8'))
            base64_pcm = response_data['candidates'][0]['content']['parts'][0]['inlineData']['data']
            all_pcm_bytes += base64.b64decode(base64_pcm)
            time.sleep(0.3)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                mark_key_limit(api_key)
                return get_gemini_tts_audio(text, voice_name)
            raise Exception(f"API Error: HTTP {e.code}")
    return pcm_to_wav(all_pcm_bytes)

def upload_image_imgbb_sync(image_bytes, imgbb_key, expiry_seconds=None):
    url = "https://api.imgbb.com/1/upload"
    b64_image = base64.b64encode(image_bytes).decode('utf-8')
    payload = {'key': imgbb_key, 'image': b64_image}
    if expiry_seconds: payload['expiration'] = expiry_seconds
    data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_json = json.loads(response.read().decode('utf-8'))
            if res_json.get("success"):
                return res_json["data"]["url"]
            raise Exception(res_json.get("error", {}).get("message", "Unknown Error"))
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.read().decode()[:50]}")
    except Exception as e:
        raise Exception(str(e))

async def animate_loading(message, mode="voice"):
    frames = ["⏳ <b>Processing...</b>", "⌛ <b>Please wait...</b>", "🔄 <b>Working...</b>", "⚙️ <b>Almost Done...</b>"]
    idx = 0
    while True:
        try:
            await message.edit_text(frames[idx % len(frames)], parse_mode='HTML')
            idx += 1
            await asyncio.sleep(1.5)
        except asyncio.CancelledError: break
        except Exception: break

# ==========================================
# 📡 CHANNEL JOIN HELPERS
# ==========================================
async def get_channel_join_url(context, channel):
    if channel[4]: # username
        return "https://t.me/" + channel[4].lstrip("@")
    if channel[5]: # invite_link
        return channel[5]
    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=channel[2], name="File Store Join Request", creates_join_request=True
        )
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("UPDATE force_channels SET invite_link=? WHERE id=?", (invite.invite_link, channel[0]))
        conn.commit(); conn.close()
        return invite.invite_link
    except Exception:
        return None

async def check_user_in_channel(context, user_id, channel_id):
    try:
        member = await context.bot.get_chat_member(channel_id, user_id)
        return member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER) or (member.status == ChatMemberStatus.RESTRICTED and member.is_member)
    except Exception:
        return False

# ==========================================
# 📡 CHANNEL ADD LOGIC 
# ==========================================
async def process_channel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message = update.message
    text = message.text.strip() if message.text else ""
    
    chat_obj = None
    origin = getattr(message, "forward_origin", None)
    if origin:
        chat_obj = getattr(origin, "chat", None)
        
    if not chat_obj and message.forward_from_chat:
        chat_obj = message.forward_from_chat

    if not chat_obj and text.startswith('@'):
        try:
            chat_obj = await context.bot.get_chat(text)
        except:
            pass

    if chat_obj and chat_obj.type == 'channel':
        chat_id_to_add = chat_obj.id
        title = chat_obj.title or "Channel"
        username = getattr(chat_obj, "username", "") or ""
        is_private = 0 if username else 1

        try:
            member = await context.bot.get_chat_member(chat_id_to_add, context.bot.id)
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                invite_link = ""
                if is_private:
                    invite = await context.bot.create_chat_invite_link(
                        chat_id=chat_id_to_add, name="File Store Join Request", creates_join_request=True
                    )
                    invite_link = invite.invite_link

                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("SELECT id FROM force_channels WHERE owner_id = ? AND chat_id = ?", (user_id, chat_id_to_add))
                if c.fetchone():
                    await message.reply_text("❌ This channel is already added.", reply_markup=force_join_menu_kb(chat_id))
                    conn.close(); return

                c.execute("INSERT INTO force_channels (owner_id, chat_id, title, username, invite_link, is_private) VALUES (?, ?, ?, ?, ?, ?)",
                          (user_id, chat_id_to_add, title, username, invite_link, is_private))
                conn.commit(); conn.close()

                await message.reply_text(tr(chat_id, 'channel_added', title=title, cid=chat_id_to_add), reply_markup=force_join_menu_kb(chat_id), parse_mode='HTML')
            else:
                await message.reply_text("❌ Please make me an Admin in that channel first.", reply_markup=force_join_menu_kb(chat_id))
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}\nMake sure I am an Admin with 'Invite Users' permission.", reply_markup=force_join_menu_kb(chat_id))
        
        context.user_data['state'] = 'force_join_menu'
    else:
        await message.reply_text(tr(chat_id, 'channel_failed'), reply_markup=back_reply_kb(chat_id))

# ==========================================
# 🚀 MAIN HANDLERS
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data['state'] = None
    context.user_data['in_admin'] = False
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT is_banned, ban_reason FROM users WHERE user_id = ?", (user.id,))
    db_user = c.fetchone()
    
    if not db_user:
        reg_date = datetime.datetime.now().strftime("%Y-%m-%d")
        c.execute("INSERT INTO users (user_id, first_name, username, reg_date) VALUES (?, ?, ?, ?)",
                  (user.id, user.first_name, user.username, reg_date))
        conn.commit()
    elif db_user[0] == 1:
        await update.message.reply_text(tr(user.id, 'banned', reason=db_user[1]))
        conn.close(); return
    conn.close()
    
    # ডিপ লিংক চেক
    if context.args and context.args[0].startswith("file_"):
        file_code = context.args[0].replace("file_", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT owner_id, from_chat_id, message_id FROM uploaded_files WHERE file_code = ?", (file_code,))
        file_data = c.fetchone()
        
        if not file_data:
            await update.message.reply_text("❌ File not found or deleted.")
            conn.close(); return
            
        owner_id, from_chat_id, message_id = file_data
        
        c.execute("SELECT * FROM force_channels WHERE owner_id = ?", (owner_id,))
        channels = c.fetchall()
        conn.close()
        
        if channels:
            missing = []
            for ch in channels:
                if not await check_user_in_channel(context, user.id, ch[2]):
                    missing.append(ch)
            
            if not missing:
                try:
                    await context.bot.copy_message(chat_id=user.id, from_chat_id=from_chat_id, message_id=message_id)
                    await update.message.reply_text(tr(user.id, 'verify_success'), reply_markup=main_reply_kb(user.id))
                except Exception as e:
                    await update.message.reply_text(f"❌ File Error: {e}")
                return

            rows = []
            row = []
            for i, ch in enumerate(channels, 1):
                link = await get_channel_join_url(context, ch)
                if link:
                    btn = InlineKeyboardButton(f"JOIN {i}", url=link, style="danger") # Red Button
                    row.append(btn)
                if len(row) == 2:
                    rows.append(row); row = []
            if row: rows.append(row)
            rows.append([InlineKeyboardButton(tr(user.id, 'btn_verified'), callback_data=f"verify_join_{file_code}", style="success")]) # Green Button
            
            msg = get_fj_msg(user.id)
            photo = get_setting('force_join_photo')
            
            if photo:
                await update.message.reply_photo(photo=photo, caption=msg, reply_markup=InlineKeyboardMarkup(rows), parse_mode='HTML')
            else:
                await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(rows), parse_mode='HTML')
            return
        else:
            try:
                await context.bot.copy_message(chat_id=user.id, from_chat_id=from_chat_id, message_id=message_id)
                return
            except Exception as e:
                await update.message.reply_text(f"❌ Failed to deliver file: {e}")
                return

    welcome_text = tr(user.id, 'welcome', name=user.first_name, user_id=user.id, bot_username=context.bot.username)
    try:
        photos = await context.bot.get_user_profile_photos(context.bot.id)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            await update.message.reply_photo(photo=file_id, caption=welcome_text, reply_markup=main_reply_kb(user.id), parse_mode='HTML')
        else:
            await update.message.reply_text(welcome_text, reply_markup=main_reply_kb(user.id), parse_mode='HTML')
    except Exception:
        await update.message.reply_text(welcome_text, reply_markup=main_reply_kb(user.id), parse_mode='HTML')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text
    state = context.user_data.get('state')
    in_admin = context.user_data.get('in_admin', False)

    # চ্যানেল অ্যাড স্টেট
    if state == 'awaiting_channel_add':
        if text in [tr(chat_id, 'btn_back'), tr(chat_id, 'btn_back_user')]:
            context.user_data['state'] = 'force_join_menu'
            await update.message.reply_text("🔗 <b>Force Join Settings</b>", reply_markup=force_join_menu_kb(chat_id), parse_mode='HTML')
            return
        await process_channel_add(update, context)
        return

    if text == tr(chat_id, 'btn_back_user'):
        context.user_data['in_admin'] = False; context.user_data['state'] = None
        await update.message.reply_text("🏠 Main Menu", reply_markup=main_reply_kb(chat_id))
        return

    if text == tr(chat_id, 'btn_back'):
        context.user_data['state'] = None; context.user_data['admin_state'] = None
        if in_admin:
            await update.message.reply_text(tr(chat_id, 'admin_panel'), reply_markup=admin_reply_kb(chat_id), parse_mode='HTML')
        else:
            await update.message.reply_text("🏠 Main Menu", reply_markup=main_reply_kb(chat_id))
        return

    # --- ADMIN FLOWS ---
    if is_admin(user_id) and in_admin:
        if context.user_data.get('admin_state'):
            a_state = context.user_data.get('admin_state')
            if a_state == 'broadcast':
                context.user_data['admin_state'] = None
                await update.message.reply_text("✅ Broadcast Sent (Simulated).", reply_markup=admin_reply_kb(chat_id))
                return
            elif a_state == 'set_owner':
                set_setting('owner_link', text); context.user_data['admin_state'] = None
                await update.message.reply_text(tr(chat_id, 'link_updated'), reply_markup=admin_reply_kb(chat_id)); return
            elif a_state == 'set_channel':
                set_setting('channel_link', text); context.user_data['admin_state'] = None
                await update.message.reply_text(tr(chat_id, 'link_updated'), reply_markup=admin_reply_kb(chat_id)); return
            elif a_state == 'add_api':
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                try:
                    c.execute("INSERT INTO api_keys (api_key) VALUES (?)", (text,)); conn.commit()
                    await update.message.reply_text(tr(chat_id, 'api_added'), reply_markup=admin_reply_kb(chat_id))
                except:
                    await update.message.reply_text(tr(chat_id, 'api_exist'), reply_markup=admin_reply_kb(chat_id))
                conn.close(); context.user_data['admin_state'] = None; return
            elif a_state == 'set_imgbb':
                set_setting('imgbb_api_key', text)
                context.user_data['admin_state'] = None
                await update.message.reply_text(tr(chat_id, 'imgbb_key_updated'), reply_markup=admin_reply_kb(chat_id))
                return
            elif a_state == 'set_fj_msg_en':
                set_setting('force_join_msg_en', text); context.user_data['admin_state'] = None
                await update.message.reply_text(tr(chat_id, 'fj_msg_updated'), reply_markup=admin_reply_kb(chat_id)); return
            elif a_state == 'set_fj_msg_bn':
                set_setting('force_join_msg_bn', text); context.user_data['admin_state'] = None
                await update.message.reply_text(tr(chat_id, 'fj_msg_updated'), reply_markup=admin_reply_kb(chat_id)); return

        if text == tr(chat_id, 'btn_stats'):
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users"); u = c.fetchone()[0]
            c.execute("SELECT SUM(cnt_voice), SUM(cnt_tiktok), SUM(cnt_img), SUM(cnt_file) FROM users"); stats = c.fetchone()
            c.execute("SELECT COUNT(*) FROM force_channels"); ch = c.fetchone()[0]
            conn.close()
            
            total_voices = stats[0] or 0; total_tiktoks = stats[1] or 0
            total_imgs = stats[2] or 0; total_files = stats[3] or 0
            
            try:
                total, used, free = shutil.disk_usage("/")
                storage = round(used / (1024**3), 2)
            except: storage = "N/A"
            
            try: ram = round(psutil.virtual_memory().used / (1024**2), 2)
            except: ram = "N/A"
            
            msg = tr(chat_id, 'stats_msg', users=u, voices=total_voices, tiktoks=total_tiktoks, images=total_imgs, files=total_files, channels=ch, storage=storage, ram=ram)
            await update.message.reply_text(msg, reply_markup=admin_reply_kb(chat_id), parse_mode='HTML')
            return
            
        elif text == tr(chat_id, 'btn_users'):
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT user_id, first_name FROM users LIMIT 20"); users = c.fetchall(); conn.close()
            kb = []
            for uid, name in users:
                kb.append([InlineKeyboardButton(f"👤 {name} ({uid})", callback_data=f"adm_user_{uid}")])
            await update.message.reply_text("👥 <b>All Users</b>\nSelect a user:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            return
            
        elif text == tr(chat_id, 'btn_broadcast'):
            context.user_data['admin_state'] = 'broadcast'
            await update.message.reply_text("📢 Send the message you want to broadcast:", reply_markup=back_reply_kb(chat_id))
            return
            
        elif text == tr(chat_id, 'btn_api'):
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT api_key, status FROM api_keys"); keys = c.fetchall(); conn.close()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(tr(chat_id, 'add_api'), callback_data="adm_add_api")],
                [InlineKeyboardButton(tr(chat_id, 'delete_api'), callback_data="adm_del_api")],
                [InlineKeyboardButton(tr(chat_id, 'view_api'), callback_data="adm_view_api")]
            ])
            await update.message.reply_text(tr(chat_id, 'btn_api'), reply_markup=kb)
            return
            
        elif text == tr(chat_id, 'btn_imgbb'):
            context.user_data['admin_state'] = 'set_imgbb'
            await update.message.reply_text(tr(chat_id, 'send_imgbb_key'), reply_markup=back_reply_kb(chat_id))
            return
            
        elif text == tr(chat_id, 'btn_set_owner'):
            context.user_data['admin_state'] = 'set_owner'
            await update.message.reply_text(tr(chat_id, 'send_owner'), reply_markup=back_reply_kb(chat_id))
            return
            
        elif text == tr(chat_id, 'btn_set_channel'):
            context.user_data['admin_state'] = 'set_channel'
            await update.message.reply_text(tr(chat_id, 'send_channel'), reply_markup=back_reply_kb(chat_id))
            return
            
        elif text == tr(chat_id, 'btn_fj_photo'):
            context.user_data['admin_state'] = 'awaiting_fj_photo'
            await update.message.reply_text(tr(chat_id, 'send_fj_photo'), reply_markup=back_reply_kb(chat_id))
            return

        elif text == tr(chat_id, 'btn_set_fj_msg_en'):
            context.user_data['admin_state'] = 'set_fj_msg_en'
            await update.message.reply_text(tr(chat_id, 'send_fj_msg_en'), reply_markup=back_reply_kb(chat_id))
            return
            
        elif text == tr(chat_id, 'btn_set_fj_msg_bn'):
            context.user_data['admin_state'] = 'set_fj_msg_bn'
            await update.message.reply_text(tr(chat_id, 'send_fj_msg_bn'), reply_markup=back_reply_kb(chat_id))
            return
            
        elif text == tr(chat_id, 'btn_toggle_bot'):
            curr = get_setting('bot_status'); new = 'off' if curr == 'on' else 'on'
            set_setting('bot_status', new)
            await update.message.reply_text(f"✅ Bot is now {new.upper()}", reply_markup=admin_reply_kb(chat_id))
            return

    # --- USER FLOWS ---
    if text == tr(chat_id, 'btn_tiktok'):
        context.user_data['state'] = 'awaiting_tiktok_url'
        await update.message.reply_text(tr(chat_id, 'send_tiktok'), reply_markup=back_reply_kb(chat_id), parse_mode='HTML')
        return
    elif text == tr(chat_id, 'btn_img2url'):
        context.user_data['state'] = 'awaiting_image'
        await update.message.reply_text(tr(chat_id, 'send_image'), reply_markup=back_reply_kb(chat_id), parse_mode='HTML')
        return
    elif text == tr(chat_id, 'btn_voice'):
        context.user_data['state'] = 'awaiting_voice_choice'
        await update.message.reply_text(tr(chat_id, 'choose_voice'), reply_markup=voice_select_kb(chat_id), parse_mode='HTML')
        return
    elif text == tr(chat_id, 'btn_upload'):
        context.user_data['state'] = 'upload_menu'
        await update.message.reply_text("📤 <b>Upload Menu</b>", reply_markup=upload_menu_kb(chat_id), parse_mode='HTML')
        return
    elif text == tr(chat_id, 'btn_upload_action'):
        context.user_data['state'] = 'awaiting_upload'
        await update.message.reply_text(tr(chat_id, 'upload_prompt'), reply_markup=back_reply_kb(chat_id), parse_mode='HTML')
        return
    elif text == tr(chat_id, 'btn_my_file'):
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT file_code, title FROM uploaded_files WHERE owner_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
        files = c.fetchall()
        conn.close()
        
        if not files:
            await update.message.reply_text(tr(chat_id, 'my_files_empty'), reply_markup=upload_menu_kb(chat_id), parse_mode='HTML')
            return
            
        await update.message.reply_text("📁 <b>Your Recent Files:</b>", reply_markup=upload_menu_kb(chat_id), parse_mode='HTML')
        for f_code, title in files:
            link = f"https://t.me/{context.bot.username}?start=file_{f_code}"
            msg = tr(chat_id, 'my_file_details', title=title, link=link)
            await update.message.reply_text(msg, parse_mode='HTML', disable_web_page_preview=True)
        return
    elif text == tr(chat_id, 'btn_force_join'):
        context.user_data['state'] = 'force_join_menu'
        await update.message.reply_text("🔗 <b>Force Join Settings</b>", reply_markup=force_join_menu_kb(chat_id), parse_mode='HTML')
        return
    elif text == tr(chat_id, 'btn_lang'):
        context.user_data['state'] = 'awaiting_lang'
        await update.message.reply_text("🌐 Select Language / ভাষা নির্বাচন করুন:", reply_markup=lang_reply_kb(chat_id))
        return
    elif text == tr(chat_id, 'btn_owner'):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(tr(chat_id, 'contact_owner'), url=get_setting('owner_link'))]])
        await update.message.reply_text(tr(chat_id, 'owner_info'), reply_markup=kb, parse_mode='HTML')
        return
    elif text == tr(chat_id, 'btn_channel'):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=get_setting('channel_link'))]])
        await update.message.reply_text("📢 <b>Official Channel</b>", reply_markup=kb, parse_mode='HTML')
        return

    # --- FORCE JOIN MENU ---
    if state == 'force_join_menu':
        if text == tr(chat_id, 'btn_add_channel'):
            context.user_data['state'] = 'awaiting_channel_add'
            await update.message.reply_text(tr(chat_id, 'add_channel_prompt', bot_username=context.bot.username), reply_markup=back_reply_kb(chat_id), parse_mode='HTML')
        elif text == tr(chat_id, 'btn_del_channel'):
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id, title FROM force_channels WHERE owner_id = ?", (user_id,)); ch = c.fetchall(); conn.close()
            if not ch: return await update.message.reply_text(tr(chat_id, 'no_channels'), reply_markup=force_join_menu_kb(chat_id))
            kb = [[InlineKeyboardButton(f"❌ {t}", callback_data=f"del_ch_{i}")] for i, t in ch]
            await update.message.reply_text(tr(chat_id, 'del_channel_prompt'), reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        elif text == tr(chat_id, 'btn_list_channel'):
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT title, chat_id FROM force_channels WHERE owner_id = ?", (user_id,)); ch = c.fetchall(); conn.close()
            if not ch: return await update.message.reply_text(tr(chat_id, 'no_channels'), reply_markup=force_join_menu_kb(chat_id))
            msg = tr(chat_id, 'channel_list')
            for i, (title, cid) in enumerate(ch, 1):
                msg += f"{i}. <b>{title}</b>\nID: <code>{cid}</code>\n\n"
            await update.message.reply_text(msg, reply_markup=force_join_menu_kb(chat_id), parse_mode='HTML')
        return

    # --- STANDARD STATES ---
    if state == 'awaiting_lang' and text in ["🇬🇧 ENGLISH", "🇧🇩 বাংলা"]:
        lang = 'en' if text == "🇬🇧 ENGLISH" else 'bn'
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id)); conn.commit(); conn.close()
        context.user_data['state'] = None
        await update.message.reply_text(tr(user_id, 'lang_changed'), reply_markup=main_reply_kb(user_id))
        return

    if state == 'awaiting_tiktok_url':
        if not re.search(r'tiktok\.com', text): return await update.message.reply_text("❌ Invalid URL.", reply_markup=back_reply_kb(chat_id))
        context.user_data['tiktok_url'] = text; context.user_data['state'] = 'awaiting_tiktok_format'
        await update.message.reply_text(tr(chat_id, 'choose_format'), reply_markup=tiktok_reply_kb(chat_id))
        return

    if state == 'awaiting_tiktok_format' and text in [tr(chat_id, 'btn_video'), tr(chat_id, 'btn_music')]:
        wait_msg = await update.message.reply_text(tr(chat_id, 'processing'), parse_mode='HTML')
        try:
            info = await asyncio.to_thread(resolve_tiktok, context.user_data.get('tiktok_url'))
            if text == tr(chat_id, 'btn_video'): 
                media_url = info.get('video_url')
                if not media_url: raise Exception("No video available")
                await context.bot.send_video(chat_id, video=media_url, reply_markup=main_reply_kb(chat_id))
            else: 
                media_url = info.get('audio_url')
                if not media_url: raise Exception("No audio available")
                await context.bot.send_audio(chat_id, audio=media_url, reply_markup=main_reply_kb(chat_id))
            
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("UPDATE users SET cnt_tiktok = cnt_tiktok + 1 WHERE user_id = ?", (user_id,)); conn.commit(); conn.close()
        except Exception as e: await update.message.reply_text(tr(chat_id, 'error', error=str(e)), reply_markup=main_reply_kb(chat_id))
        finally: context.user_data['state'] = None; await wait_msg.delete()
        return

    if state == 'awaiting_voice_choice':
        voice_key = next((k for k, v in VOICE_OPTIONS.items() if v == text), None)
        if voice_key:
            context.user_data['selected_voice'] = voice_key
            context.user_data['state'] = 'awaiting_voice_text'
            await update.message.reply_text(tr(chat_id, 'send_voice_text'), reply_markup=back_reply_kb(chat_id), parse_mode='HTML')
        return

    if state == 'awaiting_voice_text':
        if len(text) > 3000: return await update.message.reply_text("❌ Max 3000 characters.", reply_markup=back_reply_kb(chat_id))
        voice_key = context.user_data.get('selected_voice', 'Kore')
        wait_msg = await update.message.reply_text(tr(chat_id, 'processing'), parse_mode='HTML')
        anim = asyncio.create_task(animate_loading(wait_msg))
        try:
            audio = await asyncio.to_thread(get_gemini_tts_audio, text, voice_key)
            anim.cancel()
            await update.message.reply_audio(audio=io.BytesIO(audio), caption=tr(chat_id, 'success_voice'), reply_markup=main_reply_kb(chat_id), parse_mode='HTML')
            
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("UPDATE users SET cnt_voice = cnt_voice + 1 WHERE user_id = ?", (user_id,)); conn.commit(); conn.close()
        except Exception as e:
            anim.cancel(); await update.message.reply_text(tr(chat_id, 'error', error=str(e)), reply_markup=main_reply_kb(chat_id))
        finally:
            context.user_data['state'] = None
            try: await wait_msg.delete()
            except: pass
        return

    if state == 'awaiting_image_expiry':
        expiry_map = {
            tr(chat_id, 'btn_1d'): ("1 Day", 86400), tr(chat_id, 'btn_3d'): ("3 Days", 259200),
            tr(chat_id, 'btn_7d'): ("7 Days", 604800), tr(chat_id, 'btn_unlimited'): ("Unlimited", None)
        }
        if text in expiry_map:
            expiry_text, expiry_sec = expiry_map[text]
            img_data = context.user_data.get('image_bytes')
            imgbb_key = get_setting('imgbb_api_key')
            if not imgbb_key: return await update.message.reply_text("❌ ImgBB API Key is not set. Please contact Admin.", reply_markup=main_reply_kb(chat_id))

            wait_msg = await update.message.reply_text(tr(chat_id, 'uploading_img'), parse_mode='HTML')
            try:
                url = await asyncio.to_thread(upload_image_imgbb_sync, img_data, imgbb_key, expiry_sec)
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(tr(chat_id, 'btn_copy_url'), url=url)]])
                await update.message.reply_text(tr(chat_id, 'img_success', url=url, expiry=expiry_text), reply_markup=kb, parse_mode='HTML')
                
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("UPDATE users SET cnt_img = cnt_img + 1 WHERE user_id = ?", (user_id,)); conn.commit(); conn.close()
            except Exception as e:
                await update.message.reply_text(tr(chat_id, 'error', error=str(e)), reply_markup=main_reply_kb(chat_id))
            finally:
                context.user_data['state'] = None; context.user_data['image_bytes'] = None
                await wait_msg.delete()
        return

    if state == 'awaiting_upload':
        pass # Handled by media handler

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') != 'awaiting_upload': return
    
    msg = update.message
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    title = get_message_title(msg)
    
    try:
        # Generate secure unguessable random code
        file_code = secrets.token_hex(8)
        
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("INSERT INTO uploaded_files (file_code, owner_id, from_chat_id, message_id, title, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (file_code, user_id, chat_id, msg.message_id, title, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        c.execute("UPDATE users SET cnt_file = cnt_file + 1 WHERE user_id = ?", (user_id,))
        conn.commit(); conn.close()
        
        bot_username = context.bot.username
        deep_link = f"https://t.me/{bot_username}?start=file_{file_code}"
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(tr(chat_id, 'btn_copy_link'), url=deep_link)]])
        await msg.reply_text(tr(chat_id, 'upload_success', link=deep_link), reply_markup=kb, parse_mode='HTML')
        context.user_data['state'] = 'upload_menu'
        await msg.reply_text("📤 <b>Upload Menu</b>", reply_markup=upload_menu_kb(chat_id), parse_mode='HTML')
    except Exception as e:
        await msg.reply_text(f"❌ Error: {e}", reply_markup=main_reply_kb(chat_id))
        context.user_data['state'] = None

def get_message_title(message):
    if message.text: return message.text[:70].replace("\n", " ")
    if message.caption: return message.caption[:70].replace("\n", " ")
    if message.document: return message.document.file_name or "Document"
    if message.photo: return "Photo"
    if message.video: return message.video.file_name or "Video"
    if message.audio: return message.audio.file_name or "Audio"
    if message.voice: return "Voice message"
    return "Telegram content"

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    
    if is_admin(update.effective_user.id) and context.user_data.get('admin_state') == 'awaiting_fj_photo':
        file_id = update.message.photo[-1].file_id
        set_setting('force_join_photo', file_id)
        context.user_data['admin_state'] = None
        await update.message.reply_text(tr(update.effective_chat.id, 'fj_photo_updated'), reply_markup=admin_reply_kb(update.effective_chat.id))
        return
        
    if state == 'awaiting_image':
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        context.user_data['image_bytes'] = img_bytes
        context.user_data['state'] = 'awaiting_image_expiry'
        await update.message.reply_text(tr(update.effective_chat.id, 'choose_expiry'), reply_markup=expiry_reply_kb(update.effective_chat.id))
    elif state == 'awaiting_upload':
        await handle_file_upload(update, context)
    elif state == 'awaiting_channel_add':
        await process_channel_add(update, context)

async def handle_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    if state == 'awaiting_upload':
        await handle_file_upload(update, context)
    elif state == 'awaiting_channel_add':
        await process_channel_add(update, context)

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data['in_admin'] = True; context.user_data['state'] = None
    await update.message.reply_text(tr(update.effective_chat.id, 'admin_panel'), reply_markup=admin_reply_kb(update.effective_chat.id), parse_mode='HTML')

async def show_admin_user_profile(query, target_id):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT first_name, username, reg_date, is_banned, ban_reason, cnt_voice, cnt_tiktok, cnt_img, cnt_file FROM users WHERE user_id = ?", (target_id,))
    u = c.fetchone()
    c.execute("SELECT COUNT(*) FROM force_channels WHERE owner_id = ?", (target_id,))
    ch_count = c.fetchone()[0]
    conn.close()
    
    if u:
        status = "Banned" if u[3] else "Active"
        ban_reason = f"🚫 Reason: {u[4]}" if u[3] else ""
        msg = tr(query.message.chat_id, 'user_profile', name=u[0], username=u[1] if u[1] else "None", user_id=target_id, reg_date=u[2], status=status, cnt_voice=u[5], cnt_tiktok=u[6], cnt_img=u[7], cnt_file=u[8], cnt_channels=ch_count, ban_reason=ban_reason)
        
        if u[3]: btn_action = InlineKeyboardButton(tr(query.message.chat_id, 'btn_unban'), callback_data=f"adm_unban_{target_id}")
        else: btn_action = InlineKeyboardButton(tr(query.message.chat_id, 'btn_ban'), callback_data=f"adm_ban_{target_id}")
            
        kb = InlineKeyboardMarkup([
            [btn_action],
            [InlineKeyboardButton(tr(query.message.chat_id, 'btn_back'), callback_data="adm_back_panel")]
        ])
        await query.message.edit_text(msg, reply_markup=kb, parse_mode='HTML')

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data; chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    if data == "adm_back_panel" or data == "adm_back":
        context.user_data['in_admin'] = True
        await query.message.delete()
        await context.bot.send_message(chat_id, tr(chat_id, 'admin_panel'), reply_markup=admin_reply_kb(chat_id), parse_mode='HTML')
        return
        
    if data.startswith("verify_join_"):
        file_code = data.replace("verify_join_", "")
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT owner_id, from_chat_id, message_id FROM uploaded_files WHERE file_code = ?", (file_code,))
        file_data = c.fetchone()
        if not file_data:
            return await query.answer("File not found.", show_alert=True)
            
        owner_id, from_chat_id, message_id = file_data
        c.execute("SELECT * FROM force_channels WHERE owner_id = ?", (owner_id,))
        channels = c.fetchall()
        conn.close()
        
        missing = []
        missing_indices = []
        for i, ch in enumerate(channels, 1):
            if not await check_user_in_channel(context, user_id, ch[2]):
                missing.append(ch)
                missing_indices.append(str(i))
                
        if missing:
            missing_str = ", ".join([f"JOIN {i}" for i in missing_indices])
            await query.answer(tr(chat_id, 'verify_fail_missing', channels=missing_str), show_alert=True)
        else:
            await query.message.delete()
            await query.message.reply_text(tr(chat_id, 'verify_success'))
            try:
                await context.bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
            except Exception as e:
                await query.message.reply_text(f"❌ File error: {e}")
        return

    if data.startswith("del_ch_"):
        ch_id = int(data.replace("del_ch_", ""))
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("DELETE FROM force_channels WHERE id = ? AND owner_id = ?", (ch_id, user_id))
        conn.commit(); conn.close()
        await query.message.edit_text(tr(chat_id, 'channel_deleted'))
        return

    if not is_admin(user_id): return
    
    if data == "adm_add_api":
        context.user_data['admin_state'] = 'add_api'
        await query.message.edit_text(tr(chat_id, 'send_api'))
    elif data == "adm_del_api":
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT id, api_key FROM api_keys"); keys = c.fetchall(); conn.close()
        if not keys: return await query.message.edit_text(tr(chat_id, 'no_api'))
        kb = [[InlineKeyboardButton(f"❌ {k[1][:10]}...", callback_data=f"del_key_{k[0]}")] for k in keys]
        kb.append([InlineKeyboardButton(tr(chat_id, 'btn_back'), callback_data="adm_back")])
        await query.message.edit_text("Select API to delete:", reply_markup=InlineKeyboardMarkup(kb))
    elif data == "adm_view_api":
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT api_key, status FROM api_keys"); keys = c.fetchall(); conn.close()
        if not keys: return await query.message.edit_text(tr(chat_id, 'no_api'))
        txt = "\n".join([f"🔑 <code>{k[0][:15]}...</code> ({k[1]})" for k in keys])
        await query.message.edit_text(f"<b>API Keys:</b>\n\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(tr(chat_id, 'btn_back'), callback_data="adm_back")]]), parse_mode='HTML')
    elif data.startswith("del_key_"):
        key_id = data.split("_")[-1]
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("DELETE FROM api_keys WHERE id = ?", (key_id,)); conn.commit(); conn.close()
        await query.message.edit_text(tr(chat_id, 'api_deleted'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(tr(chat_id, 'btn_back'), callback_data="adm_back")]]))
    elif data.startswith("adm_user_"):
        target_id = int(data.replace("adm_user_", ""))
        await show_admin_user_profile(query, target_id)
    elif data.startswith("adm_ban_") or data.startswith("adm_unban_"):
        target_id = int(data.split("_")[-1])
        is_ban = 1 if "ban_" in data and "unban_" not in data else 0
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (is_ban, target_id))
        conn.commit(); conn.close()
        await query.answer("Status updated!")
        await show_admin_user_profile(query, target_id)

# ==========================================
# 🏃‍♂️ MAIN RUNNER
# ==========================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    # Menus
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_tiktok']}|{TR['bn']['btn_tiktok']})$"), handle_text))
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_img2url']}|{TR['bn']['btn_img2url']})$"), handle_text))
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_voice']}|{TR['bn']['btn_voice']})$"), handle_text))
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_upload']}|{TR['bn']['btn_upload']})$"), handle_text))
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_force_join']}|{TR['bn']['btn_force_join']})$"), handle_text))
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_lang']}|{TR['bn']['btn_lang']})$"), handle_text))
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_owner']}|{TR['bn']['btn_owner']})$"), handle_text))
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_channel']}|{TR['bn']['btn_channel']})$"), handle_text))
    
    # Upload Sub-menu
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_upload_action']}|{TR['bn']['btn_upload_action']}|{TR['en']['btn_my_file']}|{TR['bn']['btn_my_file']})$"), handle_text))

    # Force Join Menus
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_add_channel']}|{TR['bn']['btn_add_channel']}|{TR['en']['btn_del_channel']}|{TR['bn']['btn_del_channel']}|{TR['en']['btn_list_channel']}|{TR['bn']['btn_list_channel']})$"), handle_text))

    # Admin Reply Keyboard
    app.add_handler(MessageHandler(filters.Regex(f"^({TR['en']['btn_stats']}|{TR['bn']['btn_stats']}|{TR['en']['btn_users']}|{TR['bn']['btn_users']}|{TR['en']['btn_broadcast']}|{TR['bn']['btn_broadcast']}|{TR['en']['btn_api']}|{TR['bn']['btn_api']}|{TR['en']['btn_imgbb']}|{TR['bn']['btn_imgbb']}|{TR['en']['btn_set_owner']}|{TR['bn']['btn_set_owner']}|{TR['en']['btn_set_channel']}|{TR['bn']['btn_set_channel']}|{TR['en']['btn_fj_photo']}|{TR['bn']['btn_fj_photo']}|{TR['en']['btn_set_fj_msg_en']}|{TR['bn']['btn_set_fj_msg_en']}|{TR['en']['btn_set_fj_msg_bn']}|{TR['bn']['btn_set_fj_msg_bn']}|{TR['en']['btn_toggle_bot']}|{TR['bn']['btn_toggle_bot']}|{TR['en']['btn_back_user']}|{TR['bn']['btn_back_user']})$"), handle_text))

    # Handlers for media and forwarded messages
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler((filters.VIDEO | filters.Document.ALL | filters.AUDIO | filters.VOICE | filters.VIDEO_NOTE | filters.FORWARDED), handle_media_upload))

    # Catch all text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Inline Callbacks
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(adm_|verify_join_|del_ch_)"))

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()