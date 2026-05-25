from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def health():
    return "Server is running (All features removed)."

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
