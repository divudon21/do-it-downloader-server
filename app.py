import os
import threading
import time
import uuid
import yt_dlp
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# Config
DOWNLOAD_DIR = 'downloads'
BASE_URL = "https://do-it-downloader-server.onrender.com"

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
            "progress": 100.0,
            "downloadUrl": f"{BASE_URL}/files/{progress_data[task_id]['filename']}"
        })

def auto_delete(task_id, filepath):
    time.sleep(86400) # 24 Hours
    if os.path.exists(filepath):
        os.remove(filepath)
    if task_id in progress_data:
        del progress_data[task_id]

def run_download(url, task_id, proxy=None):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }
    if proxy:
        ydl_opts['proxy'] = proxy

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

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    proxy = data.get('proxy')
    task_id = str(uuid.uuid4())
    progress_data[task_id] = {
        "taskId": task_id,
        "status": "starting",
        "progress": 0.0,
        "speed": "0 KB/s",
        "totalSize": "N/A",
        "downloadedSize": "0 MB",
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
            if os.path.exists(path): os.remove(path)
        del progress_data[task_id]
    return jsonify({"status": "deleted"})

@app.route('/')
def health():
    return "Do It App Server is running."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
