import os
import threading
import time
import uuid
import requests
import asyncio
from flask import Flask, request, jsonify, send_from_directory
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

app = Flask(__name__)

# Config
DOWNLOAD_DIR = 'downloads'
BASE_URL = "https://do-it-downloader-server.onrender.com"
TELEGRAM_TOKEN = "8946978771:AAHvEzam0danch62xK7SfI0_g1-ff0tiD0U"
PIPED_API = "https://pipedapi.kavin.rocks" # Uses NewPipe Extractor logic

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Progress Storage
progress_data = {}

def auto_delete(task_id, filepath):
    time.sleep(86400) # 24 Hours
    if os.path.exists(filepath):
        os.remove(filepath)
    if task_id in progress_data:
        del progress_data[task_id]

def download_file(url, filepath, task_id):
    try:
        response = requests.get(url, stream=True, timeout=30)
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        progress_data[task_id].update({
                            "status": "downloading",
                            "progress": round(progress, 2),
                            "downloadedSize": f"{round(downloaded / (1024*1024), 2)} MB",
                            "totalSize": f"{round(total_size / (1024*1024), 2)} MB",
                            "speed": "Streaming..."
                        })
        
        progress_data[task_id].update({
            "status": "finished",
            "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{os.path.basename(filepath)}"
        })
        threading.Thread(target=auto_delete, args=(task_id, filepath)).start()
    except Exception as e:
        progress_data[task_id].update({"status": "error", "message": str(e)})

def run_download(url, task_id, proxy=None):
    try:
        # If it's a YouTube link, use Piped API (NewPipe logic) to get direct URL
        if "youtube.com" in url or "youtu.be" in url:
            video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
            api_res = requests.get(f"{PIPED_API}/streams/{video_id}", timeout=20).json()
            
            # Get the best video+audio stream
            stream = api_res['videoStreams'][0] 
            direct_url = stream['url']
            title = api_res.get('title', 'YouTube Video')
            filename = f"{task_id}.mp4"
        else:
            # Direct link
            direct_url = url
            title = url.split("/")[-1] or "file"
            filename = f"{task_id}_{title}"

        progress_data[task_id]['title'] = title
        progress_data[task_id]['filename'] = filename
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        download_file(direct_url, filepath, task_id)
        
    except Exception as e:
        progress_data[task_id].update({"status": "error", "message": f"Extraction failed: {str(e)}"})

# Telegram Bot Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Jay Dwarkadhish 🌹")

async def handle_telegram_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    task_id = str(uuid.uuid4())
    
    if text and (text.startswith("http://") or text.startswith("https://")):
        progress_data[task_id] = {
            "taskId": task_id, "status": "starting", "progress": 0.0,
            "speed": "Connecting...", "totalSize": "N/A", "downloadedSize": "0 MB",
            "title": "Link detected..."
        }
        threading.Thread(target=run_download, args=(text, task_id)).start()
        await update.message.reply_text(f"Download started! Task ID: {task_id}\nTrack in app.")
    
    elif update.message.document or update.message.video:
        file = await update.message.effective_attachment.get_file()
        filename = getattr(update.message.effective_attachment, 'file_name', f"{uuid.uuid4()}.file")
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        progress_data[task_id] = {
            "taskId": task_id, "status": "downloading", "progress": 0.0,
            "speed": "Telegram internal", "totalSize": "N/A", "downloadedSize": "Processing",
            "title": filename, "filename": filename
        }
        
        await file.download_to_drive(filepath)
        progress_data[task_id].update({
            "status": "finished", "progress": 100.0,
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
    task_id = str(uuid.uuid4())
    progress_data[task_id] = {
        "taskId": task_id, "status": "starting", "progress": 0.0,
        "speed": "0 KB/s", "totalSize": "N/A", "downloadedSize": "0 MB",
        "title": "Initializing..."
    }
    threading.Thread(target=run_download, args=(url, task_id)).start()
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
            if os.path.exists(path): os.remove(path)
        del progress_data[task_id]
    return jsonify({"status": "deleted"})

@app.route('/')
def health():
    return "Do It App Server (NewPipe Logic) is running."

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
