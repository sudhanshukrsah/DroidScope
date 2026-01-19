from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from llama_index.llms.openai_like import OpenAILike
import queue
import threading
import sys

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'droidrun-ux-tester-secret'

# Global queues for SSE
progress_queue = queue.Queue()
logs_queue = queue.Queue()

def send_log(message, log_type='info'):
    """Send log message to SSE queue"""
    logs_queue.put({
        'message': message,
        'type': log_type,
        'timestamp': datetime.now().strftime("%H:%M:%S")
    })

# Category context generator
def generate_category_context(app_name, category, api_key):
    """Generate category-specific context for UX testing"""
    llm = OpenAILike(
        model="mistralai/devstral-2512:free",
        api_base="https://openrouter.ai/api/v1",
        api_key=api_key,
        temperature=0.3
    )
    
    category_prompt = f"""You are a UX testing specialist for {category} applications.

For the app "{app_name}" in the {category} category, provide specific UX testing focus areas.

Consider:
- Common user flows in {category} apps
- Critical features users expect
- Industry-specific UI patterns
- Key success metrics for {category}

Return a concise paragraph (3-4 sentences) with testing priorities and what makes good UX in this category.
Focus on structural navigation, not user psychology."""

    try:
        response = llm.complete(category_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating category context: {e}")
        return f"Standard UX testing for {category} application."


def send_progress(message, percentage=0):
    """Send progress update to SSE queue"""
    progress_queue.put({
        'message': message,
        'percentage': percentage,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/')
def index():
    """Render main frontend page"""
    return render_template('index.html')


@app.route('/api/run-test', methods=['POST'])
def run_test():
    """Start UX exploration test"""
    data = request.json
    app_name = data.get('app_name', 'Unknown App')
    category = data.get('category', 'General')
    max_depth = int(data.get('max_depth', 6))
    
    # Clear previous queues
    while not progress_queue.empty():
        progress_queue.get()
    while not logs_queue.empty():
        logs_queue.get()
    
    # Start async test in background thread
    thread = threading.Thread(
        target=run_exploration_async,
        args=(app_name, category, max_depth)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'status': 'started',
        'app_name': app_name,
        'category': category,
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


@app.route('/api/logs')
def logs():
    """SSE endpoint for execution logs"""
    def generate():
        while True:
            try:
                log = logs_queue.get(timeout=30)
                yield f"data: {json.dumps(log)}\n\n"
                
                # Stop if we see completion message
                if 'complete' in log.get('message', '').lower() and log.get('type') == 'success':
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
    """Get analysis results"""
    try:
        # Read analysis results
        with open('ux_analysis_blocks.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({'error': 'No results available yet'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_exploration_async(app_name, category, max_depth):
    """Run the exploration and analysis asynchronously"""
    try:
        # Import here to avoid circular imports
        from exploration_runner import run_exploration_with_category
        
        send_log(f"Starting test for {app_name}...", 'info')
        send_progress(f"Initializing test for {app_name}...", 5)
        
        # Run the exploration
        asyncio.run(run_exploration_with_category(
            app_name=app_name,
            category=category,
            max_depth=max_depth,
            progress_callback=send_progress,
            log_callback=send_log
        ))
        
        send_log("Test completed successfully!", 'success')
        send_progress("Test completed successfully!", 100)
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        send_log(error_msg, 'error')
        send_progress(error_msg, -1)
        print(f"Exploration error: {e}")


if __name__ == '__main__':
    # Run verification before starting server
    print("Running pre-flight checks...")
    try:
        from verify_setup import main as verify_main
        verify_main()
    except SystemExit as e:
        if e.code != 0:
            print("\n❌ Verification failed. Please fix the issues above.")
            sys.exit(1)
    
    # Ensure templates and static folders exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    print("\n" + "="*60)
    print("🔭 Starting DroidScope UX Tester...")
    print("="*60)
    
    app.run(debug=True, threaded=True, port=5000)
