from flask import Flask, request, jsonify
import yt_dlp
import os
import threading

app = Flask(__name__)

# Configuration
DOWNLOAD_DIR = 'downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def download_video(url):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Successfully downloaded: {url}")
    except Exception as e:
        print(f"Error downloading {url}: {str(e)}")

@app.route('/download', methods=['POST'])
def trigger_download():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"status": "error", "message": "No URL provided"}), 400
    
    url = data['url']
    
    # Start download in a background thread to avoid blocking the request
    thread = threading.Thread(target=download_video, args=(url,))
    thread.start()
    
    return jsonify({
        "status": "success",
        "message": f"Download started for {url}",
        "taskId": "async-task"
    })

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "service": "Do It Downloader"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
