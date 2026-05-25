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
stop_flag = False

# Free Proxy List
FREE_PROXIES = [
    "http://103.152.112.162:80",
    "http://103.14.135.105:80",
    "http://154.236.177.106:1994"
]

def progress_hook(d, task_id):
    global stop_flag
    if stop_flag:
        raise Exception("Task stopped by user")
        
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
            "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{progress_data[task_id]['filename']}"
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
    global stop_flag
    # Use provided proxy or fallback to a free one if requested
    active_proxy = proxy if proxy else (FREE_PROXIES[0] if url.startswith("http") else None)
    
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
        if task_id in progress_data:
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
        await update.message.reply_text(f"Download started! Task ID: {task_id}\nTrack in app or wait here.")
    
    elif update.message.document or update.message.video:
        file = await update.message.effective_attachment.get_file()
        filename = update.message.effective_attachment.file_name or f"{uuid.uuid4()}.file"
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        progress_data[task_id] = {
            "taskId": task_id, "status": "downloading", "progress": 0.0,
            "speed": "Telegram internal", "totalSize": "N/A", "downloadedSize": "Processing",
            "title": filename, "filename": filename
        }
        
        await file.download_to_drive(filepath)
        progress_data[task_id]['status'] = 'finished'
        progress_data[task_id]['progress'] = 100.0
        progress_data[task_id]['downloadUrl'] = f"{BASE_URL}/files/{filename}"
        
        await update.message.reply_text(f"File saved to server!\nLink: {BASE_URL}/files/{filename}")
        threading.Thread(target=auto_delete, args=(task_id, filepath)).start()

def run_bot():
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_telegram_message))
        application.run_polling(stop_signals=None)
    except Exception as e:
        print(f"Bot Error: {e}")

@app.route('/download', methods=['POST'])
def download():
    global stop_flag
    stop_flag = False
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

@app.route('/stop_all', methods=['POST'])
def stop_all():
    global stop_flag
    stop_flag = True
    return jsonify({"status": "stopping_all"})

@app.route('/delete_all', methods=['DELETE'])
def delete_all():
    global progress_data
    for task_id in list(progress_data.keys()):
        filename = progress_data[task_id].get('filename')
        if filename:
            path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
    progress_data.clear()
    # Also clear directory just in case
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    return jsonify({"status": "all_deleted"})

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
    return "Do It App Server is running with Telegram Bot."

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
