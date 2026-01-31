"""
Database models and operations for DroidScope
Using SQLite for persistent storage of explorations, stages, and results
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import uuid

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'droidscope.db')


def get_db_connection():
    """Get a database connection with row factory"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_db():
    """Initialize the database with all required tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Settings table for API keys and model configuration
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Explorations table - main exploration sessions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS explorations (
                id TEXT PRIMARY KEY,
                app_name TEXT NOT NULL,
                category TEXT NOT NULL,
                persona TEXT NOT NULL,
                custom_navigation TEXT,
                save_to_memory INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                current_stage INTEGER DEFAULT 0,
                total_stages INTEGER DEFAULT 4,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        
        # Exploration stages table - individual stage data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exploration_stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exploration_id TEXT NOT NULL,
                stage_number INTEGER NOT NULL,
                stage_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                md_content TEXT,
                json_data TEXT,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (exploration_id) REFERENCES explorations(id),
                UNIQUE(exploration_id, stage_number)
            )
        ''')
        
        # Final results table - combined analysis results
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exploration_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exploration_id TEXT UNIQUE NOT NULL,
                summary TEXT,
                positive_findings TEXT,
                issues TEXT,
                recommendations TEXT,
                metrics TEXT,
                ux_score REAL,
                complexity_score REAL,
                full_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exploration_id) REFERENCES explorations(id)
            )
        ''')
        
        # Comparison snapshots for the compare feature
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comparison_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exploration_id TEXT NOT NULL,
                snapshot_name TEXT,
                category TEXT,
                persona TEXT,
                ux_score REAL,
                complexity_score REAL,
                key_metrics TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exploration_id) REFERENCES explorations(id)
            )
        ''')
        
        print("✅ Database initialized successfully")


# ============== Settings Operations ==============

def get_setting(key: str, default: str = None) -> Optional[str]:
    """Get a setting value by key"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row['value'] if row else default


def set_setting(key: str, value: str) -> bool:
    """Set a setting value"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO settings (key, value, updated_at) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
        ''', (key, value, value))
        return True


def get_all_settings() -> Dict[str, str]:
    """Get all settings as a dictionary"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        return {row['key']: row['value'] for row in cursor.fetchall()}


# ============== Exploration Operations ==============

def create_exploration(
    app_name: str,
    category: str,
    persona: str,
    custom_navigation: str = None,
    save_to_memory: bool = False
) -> str:
    """Create a new exploration session and return its ID"""
    exploration_id = str(uuid.uuid4())[:8]
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO explorations 
            (id, app_name, category, persona, custom_navigation, save_to_memory, status)
            VALUES (?, ?, ?, ?, ?, ?, 'running')
        ''', (exploration_id, app_name, category, persona, custom_navigation, 1 if save_to_memory else 0))
        
        # Create stage records
        stage_names = [
            'Basic Exploration',
            'Persona Analysis',
            'Custom Navigation / Stress Test',
            'Final Analysis'
        ]
        for i, name in enumerate(stage_names, 1):
            cursor.execute('''
                INSERT INTO exploration_stages (exploration_id, stage_number, stage_name, status)
                VALUES (?, ?, ?, 'pending')
            ''', (exploration_id, i, name))
    
    return exploration_id


def get_exploration(exploration_id: str) -> Optional[Dict[str, Any]]:
    """Get exploration details by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM explorations WHERE id = ?', (exploration_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def update_exploration_status(exploration_id: str, status: str, current_stage: int = None):
    """Update exploration status"""
    with get_db() as conn:
        cursor = conn.cursor()
        if current_stage is not None:
            cursor.execute('''
                UPDATE explorations 
                SET status = ?, current_stage = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, current_stage, exploration_id))
        else:
            cursor.execute('''
                UPDATE explorations SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            ''', (status, exploration_id))
        
        if status == 'completed':
            cursor.execute('''
                UPDATE explorations SET completed_at = CURRENT_TIMESTAMP WHERE id = ?
            ''', (exploration_id,))


def get_all_explorations(limit: int = 50) -> List[Dict[str, Any]]:
    """Get all explorations ordered by creation date"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.*, r.ux_score, r.complexity_score 
            FROM explorations e
            LEFT JOIN exploration_results r ON e.id = r.exploration_id
            ORDER BY e.created_at DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_explorations_by_category(category: str) -> List[Dict[str, Any]]:
    """Get explorations filtered by category"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.*, r.ux_score, r.complexity_score 
            FROM explorations e
            LEFT JOIN exploration_results r ON e.id = r.exploration_id
            WHERE e.category = ?
            ORDER BY e.created_at DESC
        ''', (category,))
        return [dict(row) for row in cursor.fetchall()]


def get_explorations_by_persona(persona: str) -> List[Dict[str, Any]]:
    """Get explorations filtered by persona"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.*, r.ux_score, r.complexity_score 
            FROM explorations e
            LEFT JOIN exploration_results r ON e.id = r.exploration_id
            WHERE e.persona = ?
            ORDER BY e.created_at DESC
        ''', (persona,))
        return [dict(row) for row in cursor.fetchall()]


# ============== Stage Operations ==============

def update_stage(
    exploration_id: str,
    stage_number: int,
    status: str,
    md_content: str = None,
    json_data: dict = None,
    error_message: str = None
):
    """Update a specific exploration stage"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if status == 'running':
            cursor.execute('''
                UPDATE exploration_stages 
                SET status = ?, started_at = CURRENT_TIMESTAMP
                WHERE exploration_id = ? AND stage_number = ?
            ''', (status, exploration_id, stage_number))
        elif status in ['completed', 'failed']:
            json_str = json.dumps(json_data) if json_data else None
            cursor.execute('''
                UPDATE exploration_stages 
                SET status = ?, md_content = ?, json_data = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP
                WHERE exploration_id = ? AND stage_number = ?
            ''', (status, md_content, json_str, error_message, exploration_id, stage_number))
        else:
            cursor.execute('''
                UPDATE exploration_stages SET status = ? WHERE exploration_id = ? AND stage_number = ?
            ''', (status, exploration_id, stage_number))


def get_stage(exploration_id: str, stage_number: int) -> Optional[Dict[str, Any]]:
    """Get a specific stage data"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM exploration_stages 
            WHERE exploration_id = ? AND stage_number = ?
        ''', (exploration_id, stage_number))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            if data.get('json_data'):
                data['json_data'] = json.loads(data['json_data'])
            return data
        return None


def get_all_stages(exploration_id: str) -> List[Dict[str, Any]]:
    """Get all stages for an exploration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM exploration_stages 
            WHERE exploration_id = ? 
            ORDER BY stage_number
        ''', (exploration_id,))
        stages = []
        for row in cursor.fetchall():
            data = dict(row)
            if data.get('json_data'):
                data['json_data'] = json.loads(data['json_data'])
            stages.append(data)
        return stages


# ============== Results Operations ==============

def save_result(
    exploration_id: str,
    summary: str,
    positive_findings: list,
    issues: list,
    recommendations: list,
    metrics: dict,
    ux_score: float,
    complexity_score: float,
    full_json: dict
):
    """Save final analysis results"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO exploration_results 
            (exploration_id, summary, positive_findings, issues, recommendations, metrics, ux_score, complexity_score, full_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(exploration_id) DO UPDATE SET
                summary = ?, positive_findings = ?, issues = ?, recommendations = ?, 
                metrics = ?, ux_score = ?, complexity_score = ?, full_json = ?
        ''', (
            exploration_id,
            summary,
            json.dumps(positive_findings),
            json.dumps(issues),
            json.dumps(recommendations),
            json.dumps(metrics),
            ux_score,
            complexity_score,
            json.dumps(full_json),
            summary,
            json.dumps(positive_findings),
            json.dumps(issues),
            json.dumps(recommendations),
            json.dumps(metrics),
            ux_score,
            complexity_score,
            json.dumps(full_json)
        ))


def get_result(exploration_id: str) -> Optional[Dict[str, Any]]:
    """Get results for an exploration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM exploration_results WHERE exploration_id = ?', (exploration_id,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            # Parse JSON fields
            for field in ['positive_findings', 'issues', 'recommendations', 'metrics', 'full_json']:
                if data.get(field):
                    data[field] = json.loads(data[field])
            return data
        return None


def get_latest_result() -> Optional[Dict[str, Any]]:
    """Get the most recent result"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, e.app_name, e.category, e.persona 
            FROM exploration_results r
            JOIN explorations e ON r.exploration_id = e.id
            ORDER BY r.created_at DESC 
            LIMIT 1
        ''')
        row = cursor.fetchone()
        if row:
            data = dict(row)
            for field in ['positive_findings', 'issues', 'recommendations', 'metrics', 'full_json']:
                if data.get(field):
                    data[field] = json.loads(data[field])
            return data
        return None


# ============== Comparison Operations ==============

def create_comparison_snapshot(
    exploration_id: str,
    snapshot_name: str = None
) -> int:
    """Create a snapshot for comparison"""
    exploration = get_exploration(exploration_id)
    result = get_result(exploration_id)
    
    if not exploration or not result:
        return None
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO comparison_snapshots 
            (exploration_id, snapshot_name, category, persona, ux_score, complexity_score, key_metrics)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            exploration_id,
            snapshot_name or f"{exploration['app_name']} - {exploration['created_at'][:10]}",
            exploration['category'],
            exploration['persona'],
            result.get('ux_score'),
            result.get('complexity_score'),
            json.dumps(result.get('metrics', {}))
        ))
        return cursor.lastrowid


def get_comparison_data(category: str = None, persona: str = None) -> List[Dict[str, Any]]:
    """Get comparison data filtered by category and/or persona"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        query = '''
            SELECT cs.*, e.app_name 
            FROM comparison_snapshots cs
            JOIN explorations e ON cs.exploration_id = e.id
            WHERE 1=1
        '''
        params = []
        
        if category:
            query += ' AND cs.category = ?'
            params.append(category)
        if persona:
            query += ' AND cs.persona = ?'
            params.append(persona)
        
        query += ' ORDER BY cs.created_at DESC'
        
        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            data = dict(row)
            if data.get('key_metrics'):
                data['key_metrics'] = json.loads(data['key_metrics'])
            results.append(data)
        return results


# Initialize database on module import
if __name__ == '__main__':
    init_db()
