import os
import threading
import time
import uuid
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# Config
DOWNLOAD_DIR = 'downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Progress Storage
progress_data = {}

def download_file(url, task_id):
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        filename = url.split('/')[-1] or f"file_{task_id}"
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        
        progress_data[task_id].update({
            "status": "downloading",
            "title": filename,
            "totalSize": f"{total_size / (1024*1024):.2f} MB" if total_size > 0 else "Unknown"
        })

        downloaded = 0
        start_time = time.time()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Update progress every 1 second to avoid overhead
                    if time.time() - start_time > 1:
                        elapsed = time.time() - (start_time - 1) # approximate
                        speed = len(chunk) / 1024 # very rough
                        
                        p = (downloaded / total_size * 100) if total_size > 0 else 0
                        progress_data[task_id].update({
                            "progress": round(p, 2),
                            "downloadedSize": f"{downloaded / (1024*1024):.2f} MB",
                            "speed": f"{speed:.2f} KB/s"
                        })
                        start_time = time.time()

        progress_data[task_id].update({
            "status": "finished",
            "progress": 100.0,
            "downloadedSize": f"{downloaded / (1024*1024):.2f} MB"
        })
        
    except Exception as e:
        progress_data[task_id].update({
            "status": "error",
            "message": str(e)
        })

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
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
    threading.Thread(target=download_file, args=(url, task_id)).start()
    return jsonify({"status": "ok", "taskId": task_id})

@app.route('/tasks', methods=['GET'])
def list_tasks():
    return jsonify(list(progress_data.values()))

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
    return "Do It App Server is running (Clean Version)."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
