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

# Task Storage (Persistent during session)
tasks = {}

def progress_hook(d, task_id):
    if task_id not in tasks: return
    
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%').replace('%', '').strip()
        try: progress_val = float(p)
        except: progress_val = 0.0
            
        tasks[task_id].update({
            "status": "downloading",
            "progress": progress_val,
            "speed": d.get('_speed_str', '0 KB/s'),
            "totalSize": d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', 'N/A')),
            "downloadedSize": d.get('_downloaded_bytes_str', '0 MB'),
        })
    elif d['status'] == 'finished':
        tasks[task_id].update({
            "status": "finished",
            "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{tasks[task_id].get('filename', 'file')}"
        })

def auto_delete(task_id, filepath):
    time.sleep(86400) # 24 Hours
    if os.path.exists(filepath):
        try: os.remove(filepath)
        except: pass
    if task_id in tasks:
        del tasks[task_id]

def run_download(url, task_id, proxy=None):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'nocheckcertificate': True,
    }
    if proxy:
        ydl_opts['proxy'] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = os.path.basename(ydl.prepare_filename(info))
            tasks[task_id].update({
                "title": info.get('title', 'Unknown'),
                "filename": filename,
                "downloadUrl": f"{BASE_URL}/files/{filename}"
            })
            threading.Thread(target=auto_delete, args=(task_id, os.path.join(DOWNLOAD_DIR, filename))).start()
    except Exception as e:
        if task_id in tasks:
            tasks[task_id].update({"status": "error", "message": str(e)})

# Telegram Bot Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Jay Dwarkadhish 🌹")

async def handle_telegram_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    task_id = str(uuid.uuid4())
    
    if text and (text.startswith("http://") or text.startswith("https://")):
        tasks[task_id] = {
            "taskId": task_id, "status": "starting", "progress": 0.0,
            "speed": "0 KB/s", "totalSize": "N/A", "downloadedSize": "0 MB",
            "title": "Analyzing URL..."
        }
        threading.Thread(target=run_download, args=(text, task_id)).start()
        await update.message.reply_text(f"Download started! Track in Do It App.\nTask ID: {task_id}")
    
    elif update.message.document or update.message.video:
        file = await update.message.effective_attachment.get_file()
        filename = getattr(update.message.effective_attachment, 'file_name', f"{uuid.uuid4()}.file")
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        tasks[task_id] = {
            "taskId": task_id, "status": "downloading", "progress": 50.0,
            "speed": "Telegram speed", "totalSize": "N/A", "downloadedSize": "Processing",
            "title": filename, "filename": filename
        }
        
        await file.download_to_drive(filepath)
        tasks[task_id].update({
            "status": "finished",
            "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{filename}"
        })
        await update.message.reply_text(f"Success! Link: {BASE_URL}/files/{filename}")
        threading.Thread(target=auto_delete, args=(task_id, filepath)).start()

def run_bot():
    app_tg = Application.builder().token(TELEGRAM_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_command))
    app_tg.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_telegram_message))
    app_tg.run_polling(stop_signals=None)

@app.route('/download', methods=['POST'])
def download_api():
    data = request.json
    url = data.get('url')
    proxy = data.get('proxy')
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "taskId": task_id, "status": "starting", "progress": 0.0,
        "speed": "0 KB/s", "totalSize": "N/A", "downloadedSize": "0 MB",
        "title": "Analyzing..."
    }
    threading.Thread(target=run_download, args=(url, task_id, proxy)).start()
    return jsonify({"status": "ok", "taskId": task_id})

@app.route('/tasks', methods=['GET'])
def list_tasks():
    return jsonify(list(tasks.values()))

@app.route('/files/<path:filename>')
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename)

@app.route('/delete/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    if task_id in tasks:
        filename = tasks[task_id].get('filename')
        if filename:
            path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
        del tasks[task_id]
        return jsonify({"status": "deleted"})
    return jsonify({"status": "not_found"}), 404

@app.route('/')
def health():
    return "Do It App Server is running."

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
