import os
import threading
import time
import uuid
import yt_dlp
from flask import Flask, request, jsonify

app = Flask(__name__)

# Progress Storage
progress_data = {}
DOWNLOAD_DIR = 'downloads'

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def progress_hook(d, task_id):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%').replace('%', '').strip()
        try:
            progress_val = float(p)
        except:
            progress_val = 0.0
            
        progress_data[task_id].update({
            "status": "downloading",
            "progress": progress_val,
            "speed": d.get('_speed_str', '0 KB/s'),
            "totalSize": d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', 'N/A')),
            "downloadedSize": d.get('_downloaded_bytes_str', '0 MB'),
            "title": progress_data[task_id].get('title', 'Downloading...')
        })
    elif d['status'] == 'finished':
        progress_data[task_id]['status'] = 'finished'
        progress_data[task_id]['progress'] = 100.0

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
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }
    
    if proxy:
        ydl_opts['proxy'] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            progress_data[task_id]['title'] = info.get('title', 'Unknown')
            threading.Thread(target=auto_delete, args=(task_id, filename)).start()
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

@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    return jsonify(progress_data.get(task_id, {"status": "not_found"}))

@app.route('/delete/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    if task_id in progress_data:
        del progress_data[task_id]
    return jsonify({"status": "deleted"})

@app.route('/')
def health():
    return "Do It App Server is running."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
