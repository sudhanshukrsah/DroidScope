from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import asyncio
import json
import os
import uuid
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from llama_index.llms.openai_like import OpenAILike
import queue
import threading
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
from database import (
    get_all_settings, set_setting, get_exploration, get_exploration_by_id,
    get_library, get_library_count, get_comparison_data, save_comparison_snapshot,
    get_comparison_snapshots, get_result, get_latest_result, get_stages
)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'droidrun-ux-tester-secret'

# Global queues for SSE
progress_queue = queue.Queue()
logs_queue = queue.Queue()
stage_queue = queue.Queue()

# Global flag to signal agent stop
agent_stop_flag = threading.Event()
current_exploration_thread = None
current_request_id = None

class LogCapture:
    """Captures stdout/stderr - accumulates for 5 seconds then sends as batch"""
    def __init__(self, log_type='info'):
        self.log_type = log_type
        self.text_buffer = ""  # Accumulate all text
        self.last_flush_time = datetime.now()
        self.flush_interval = 5  # seconds - accumulate for 5 seconds
        self.original_stdout = sys.__stdout__
        self.lock = threading.Lock()
        self.running = True
        
        # Start background flush thread
        self.flush_thread = threading.Thread(target=self._auto_flush_loop, daemon=True)
        self.flush_thread.start()
    
    def _auto_flush_loop(self):
        """Flush buffer every 5 seconds"""
        while self.running:
            threading.Event().wait(self.flush_interval)
            with self.lock:
                if self.text_buffer.strip():
                    self._send_buffer()
    
    def _send_buffer(self):
        """Send accumulated buffer - must be called with lock held"""
        if self.text_buffer.strip():
            log_entry = {
                'message': self.text_buffer.strip(),
                'type': self.log_type,
                'timestamp': datetime.now().strftime("%H:%M:%S")
            }
            logs_queue.put(log_entry)
            
            # Server console log
            if self.original_stdout:
                self.original_stdout.write(f"[BATCH-{self.log_type.upper()}] {self.text_buffer}")
                self.original_stdout.flush()
            
            self.text_buffer = ""
            self.last_flush_time = datetime.now()
    
    def write(self, message):
        with self.lock:
            self.text_buffer += message
        return len(message)
    
    def flush(self):
        with self.lock:
            self._send_buffer()
        if self.original_stdout:
            self.original_stdout.flush()
    
    def isatty(self):
        return False
    
    def close(self):
        """Flush and stop"""
        self.running = False
        with self.lock:
            self._send_buffer()

def send_log(message, log_type='info'):
    """Send log message directly to SSE queue"""
    log_entry = {
        'message': message,
        'type': log_type,
        'timestamp': datetime.now().strftime("%H:%M:%S")
    }
    logs_queue.put(log_entry)
    
    # Log to server stdout only if we have the original reference
    if hasattr(sys, '__stdout__') and sys.__stdout__ is not None:
        sys.__stdout__.write(f"[LOG-SEND] [{log_type.upper()}] {message}\n")
        sys.__stdout__.flush()

def send_progress(message, percentage=0):
    """Send progress update to SSE queue"""
    progress_queue.put({
        'message': message,
        'percentage': percentage,
        'timestamp': datetime.now().isoformat()
    })


def send_stage_update(stage_num, status, message=''):
    """Send stage status update to SSE queue"""
    stage_queue.put({
        'stage': stage_num,
        'status': status,
        'message': message,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/')
def index():
    """Render main frontend page"""
    return render_template('index_new.html')


@app.route('/api/test-log', methods=['POST'])
def test_log():
    """Test endpoint to verify logging works"""
    send_log("🧪 Test log message", 'info')
    send_log("✅ Test success message", 'success')
    send_log("⚠️ Test warning message", 'warning')
    send_log("❌ Test error message", 'error')
    return jsonify({'status': 'Test logs sent'})


@app.route('/api/run-test', methods=['POST'])
def run_test():
    """Start UX exploration test with staged execution"""
    global current_exploration_thread, agent_stop_flag, current_request_id, log_buffer
    
    data = request.json
    app_name = data.get('app_name', 'Unknown App')
    category = data.get('category', 'General')
    persona = data.get('persona', 'UX Designer')
    custom_navigation = data.get('custom_navigation', '')
    max_depth = int(data.get('max_depth', 6))
    save_to_memory = data.get('save_to_memory', True)
    
    # Generate unique request ID
    request_id = str(uuid.uuid4())[:8]
    current_request_id = request_id
    
    # Clear previous queues and log buffer
    while not progress_queue.empty():
        progress_queue.get()
    while not logs_queue.empty():
        logs_queue.get()
    while not stage_queue.empty():
        stage_queue.get()
    
    # Clear stop flag
    agent_stop_flag.clear()
    
    # Start async test in background thread
    thread = threading.Thread(
        target=run_staged_exploration_async,
        args=(request_id, app_name, category, persona, custom_navigation, max_depth, save_to_memory)
    )
    thread.daemon = True
    thread.start()
    
    # Store reference to current thread
    current_exploration_thread = thread
    
    return jsonify({
        'status': 'started',
        'request_id': request_id,
        'app_name': app_name,
        'category': category,
        'persona': persona,
        'max_depth': max_depth
    })


@app.route('/api/progress')
def progress():
    """SSE endpoint for progress updates"""
    def generate():
        while True:
            try:
                # Get progress update from queue
                update = progress_queue.get(timeout=30)
                yield f"data: {json.dumps(update)}\n\n"
                
                # If analysis is complete, stop streaming
                if update.get('percentage') >= 100:
                    break
            except queue.Empty:
                # Send keepalive
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/stages')
def stages():
    """SSE endpoint for stage updates"""
    def generate():
        while True:
            try:
                update = stage_queue.get(timeout=30)
                yield f"data: {json.dumps(update)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/logs')
def logs():
    """SSE endpoint for execution logs"""
    def generate():
        # Log connection establishment
        if sys.__stdout__ is not None:
            sys.__stdout__.write("[SSE] Logs stream connected\n")
            sys.__stdout__.flush()
        
        while True:
            try:
                log = logs_queue.get(timeout=30)
                
                # Debug: show what we're sending
                if sys.__stdout__ is not None:
                    sys.__stdout__.write(f"[SSE] Sending log: {log.get('message', '')[:50]}...\n")
                    sys.__stdout__.flush()
                
                yield f"data: {json.dumps(log)}\n\n"
                
                # Only stop if we see the FINAL exploration completion message
                # Don't stop for individual stage completions
                if log.get('type') == 'success':
                    message = log.get('message', '').lower()
                    # Match only the final completion messages
                    if 'exploration completed successfully' in message or 'test completed successfully' in message:
                        if sys.__stdout__ is not None:
                            sys.__stdout__.write("[SSE] Final completion detected, closing stream\n")
                            sys.__stdout__.flush()
                        return
            except queue.Empty:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )



@app.route('/api/results')
def get_results():
    """Get latest analysis results from database ONLY"""
    try:
        # ONLY get from database - no file fallback
        result = get_latest_result()
        if result:
            print(f"[API /api/results] Returning exploration_id: {result.get('exploration_id', 'unknown')}")
            return jsonify(result['analysis_json'])
        
        print("[API /api/results] No results in database")
        return jsonify({'error': 'No results available yet'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/results/<int:exploration_id>')
def get_exploration_results(exploration_id):
    """Get results for specific exploration"""
    try:
        print(f"[API] Fetching results for exploration_id: {exploration_id}")
        result = get_result(exploration_id)
        if result:
            print(f"[API] Found results for exploration_id: {exploration_id}")
            return jsonify(result['analysis_json'])
        print(f"[API] No results found for exploration_id: {exploration_id}")
        return jsonify({'error': 'No results found'}), 404
    except Exception as e:
        print(f"[API] Error fetching results for exploration_id {exploration_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/library')
def library():
    """Get exploration library"""
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        category = request.args.get('category')
        persona = request.args.get('persona')
        
        items = get_library(limit, offset, category, persona)
        total = get_library_count(category, persona)
        
        return jsonify({
            'items': items,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/compare')
def compare():
    """Get comparison data with detailed metrics"""
    category = request.args.get('category')
    persona = request.args.get('persona')
    
    if not category or not persona:
        return jsonify({'error': 'Category and persona required'}), 400
    
    try:
        data = get_comparison_data(category, persona)
        
        # Extract detailed comparison data
        items = []
        all_features = set()
        
        for item in data:
            analysis = item.get('analysis_json')
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            
            # Extract features from different sources
            features = set()
            if analysis:
                # From core flows
                if 'app_metadata' in analysis and 'core_flows' in analysis['app_metadata']:
                    features.update(analysis['app_metadata']['core_flows'])
                # From reused patterns in consistency
                if 'consistency' in analysis and 'reused_patterns' in analysis['consistency']:
                    features.update(analysis['consistency']['reused_patterns'])
                # From positives aspects
                if 'positive' in analysis:
                    for pos in analysis['positive']:
                        if 'aspect' in pos:
                            features.add(pos['aspect'])
            
            all_features.update(features)
            
            item_data = {
                'id': item.get('id'),
                'app_name': item.get('app_name'),
                'completed_at': item.get('completed_at'),
                'ux_score': item.get('ux_score'),
                'analysis_json': analysis,
                'features': list(features),
                'issues': analysis.get('issues', []) if analysis else [],
                'positives': analysis.get('positive', []) if analysis else [],
                'navigation_depth': analysis.get('navigation_metrics', {}).get('avg_depth', 0) if analysis else 0,
                'max_depth': analysis.get('navigation_metrics', {}).get('max_depth', 0) if analysis else 0,
                'complexity_score': analysis.get('complexity_score', 0) if analysis else 0,
                'screens_discovered': analysis.get('app_metadata', {}).get('screens_discovered', 0) if analysis else 0,
                'error_handling_rating': analysis.get('error_handling', {}).get('handling_rating', 'unknown') if analysis else 'unknown'
            }
            items.append(item_data)
        
        # Find common and distinct features
        if items:
            common_features = set(items[0]['features'])
            for item in items[1:]:
                common_features = common_features.intersection(set(item['features']))
            
            # Add distinct features for each item
            for item in items:
                item['distinct_features'] = list(set(item['features']) - common_features)
            
            comparison_summary = {
                'common_features': list(common_features),
                'all_features': list(all_features),
                'total_apps': len(items)
            }
        else:
            comparison_summary = {
                'common_features': [],
                'all_features': [],
                'total_apps': 0
            }
        
        return jsonify({
            'items': items,
            'comparison_summary': comparison_summary
        })
    except Exception as e:
        import traceback
        print(f"Error in compare: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/compare/snapshot', methods=['POST'])
def create_snapshot():
    """Create a comparison snapshot"""
    try:
        data = request.json
        name = data.get('name', f'Comparison {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        exploration_ids = data.get('exploration_ids', [])
        comparison_data = data.get('comparison_data', {})
        
        save_comparison_snapshot(name, exploration_ids, comparison_data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/compare/snapshots')
def list_snapshots():
    """List comparison snapshots"""
    try:
        snapshots = get_comparison_snapshots()
        return jsonify({'snapshots': snapshots})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    """Get or update settings"""
    if request.method == 'GET':
        return jsonify(get_all_settings())
    
    try:
        data = request.json
        for key, value in data.items():
            set_setting(key, value)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/device-status')
def device_status():
    """Check ADB device connection status"""
    try:
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split('\n')
        # Filter out header and empty lines
        devices = [l for l in lines[1:] if l.strip() and 'device' in l]
        connected = len(devices) > 0
        return jsonify({
            'connected': connected,
            'devices': devices,
            'status': 'connected' if connected else 'disconnected'
        })
    except Exception as e:
        return jsonify({
            'connected': False,
            'status': 'error',
            'error': str(e)
        })


@app.route('/api/stop-agent', methods=['POST'])
def stop_agent():
    """Stop the currently running agent"""
    global agent_stop_flag, current_exploration_thread
    
    try:
        if current_exploration_thread and current_exploration_thread.is_alive():
            # Set the stop flag
            agent_stop_flag.set()
            send_log("⚠️ Stop signal sent to agent", 'warning')
            send_progress("Agent stopping...", -1)
            
            return jsonify({
                'success': True,
                'message': 'Stop signal sent to agent'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No agent currently running'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/results/<int:exploration_id>', methods=['DELETE'])
def delete_exploration(exploration_id):
    """Delete an exploration result"""
    try:
        from database import delete_exploration as db_delete_exploration
        success = db_delete_exploration(exploration_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Exploration not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_staged_exploration_async(request_id, app_name, category, persona, custom_navigation, max_depth, save_to_memory):
    """Run the staged exploration asynchronously"""
    global agent_stop_flag
    
    try:
        from staged_runner import run_staged_exploration
        
        send_log(f"🚀 Starting staged exploration for {app_name}...", 'info')
        send_progress(f"Initializing exploration for {app_name}...", 5)
        
        # Run the exploration - stdout/stderr capture happens inside staged_runner
        asyncio.run(run_staged_exploration(
            request_id=request_id,
            app_name=app_name,
            category=category,
            persona=persona,
            custom_navigation=custom_navigation,
            max_depth=max_depth,
            save_to_memory=save_to_memory,
            progress_callback=send_progress,
            log_callback=send_log,
            stage_callback=send_stage_update,
            stop_flag=agent_stop_flag
        ))
        
        send_log("✅ Exploration completed successfully!", 'success')
        send_progress("Exploration completed!", 100)
    
    except KeyboardInterrupt:
        send_log("⚠️ Exploration stopped by user", 'warning')
        send_progress("Exploration stopped", -1)
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        send_log(error_msg, 'error')
        send_progress(error_msg, -1)
        print(f"Exploration error: {e}")


def run_exploration_async(app_name, category, max_depth):
    """Run the exploration and analysis asynchronously (legacy)"""
    global agent_stop_flag
    
    try:
        # Import here to avoid circular imports
        from exploration_runner import run_exploration_with_category
        
        send_log(f"🚀 Starting UX exploration for {app_name}...", 'info')
        send_progress(f"Initializing test for {app_name}...", 5)
        
        # Run the exploration with stop flag
        asyncio.run(run_exploration_with_category(
            app_name=app_name,
            category=category,
            max_depth=max_depth,
            progress_callback=send_progress,
            log_callback=send_log,
            stop_flag=agent_stop_flag
        ))
        
        send_log("✅ Test completed successfully!", 'success')
        send_progress("Test completed successfully!", 100)
    
    except KeyboardInterrupt:
        send_log("⚠️ Agent execution stopped by user", 'warning')
        send_progress("Agent stopped by user", -1)
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        send_log(error_msg, 'error')
        send_progress(error_msg, -1)
        print(f"Exploration error: {e}")


if __name__ == '__main__':
    # Ensure templates and static folders exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Run verification before starting server (only in main process, not reloader)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # This is the reloader process, skip verification
        pass
    else:
        # This is the main process, run verification once
        print("Running pre-flight checks...")
        try:
            from verify_setup import main as verify_main
            verify_main()
        except SystemExit as e:
            if e.code != 0:
                print("\n❌ Verification failed. Please fix the issues above.")
                sys.exit(1)
    
    print("\n" + "="*60)
    print("🔭 Starting DroidScope UX Tester...")
    print("="*60)
    
    app.run(debug=True, threaded=True, port=5000)
