"""
DroidScope v2 Launcher
Run this file to start the refactored DroidScope application
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize database on startup
from database import init_db
init_db()

# Import and run the v2 app
from app_v2 import app

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('explorations', exist_ok=True)
    os.makedirs('prompts', exist_ok=True)
    
    print("\n" + "="*60)
    print("🔭 DroidScope v2 - Multi-Stage UX Exploration")
    print("="*60)
    print("📍 Open http://localhost:5000 in your browser")
    print("="*60)
    print("\nNew Features:")
    print("  • 4-stage exploration (Basic → Persona → Stress → Analysis)")
    print("  • Persona-based analysis (UX Designer, QA, PM)")
    print("  • SQLite database for results storage")
    print("  • Results library and comparison")
    print("  • Settings persistence via frontend")
    print("="*60 + "\n")
    
    app.run(debug=True, threaded=True, port=5000)
