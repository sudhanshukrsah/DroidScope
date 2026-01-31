"""
DroidScope - UX Exploration & Analysis Tool
Flask backend with multi-stage exploration, SSE streaming, and database integration
"""
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import asyncio
import json
import os
import subprocess
import time
from datetime import datetime
from dotenv import load_dotenv
import queue
import threading
import sys

load_dotenv()

# Initialize database
from database import (
    init_db, get_setting, set_setting, get_all_settings,
    get_exploration, get_all_explorations, get_explorations_by_category,
    get_explorations_by_persona, get_result, get_latest_result,
    get_all_stages, get_comparison_data, create_comparison_snapshot
)

init_db()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'droidscope-secret-key')

# ============== Global State ==============

# SSE Queues
progress_queue = queue.Queue()
logs_queue = queue.Queue()
stage_queue = queue.Queue()

# Agent control
agent_stop_flag = threading.Event()
current_exploration_thread = None
current_exploration_id = None

# Log batching settings
LOG_BATCH_INTERVAL = 20  # seconds
log_batch_buffer = []
log_batch_lock = threading.Lock()
last_log_flush = time.time()


# ============== SSE Helpers ==============

def send_log(message, log_type='info'):
    """Send log message to SSE queue with batching"""
    global log_batch_buffer, last_log_flush
    
    with log_batch_lock:
        log_batch_buffer.append({
            'message': message,
            'type': log_type,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        })
        
        # Flush if buffer is large or time elapsed
        current_time = time.time()
        if len(log_batch_buffer) >= 10 or (current_time - last_log_flush) >= LOG_BATCH_INTERVAL:
            flush_log_batch()


def flush_log_batch():
    """Flush accumulated logs to queue"""
    global log_batch_buffer, last_log_flush
    
    if log_batch_buffer:
        # Combine messages for batch send
        for log_entry in log_batch_buffer:
            logs_queue.put(log_entry)
        log_batch_buffer = []
        last_log_flush = time.time()


def send_progress(message, percentage=0):
    """Send progress update to SSE queue"""
    progress_queue.put({
        'message': message,
        'percentage': percentage,
        'timestamp': datetime.now().isoformat()
    })


def send_stage_update(stage_data):
    """Send stage status update to SSE queue"""
    stage_queue.put(stage_data)


# ============== Device Status ==============

def check_device_connection():
    """Check if Android device is connected via ADB/DroidRun"""
    try:
        result = subprocess.run(
            ['droidrun', 'ping'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        # Fallback to adb check
        try:
            result = subprocess.run(
                ['adb', 'devices'],
                capture_output=True,
                text=True,
                timeout=5
            )
            lines = result.stdout.strip().split('\n')
            # Check if any device is connected (more than just header line)
            devices = [l for l in lines[1:] if l.strip() and 'device' in l]
            return len(devices) > 0
        except:
            return False


# ============== Routes: Pages ==============

@app.route('/')
def index():
    """Render main frontend page"""
    return render_template('index_v2.html')


# ============== Routes: API Endpoints ==============

@app.route('/api/device-status')
def device_status():
    """Get device connection status"""
    connected = check_device_connection()
    return jsonify({
        'connected': connected,
        'status': 'connected' if connected else 'disconnected'
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    """Get or update settings"""
    if request.method == 'GET':
        return jsonify(get_all_settings())
    
    elif request.method == 'POST':
        data = request.json
        for key, value in data.items():
            if key in ['api_key', 'llm_model', 'api_base']:
                set_setting(key, value)
        return jsonify({'success': True})


@app.route('/api/run-test', methods=['POST'])
def run_test():
    """Start multi-stage UX exploration test"""
    global current_exploration_thread, agent_stop_flag, current_exploration_id
    
    data = request.json
    app_name = data.get('app_name', 'Unknown App')
    category = data.get('category', 'General')
    persona = data.get('persona', 'UX Designer')
    custom_navigation = data.get('custom_navigation', '')
    max_depth = int(data.get('max_depth', 6))
    save_to_memory = data.get('save_to_memory', False)
    
    # Validation
    if not app_name:
        return jsonify({'error': 'App name is required'}), 400
    
    # Clear previous queues
    for q in [progress_queue, logs_queue, stage_queue]:
        while not q.empty():
            try:
                q.get_nowait()
            except:
                pass
    
    # Clear stop flag
    agent_stop_flag.clear()
    
    # Start exploration in background thread
    thread = threading.Thread(
        target=run_exploration_async,
        args=(app_name, category, persona, custom_navigation, max_depth, save_to_memory)
    )
    thread.daemon = True
    thread.start()
    
    current_exploration_thread = thread
    
    return jsonify({
        'status': 'started',
        'app_name': app_name,
        'category': category,
        'persona': persona,
        'max_depth': max_depth
    })


@app.route('/api/stop-agent', methods=['POST'])
def stop_agent():
    """Stop the currently running agent"""
    global agent_stop_flag, current_exploration_thread
    
    try:
        if current_exploration_thread and current_exploration_thread.is_alive():
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


@app.route('/api/progress')
def progress():
    """SSE endpoint for progress updates"""
    def generate():
        while True:
            try:
                update = progress_queue.get(timeout=30)
                yield f"data: {json.dumps(update)}\n\n"
                
                if update.get('percentage') >= 100 or update.get('percentage') < 0:
                    break
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
        while True:
            try:
                log = logs_queue.get(timeout=30)
                yield f"data: {json.dumps(log)}\n\n"
                
                if 'complete' in log.get('message', '').lower() and log.get('type') == 'success':
                    break
            except queue.Empty:
                # Flush any remaining batched logs
                with log_batch_lock:
                    flush_log_batch()
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
    """SSE endpoint for stage status updates"""
    def generate():
        while True:
            try:
                stage_data = stage_queue.get(timeout=30)
                yield f"data: {json.dumps(stage_data)}\n\n"
                
                # Stop if all stages complete
                if stage_data.get('stage') == 4 and stage_data.get('status') == 'completed':
                    break
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
    """Get current/latest analysis results"""
    exploration_id = request.args.get('exploration_id')
    
    try:
        if exploration_id:
            result = get_result(exploration_id)
        else:
            result = get_latest_result()
        
        if result:
            # Return full_json if available, otherwise construct from fields
            if result.get('full_json'):
                return jsonify(result['full_json'])
            else:
                return jsonify({
                    'summary': result.get('summary', ''),
                    'positive': result.get('positive_findings', []),
                    'issues': result.get('issues', []),
                    'recommendations': result.get('recommendations', []),
                    'ux_score': result.get('ux_score', 0),
                    'complexity_score': result.get('complexity_score', 0)
                })
        else:
            # Fallback to file-based results
            try:
                with open('ux_analysis_blocks.json', 'r', encoding='utf-8') as f:
                    return jsonify(json.load(f))
            except FileNotFoundError:
                return jsonify({'error': 'No results available yet'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/results/<exploration_id>')
def get_results_by_id(exploration_id):
    """Get results for a specific exploration"""
    try:
        result = get_result(exploration_id)
        if result and result.get('full_json'):
            exploration = get_exploration(exploration_id)
            data = result['full_json']
            data['exploration_info'] = exploration
            return jsonify(data)
        return jsonify({'error': 'Results not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/exploration/<exploration_id>/stages')
def get_exploration_stages(exploration_id):
    """Get all stages for an exploration"""
    try:
        stages = get_all_stages(exploration_id)
        return jsonify(stages)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============== Library Endpoints ==============

@app.route('/api/library')
def library():
    """Get all explorations for library view"""
    category = request.args.get('category')
    persona = request.args.get('persona')
    limit = int(request.args.get('limit', 50))
    
    try:
        if category:
            explorations = get_explorations_by_category(category)
        elif persona:
            explorations = get_explorations_by_persona(persona)
        else:
            explorations = get_all_explorations(limit)
        
        return jsonify(explorations)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/library/categories')
def get_categories():
    """Get list of all app categories"""
    categories = [
        'Social Media', 'E-Commerce', 'Food Delivery', 'Productivity',
        'Entertainment', 'Finance', 'Health & Fitness', 'Education',
        'Travel', 'Gaming', 'News', 'Messaging', 'Other'
    ]
    return jsonify(categories)


@app.route('/api/library/personas')
def get_personas():
    """Get list of all personas"""
    personas = ['UX Designer', 'QA Engineer', 'Product Manager']
    return jsonify(personas)


# ============== Comparison Endpoints ==============

@app.route('/api/compare')
def compare():
    """Get comparison data"""
    category = request.args.get('category')
    persona = request.args.get('persona')
    
    try:
        data = get_comparison_data(category, persona)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/compare/snapshot', methods=['POST'])
def create_snapshot():
    """Create a comparison snapshot"""
    data = request.json
    exploration_id = data.get('exploration_id')
    snapshot_name = data.get('name')
    
    try:
        snapshot_id = create_comparison_snapshot(exploration_id, snapshot_name)
        if snapshot_id:
            return jsonify({'success': True, 'snapshot_id': snapshot_id})
        return jsonify({'error': 'Failed to create snapshot'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============== Background Task ==============

def run_exploration_async(app_name, category, persona, custom_navigation, max_depth, save_to_memory):
    """Run the multi-stage exploration asynchronously"""
    global current_exploration_id
    
    try:
        from exploration_runner_v2 import run_staged_exploration
        
        send_log(f"🚀 Starting multi-stage exploration for {app_name}...", 'info')
        send_log(f"Category: {category} | Persona: {persona}", 'info')
        send_progress(f"Initializing exploration for {app_name}...", 5)
        
        # Run the staged exploration
        result = asyncio.run(run_staged_exploration(
            app_name=app_name,
            category=category,
            persona=persona,
            custom_navigation=custom_navigation if custom_navigation else None,
            max_depth=max_depth,
            save_to_memory=save_to_memory,
            progress_callback=send_progress,
            log_callback=send_log,
            stage_callback=send_stage_update,
            stop_flag=agent_stop_flag
        ))
        
        # Flush remaining logs
        with log_batch_lock:
            flush_log_batch()
        
        send_log("✅ All stages completed successfully!", 'success')
        send_progress("Exploration completed successfully!", 100)
        
    except KeyboardInterrupt:
        send_log("⚠️ Exploration stopped by user", 'warning')
        send_progress("Exploration stopped by user", -1)
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        send_log(error_msg, 'error')
        send_progress(error_msg, -1)
        print(f"Exploration error: {e}")
        import traceback
        traceback.print_exc()


# ============== Main ==============

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('explorations', exist_ok=True)
    
    # Run verification (optional)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("Running pre-flight checks...")
        try:
            from verify_setup import main as verify_main
            verify_main()
        except SystemExit as e:
            if e.code != 0:
                print("\n⚠️ Some verification checks failed. Continuing anyway...")
        except Exception as e:
            print(f"⚠️ Verification skipped: {e}")
    
    print("\n" + "="*60)
    print("🔭 Starting DroidScope v2...")
    print("="*60)
    print("📍 Open http://localhost:5000 in your browser")
    print("="*60 + "\n")
    
    app.run(debug=True, threaded=True, port=5000)
