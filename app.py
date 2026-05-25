import os
import threading
import time
import uuid
import yt_dlp
import asyncio
import logging
from flask import Flask, request, jsonify, send_from_directory
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Config
DOWNLOAD_DIR = 'downloads'
BASE_URL = "https://do-it-downloader-server.onrender.com"
TELEGRAM_TOKEN = "8946978771:AAHvEzam0danch62xK7SfI0_g1-ff0tiD0U"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Progress Storage
progress_data = {}

def progress_hook(d, task_id):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%').replace('%', '').strip()
        try: progress_val = float(p)
        except: progress_val = 0.0
            
        progress_data[task_id].update({
            "status": "downloading",
            "progress": progress_val,
            "speed": d.get('_speed_str', '0 KB/s'),
            "totalSize": d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', 'N/A')),
            "downloadedSize": d.get('_downloaded_bytes_str', '0 MB'),
        })
    elif d['status'] == 'finished':
        progress_data[task_id].update({
            "status": "finished",
            "progress": 100.0
        })

def auto_delete(task_id, filepath):
    time.sleep(86400) # 24 Hours
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
        if task_id in progress_data:
            del progress_data[task_id]
    except: pass

def run_download(url, task_id, proxy=None):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'web']}},
    }
    
    if proxy:
        ydl_opts['proxy'] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First extract info
            info = ydl.extract_info(url, download=False)
            progress_data[task_id]['title'] = info.get('title', 'Unknown Title')
            
            # Then download
            ydl.download([url])
            
            filename = os.path.basename(ydl.prepare_filename(info))
            progress_data[task_id]['filename'] = filename
            progress_data[task_id]['downloadUrl'] = f"{BASE_URL}/files/{filename}"
            
            threading.Thread(target=auto_delete, args=(task_id, os.path.join(DOWNLOAD_DIR, filename))).start()
    except Exception as e:
        logger.error(f"Download Error: {str(e)}")
        progress_data[task_id]['status'] = 'error'
        progress_data[task_id]['message'] = str(e)

# Telegram Bot Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Start command received")
    await update.message.reply_text("Jay Dwarkadhish 🌹")

async def handle_telegram_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    task_id = str(uuid.uuid4())
    
    if text and (text.startswith("http://") or text.startswith("https://")):
        progress_data[task_id] = {
            "taskId": task_id, "status": "starting", "progress": 0.0,
            "speed": "0 KB/s", "totalSize": "N/A", "downloadedSize": "0 MB",
            "title": "Telegram Link..."
        }
        threading.Thread(target=run_download, args=(text, task_id)).start()
        await update.message.reply_text(f"Download started! 🚀\nTask ID: {task_id}\nCheck progress in 'Do It' app.")
    
    elif update.message.document or update.message.video:
        attachment = update.message.document or update.message.video
        file = await attachment.get_file()
        filename = getattr(attachment, 'file_name', f"{uuid.uuid4()}.mp4")
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        progress_data[task_id] = {
            "taskId": task_id, "status": "downloading", "progress": 50.0,
            "speed": "Telegram", "totalSize": "N/A", "downloadedSize": "Processing",
            "title": filename, "filename": filename
        }
        
        await file.download_to_drive(filepath)
        progress_data[task_id].update({
            "status": "finished", "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{filename}"
        })
        
        await update.message.reply_text(f"✅ File saved to server!\nLink: {BASE_URL}/files/{filename}")
        threading.Thread(target=auto_delete, args=(task_id, filepath)).start()

def run_bot():
    logger.info("Starting Telegram Bot...")
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_telegram_message))
        
        # This is the correct way to run polling in a thread without signal conflicts
        application.run_polling(stop_signals=None)
    except Exception as e:
        logger.error(f"Bot Error: {str(e)}")

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    proxy = data.get('proxy')
    task_id = str(uuid.uuid4())
    progress_data[task_id] = {
        "taskId": task_id, "status": "starting", "progress": 0.0,
        "speed": "0 KB/s", "totalSize": "N/A", "downloadedSize": "0 MB",
        "title": "Initializing..."
    }
    threading.Thread(target=run_download, args=(url, task_id, proxy)).start()
    return jsonify({"status": "ok", "taskId": task_id})

@app.route('/tasks', methods=['GET'])
def list_tasks():
    return jsonify(list(progress_data.values()))

@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    return jsonify(progress_data.get(task_id, {"status": "not_found"}))

@app.route('/files/<path:filename>')
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename)

@app.route('/delete/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    if task_id in progress_data:
        filename = progress_data[task_id].get('filename')
        if filename:
            path = os.path.join(DOWNLOAD_DIR, filename)
            try:
                if os.path.exists(path): os.remove(path)
            except: pass
        del progress_data[task_id]
    return jsonify({"status": "deleted"})

@app.route('/')
def health():
    return "Do It App Server is running with Telegram Bot."

if __name__ == '__main__':
    # Start bot in a daemon thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
