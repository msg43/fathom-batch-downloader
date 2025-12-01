"""
Fathom Batch Downloader - Flask Application
A web app to batch download videos and data from Fathom.video
"""

import os
import json
import time
import queue
import threading
from flask import Flask, render_template, request, jsonify, Response
from fathom_api import FathomAPI
from video_extractor import VideoExtractor
from download_organizer import DownloadOrganizer

app = Flask(__name__)

# Delay between processing each meeting (seconds) - helps avoid rate limits
DOWNLOAD_DELAY = 1  # seconds between meetings
VIDEO_DOWNLOAD_DELAY = 3  # extra seconds after video downloads (to be nice to servers)

# Global progress queue for SSE
progress_queues = {}

# Config file path
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
DEFAULT_DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), 'downloads')


def get_downloads_dir():
    """Get the configured downloads directory, or default if not set"""
    cfg = load_config()
    download_dir = cfg.get('download_dir', '').strip()
    
    if download_dir:
        # Expand ~ to home directory
        download_dir = os.path.expanduser(download_dir)
        # Make absolute if relative
        if not os.path.isabs(download_dir):
            download_dir = os.path.abspath(download_dir)
        return download_dir
    
    return DEFAULT_DOWNLOADS_DIR


def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_config(config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')


@app.route('/api/config', methods=['GET', 'POST'])
def config():
    """Get or save configuration"""
    if request.method == 'GET':
        cfg = load_config()
        # Don't send password back to client
        if 'fathom_password' in cfg:
            cfg['fathom_password'] = '••••••••' if cfg['fathom_password'] else ''
        # Check if Google session exists
        session_file = os.path.join(os.path.dirname(__file__), '.browser_session', 'state.json')
        cfg['google_authenticated'] = os.path.exists(session_file)
        return jsonify(cfg)
    
    elif request.method == 'POST':
        data = request.json
        cfg = load_config()
        
        # Update config
        if 'api_key' in data:
            cfg['api_key'] = data['api_key']
        if 'download_dir' in data:
            cfg['download_dir'] = data['download_dir']
        if 'fathom_email' in data:
            cfg['fathom_email'] = data['fathom_email']
        if 'fathom_password' in data and data['fathom_password'] != '••••••••':
            cfg['fathom_password'] = data['fathom_password']
        
        # Validate API key
        if cfg.get('api_key'):
            api = FathomAPI(cfg['api_key'])
            is_valid, error = api.validate_key()
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        save_config(cfg)
        return jsonify({'success': True})


@app.route('/api/google-auth', methods=['POST'])
def google_auth():
    """Initiate Google OAuth authentication via browser"""
    try:
        extractor = VideoExtractor()
        success, message = extractor.authenticate_with_google()
        extractor.close()
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/meetings')
def get_meetings():
    """Fetch meetings list from Fathom API"""
    cfg = load_config()
    if not cfg.get('api_key'):
        return jsonify({'error': 'API key not configured'}), 400
    
    api = FathomAPI(cfg['api_key'])
    meetings, error = api.get_meetings()
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({'meetings': meetings})


@app.route('/api/download', methods=['POST'])
def start_download():
    """Start downloading selected meetings"""
    data = request.json
    meeting_ids = data.get('meeting_ids', [])
    options = data.get('options', {})
    
    if not meeting_ids:
        return jsonify({'error': 'No meetings selected'}), 400
    
    cfg = load_config()
    if not cfg.get('api_key'):
        return jsonify({'error': 'API key not configured'}), 400
    
    # Create a unique session ID for progress tracking
    import uuid
    session_id = str(uuid.uuid4())
    progress_queues[session_id] = queue.Queue()
    
    # Start download in background thread
    thread = threading.Thread(
        target=download_worker,
        args=(session_id, meeting_ids, options, cfg)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'session_id': session_id})


def download_worker(session_id, meeting_ids, options, cfg):
    """Background worker to download meetings"""
    q = progress_queues.get(session_id)
    if not q:
        return
    
    try:
        downloads_dir = get_downloads_dir()
        os.makedirs(downloads_dir, exist_ok=True)
        
        api = FathomAPI(cfg['api_key'])
        organizer = DownloadOrganizer(downloads_dir)
        video_extractor = None
        
        # Initialize video extractor if needed
        if options.get('video'):
            # Check if Google session exists
            session_file = os.path.join(os.path.dirname(__file__), '.browser_session', 'state.json')
            if not os.path.exists(session_file):
                q.put({'type': 'error', 'message': 'Google authentication required for video download. Click "Sign in with Google" first.'})
                return
            video_extractor = VideoExtractor()
        
        total = len(meeting_ids)
        
        # Warn user if downloading many videos
        if options.get('video') and total > 5:
            q.put({
                'type': 'status',
                'message': f'Downloading {total} meetings with videos. This may take a while (videos are downloaded sequentially with delays to avoid rate limits).'
            })
        
        for i, meeting_id in enumerate(meeting_ids):
            try:
                # Get meeting details
                q.put({
                    'type': 'progress',
                    'current': i + 1,
                    'total': total,
                    'message': f'Processing meeting {i + 1} of {total}...'
                })
                
                meeting, error = api.get_meeting_details(meeting_id, options)
                if error:
                    q.put({'type': 'warning', 'message': f'Error fetching meeting {meeting_id}: {error}'})
                    continue
                
                # Create folder for this meeting
                folder_path = organizer.create_meeting_folder(meeting)
                
                # Save metadata
                organizer.save_metadata(folder_path, meeting)
                
                # Save transcript
                if options.get('transcript') and meeting.get('transcript'):
                    q.put({'type': 'status', 'message': f'Saving transcript...'})
                    organizer.save_transcript(folder_path, meeting['transcript'])
                
                # Save summary
                if options.get('summary') and meeting.get('default_summary'):
                    q.put({'type': 'status', 'message': f'Saving summary...'})
                    organizer.save_summary(folder_path, meeting['default_summary'])
                
                # Save action items
                if options.get('action_items') and meeting.get('action_items'):
                    q.put({'type': 'status', 'message': f'Saving action items...'})
                    organizer.save_action_items(folder_path, meeting['action_items'])
                
                # Download video
                if options.get('video') and video_extractor:
                    q.put({'type': 'status', 'message': f'Downloading video (this may take a few minutes)...'})
                    video_url = meeting.get('url')
                    if video_url:
                        success, msg = video_extractor.download_video(video_url, folder_path)
                        if not success:
                            q.put({'type': 'warning', 'message': f'Video download failed: {msg}'})
                        else:
                            q.put({'type': 'status', 'message': f'Video downloaded successfully'})
                        # Extra delay after video downloads to avoid overloading servers
                        time.sleep(VIDEO_DOWNLOAD_DELAY)
                
                # Small delay between meetings to be nice to Fathom's servers
                if i < total - 1:  # Don't delay after the last meeting
                    time.sleep(DOWNLOAD_DELAY)
                
            except Exception as e:
                q.put({'type': 'warning', 'message': f'Error processing meeting: {str(e)}'})
        
        # Cleanup
        if video_extractor:
            video_extractor.close()
        
        q.put({
            'type': 'complete',
            'message': f'Download complete! {total} meetings processed.',
            'folder': downloads_dir
        })
        
    except Exception as e:
        q.put({'type': 'error', 'message': str(e)})
    
    finally:
        # Keep queue alive for a bit to ensure client gets final message
        import time
        time.sleep(2)
        if session_id in progress_queues:
            del progress_queues[session_id]


@app.route('/api/progress/<session_id>')
def progress(session_id):
    """Server-Sent Events endpoint for download progress"""
    def generate():
        q = progress_queues.get(session_id)
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid session'})}\n\n"
            return
        
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get('type') in ('complete', 'error'):
                    break
            except queue.Empty:
                # Send keepalive
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


if __name__ == '__main__':
    # Ensure default downloads directory exists
    os.makedirs(DEFAULT_DOWNLOADS_DIR, exist_ok=True)
    
    print("\n" + "="*50)
    print("Fathom Batch Downloader")
    print("="*50)
    print(f"Open http://localhost:5000 in your browser")
    print("="*50 + "\n")
    
    app.run(debug=True, port=5000, threaded=True)

