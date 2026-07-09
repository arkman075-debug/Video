import os
import yt_dlp
from flask import Flask, render_template, request, send_file, jsonify, after_this_request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
DOWNLOAD_FOLDER = 'downloads'
COOKIE_FILE = 'cookies.txt'  # Ensure this file exists in your project root

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# yt-dlp global configuration
# Includes the cookie file and anti-bot bypass arguments
YDL_OPTIONS = {
    'quiet': True,
    'noplaylist': True,
    'cookiefile': COOKIE_FILE,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web_embedded'],
            'player_skip': ['webpage', 'configs'],
        }
    }
}

def get_video_id(url):
    """Extracts the video ID for the frontend preview player."""
    if 'v=' in url: return url.split('v=')[1].split('&')[0]
    elif 'be/' in url: return url.split('be/')[1].split('?')[0]
    elif 'shorts/' in url: return url.split('shorts/')[1].split('?')[0]
    return None

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    if not os.path.exists(COOKIE_FILE):
        return jsonify({"error": "Server Error: cookies.txt is missing. Please upload it."}), 500
    
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'channel': info.get('uploader'),
                'duration': info.get('duration_string'),
                'video_id': get_video_id(url),
                'views': f"{info.get('view_count', 0):,}"
            })
    except Exception as e:
        error_msg = str(e)
        if "confirm you're not a bot" in error_msg:
            return jsonify({"error": "YouTube blocked the request. Update cookies.txt"}), 403
        return jsonify({"error": error_msg}), 500

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    video_id = get_video_id(url)
    if not video_id:
        video_id = "video_file"

    # Define the temporary path on the server
    temp_filename = f"{video_id}.mp4"
    file_path = os.path.join(DOWNLOAD_FOLDER, temp_filename)
    
    # Custom options for the actual download phase
    dl_opts = {
        **YDL_OPTIONS,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': file_path,
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            # Clean title for the user's download filename
            safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '.', '_')]).rstrip()

        # Cleanup: This ensures the file is deleted from the Render server after being sent
        @after_this_request
        def remove_file(response):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                app.logger.error(f"Error deleting temporary file: {e}")
            return response

        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"{safe_title}.mp4",
            mimetype='video/mp4'
        )

    except Exception as e:
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

if __name__ == '__main__':
    # Use the PORT environment variable provided by Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
