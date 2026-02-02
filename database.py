"""SQLite database module for DroidScope"""
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

DATABASE_PATH = Path(__file__).parent / 'droidscope.db'


def get_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    # Enable foreign key constraints
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_database():
    """Initialize database tables"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Explorations table - main record for each exploration run
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS explorations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL,
            app_name TEXT NOT NULL,
            category TEXT NOT NULL,
            persona TEXT,
            custom_navigation TEXT,
            max_depth INTEGER DEFAULT 6,
            status TEXT DEFAULT 'pending',
            current_stage INTEGER DEFAULT 0,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            error_message TEXT
        )
    ''')
    
    # Stages table - individual stage records
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exploration_id INTEGER NOT NULL,
            stage_number INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            markdown_content TEXT,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            FOREIGN KEY (exploration_id) REFERENCES explorations(id) ON DELETE CASCADE,
            UNIQUE(exploration_id, stage_number)
        )
    ''')
    
    # Results table - final analysis results
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exploration_id INTEGER UNIQUE NOT NULL,
            analysis_json TEXT NOT NULL,
            ux_score REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (exploration_id) REFERENCES explorations(id) ON DELETE CASCADE
        )
    ''')
    
    # Create indexes for better query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_explorations_status ON explorations(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_explorations_category ON explorations(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_explorations_persona ON explorations(persona)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_exploration_id ON results(exploration_id)')
    
    # Comparison snapshots table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comparison_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            exploration_ids TEXT NOT NULL,
            comparison_data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()


# Settings operations
def get_setting(key, default=None):
    """Get a setting value"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    """Set a setting value"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
    ''', (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_all_settings():
    """Get all settings as dict"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    rows = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}


# Exploration operations
def create_exploration(request_id, app_name, category, persona=None, custom_navigation=None, max_depth=6):
    """Create a new exploration record"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO explorations (request_id, app_name, category, persona, custom_navigation, max_depth, status, started_at)
        VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
    ''', (request_id, app_name, category, persona, custom_navigation, max_depth, datetime.now().isoformat()))
    exploration_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return exploration_id


def get_exploration(request_id):
    """Get exploration by request_id"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM explorations WHERE request_id = ?', (request_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_exploration_by_id(exploration_id):
    """Get exploration by id"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM explorations WHERE id = ?', (exploration_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_exploration_status(exploration_id, status, error_message=None):
    """Update exploration status"""
    conn = get_connection()
    cursor = conn.cursor()
    if status in ('completed', 'failed'):
        cursor.execute('''
            UPDATE explorations SET status = ?, completed_at = ?, error_message = ?
            WHERE id = ?
        ''', (status, datetime.now().isoformat(), error_message, exploration_id))
    else:
        cursor.execute('''
            UPDATE explorations SET status = ?, current_stage = current_stage + 1
            WHERE id = ?
        ''', (status, exploration_id))
    conn.commit()
    conn.close()


def update_exploration_stage(exploration_id, stage_number):
    """Update current stage number"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE explorations SET current_stage = ? WHERE id = ?', (stage_number, exploration_id))
    conn.commit()
    conn.close()


# Stage operations
def create_stage(exploration_id, stage_number, stage_name):
    """Create a stage record"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO stages (exploration_id, stage_number, stage_name, status, started_at)
        VALUES (?, ?, ?, 'running', ?)
    ''', (exploration_id, stage_number, stage_name, datetime.now().isoformat()))
    stage_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return stage_id


def update_stage(stage_id, status, markdown_content=None, error_message=None):
    """Update stage status and content"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE stages SET status = ?, markdown_content = ?, completed_at = ?, error_message = ?
        WHERE id = ?
    ''', (status, markdown_content, datetime.now().isoformat(), error_message, stage_id))
    conn.commit()
    conn.close()


def get_stages(exploration_id):
    """Get all stages for an exploration"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stages WHERE exploration_id = ? ORDER BY stage_number', (exploration_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# Results operations
def save_result(exploration_id, analysis_json, ux_score=None):
    """Save final analysis result"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO results (exploration_id, analysis_json, ux_score, created_at)
        VALUES (?, ?, ?, ?)
    ''', (exploration_id, json.dumps(analysis_json), ux_score, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_result(exploration_id):
    """Get result for an exploration"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM results WHERE exploration_id = ?', (exploration_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        result = dict(row)
        result['analysis_json'] = json.loads(result['analysis_json'])
        return result
    return None


def get_latest_result():
    """Get the most recent result"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, e.app_name, e.category, e.persona
        FROM results r
        JOIN explorations e ON r.exploration_id = e.id
        ORDER BY r.created_at DESC LIMIT 1
    ''')
    row = cursor.fetchone()
    conn.close()
    if row:
        result = dict(row)
        result['analysis_json'] = json.loads(result['analysis_json'])
        return result
    return None


# Library operations
def get_library(limit=50, offset=0, category=None, persona=None):
    """Get exploration library with filters"""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT e.*, r.ux_score, r.created_at as result_date
        FROM explorations e
        LEFT JOIN results r ON e.id = r.exploration_id
        WHERE e.status = 'completed'
    '''
    params = []
    
    if category:
        query += ' AND e.category = ?'
        params.append(category)
    if persona:
        query += ' AND e.persona = ?'
        params.append(persona)
    
    query += ' ORDER BY e.completed_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_library_count(category=None, persona=None):
    """Get total count for library"""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = 'SELECT COUNT(*) as count FROM explorations WHERE status = ?'
    params = ['completed']
    
    if category:
        query += ' AND category = ?'
        params.append(category)
    if persona:
        query += ' AND persona = ?'
        params.append(persona)
    
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row['count']


# Comparison operations
def get_comparison_data(category, persona):
    """Get data for comparison by category and persona"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT e.id, e.app_name, e.category, e.persona, e.completed_at, r.analysis_json, r.ux_score
        FROM explorations e
        JOIN results r ON e.id = r.exploration_id
        WHERE e.category = ? AND e.persona = ? AND e.status = 'completed'
        ORDER BY e.completed_at DESC
    ''', (category, persona))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        result = dict(row)
        result['analysis_json'] = json.loads(result['analysis_json'])
        results.append(result)
    return results


def save_comparison_snapshot(name, exploration_ids, comparison_data):
    """Save a comparison snapshot"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO comparison_snapshots (name, exploration_ids, comparison_data, created_at)
        VALUES (?, ?, ?, ?)
    ''', (name, json.dumps(exploration_ids), json.dumps(comparison_data), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_comparison_snapshots():
    """Get all comparison snapshots"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM comparison_snapshots ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        result = dict(row)
        result['exploration_ids'] = json.loads(result['exploration_ids'])
        if result['comparison_data']:
            result['comparison_data'] = json.loads(result['comparison_data'])
        results.append(result)
    return results


def delete_exploration(exploration_id):
    """Delete an exploration and all related data (CASCADE)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if exploration exists
        cursor.execute('SELECT id FROM explorations WHERE id = ?', (exploration_id,))
        if not cursor.fetchone():
            conn.close()
            return False
        
        # Delete exploration - CASCADE will automatically delete related stages and results
        cursor.execute('DELETE FROM explorations WHERE id = ?', (exploration_id,))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error deleting exploration {exploration_id}: {e}")
        return False
    
    conn.commit()
    conn.close()
    return True


# Initialize database on import
init_database()
