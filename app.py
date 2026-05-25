import os
import threading
import time
import uuid
import yt_dlp
import asyncio
from flask import Flask, request, jsonify, send_from_directory
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

app = Flask(__name__)

# Config
DOWNLOAD_DIR = 'downloads'
BASE_URL = "https://do-it-downloader-server.onrender.com"
TELEGRAM_TOKEN = "8946978771:AAHvEzam0danch62xK7SfI0_g1-ff0tiD0U"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Progress Storage
progress_data = {}

# Free Proxy List (Fallback)
FREE_PROXIES = [
    "http://103.152.112.162:80",
    "http://103.14.135.105:80"
]

def format_bytes(size):
    # Convert bytes to human readable format
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

def progress_hook(d, task_id):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%').replace('%', '').strip()
        try: progress_val = float(p)
        except: progress_val = 0.0
        
        # Real speed and size calculation
        speed = d.get('_speed_str', '0 KB/s')
        total = d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', 'N/A'))
        downloaded = d.get('_downloaded_bytes_str', '0 MB')
            
        progress_data[task_id].update({
            "status": "downloading",
            "progress": progress_val,
            "speed": speed,
            "totalSize": total,
            "downloadedSize": downloaded,
        })
    elif d['status'] == 'finished':
        filename = os.path.basename(d['filename'])
        progress_data[task_id].update({
            "status": "finished",
            "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{filename}",
            "filename": filename
        })

def auto_delete(task_id, filepath):
    time.sleep(86400) # 24 Hours
    if os.path.exists(filepath):
        try: os.remove(filepath)
        except: pass
    if task_id in progress_data:
        try: del progress_data[task_id]
        except: pass

def run_download(url, task_id, proxy=None):
    active_proxy = proxy if proxy else None
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }
    if active_proxy:
        ydl_opts['proxy'] = active_proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = os.path.basename(ydl.prepare_filename(info))
            progress_data[task_id]['title'] = info.get('title', 'File')
            progress_data[task_id]['filename'] = filename
            threading.Thread(target=auto_delete, args=(task_id, os.path.join(DOWNLOAD_DIR, filename))).start()
    except Exception as e:
        progress_data[task_id]['status'] = 'error'
        progress_data[task_id]['message'] = str(e)

# Telegram Bot Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"Download started! Track in Do It App.\nTask ID: {task_id}")
    
    elif update.message.document or update.message.video:
        file = await update.message.effective_attachment.get_file()
        filename = update.message.effective_attachment.file_name or f"{uuid.uuid4()}.file"
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        progress_data[task_id] = {
            "taskId": task_id, "status": "downloading", "progress": 0.0,
            "speed": "Internal", "totalSize": "N/A", "downloadedSize": "Saving...",
            "title": filename, "filename": filename
        }
        
        await file.download_to_drive(filepath)
        progress_data[task_id].update({
            "status": "finished",
            "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{filename}"
        })
        
        await update.message.reply_text(f"File saved!\nLink: {BASE_URL}/files/{filename}")
        threading.Thread(target=auto_delete, args=(task_id, filepath)).start()

def run_bot():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_telegram_message))
    application.run_polling(stop_signals=None)

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
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
        del progress_data[task_id]
    return jsonify({"status": "deleted"})

@app.route('/')
def health():
    return "Do It App Server is running."

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
