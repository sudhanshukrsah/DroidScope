"""
Utility script to manually save ux_analysis_blocks.json to database

This script can be used to:
1. Manually import a JSON file to the database
2. Re-import results if there was an issue during exploration
3. Verify JSON file integrity before DB save
"""
import json
import os
import sys
from database import save_result, get_exploration, get_exploration_by_id


def import_json_to_db(json_file='ux_analysis_blocks.json', exploration_id=None):
    """
    Import a JSON analysis file to the database
    
    Args:
        json_file: Path to the JSON file (default: ux_analysis_blocks.json)
        exploration_id: The exploration ID to associate with (optional, uses latest if None)
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Check if file exists
    if not os.path.exists(json_file):
        print(f"❌ Error: File '{json_file}' not found")
        return False
    
    try:
        # Read JSON file
        print(f"📖 Reading {json_file}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            analysis_json = json.load(f)
        
        print(f"✅ JSON file loaded successfully")
        print(f"   - Keys found: {', '.join(analysis_json.keys())}")
        
        # Validate required fields
        required_fields = ['summary', 'ux_confidence_score']
        missing_fields = [f for f in required_fields if f not in analysis_json]
        if missing_fields:
            print(f"⚠️  Warning: Missing recommended fields: {', '.join(missing_fields)}")
        
        # Get UX score
        ux_score = analysis_json.get('ux_confidence_score', {}).get('score', 5)
        print(f"   - UX Score: {ux_score}/10")
        
        # Determine exploration ID
        if exploration_id is None:
            # Get the latest exploration
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id, app_name, completed_at FROM explorations ORDER BY id DESC LIMIT 1')
            row = cursor.fetchone()
            conn.close()
            
            if row:
                exploration_id = row['id']
                print(f"   - Using latest exploration: ID={exploration_id}, App={row['app_name']}")
            else:
                print(f"❌ Error: No explorations found in database")
                return False
        else:
            # Verify exploration exists
            exploration = get_exploration_by_id(exploration_id)
            if not exploration:
                print(f"❌ Error: Exploration ID {exploration_id} not found")
                return False
            print(f"   - Using exploration: ID={exploration_id}, App={exploration['app_name']}")
        
        # Save to database
        print(f"💾 Saving to database...")
        save_result(exploration_id, analysis_json, ux_score)
        
        print(f"✅ Successfully saved to database!")
        print(f"   - Exploration ID: {exploration_id}")
        print(f"   - UX Score: {ux_score}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON file - {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_json_file(json_file='ux_analysis_blocks.json'):
    """Verify JSON file structure without saving to database"""
    if not os.path.exists(json_file):
        print(f"❌ Error: File '{json_file}' not found")
        return False
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ Valid JSON file")
        print(f"\nStructure:")
        print(f"  - Summary: {len(data.get('summary', ''))} chars")
        print(f"  - Positive findings: {len(data.get('positive', []))}")
        print(f"  - Issues: {len(data.get('issues', []))}")
        print(f"  - Recommendations: {len(data.get('recommendations', []))}")
        print(f"  - UX Score: {data.get('ux_confidence_score', {}).get('score', 'N/A')}")
        print(f"  - Dark Patterns: {len(data.get('dark_patterns_detected', []))}")
        print(f"  - Actor Analysis: {len(data.get('actor_analysis', []))}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("JSON to Database Utility")
    print("=" * 60)
    print()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'import':
            json_file = sys.argv[2] if len(sys.argv) > 2 else 'ux_analysis_blocks.json'
            exploration_id = int(sys.argv[3]) if len(sys.argv) > 3 else None
            import_json_to_db(json_file, exploration_id)
            
        elif command == 'verify':
            json_file = sys.argv[2] if len(sys.argv) > 2 else 'ux_analysis_blocks.json'
            verify_json_file(json_file)
            
        else:
            print(f"Unknown command: {command}")
            print()
            print("Usage:")
            print("  python json_to_db.py verify [json_file]")
            print("  python json_to_db.py import [json_file] [exploration_id]")
    else:
        # Default: import ux_analysis_blocks.json to latest exploration
        import_json_to_db()
