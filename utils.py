"""Utility functions for DroidRun UX Explorer"""
import os
from pathlib import Path


def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent


def load_prompt(prompt_name):
    """Load a prompt template from the prompts folder
    
    Args:
        prompt_name: Name of the prompt file (with or without .txt extension)
    
    Returns:
        str: Content of the prompt file
    """
    if not prompt_name.endswith('.txt'):
        prompt_name += '.txt'
    
    prompt_path = get_project_root() / 'prompts' / prompt_name
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    except Exception as e:
        raise Exception(f"Error loading prompt {prompt_name}: {str(e)}")


def format_prompt(template, **kwargs):
    """Format a prompt template with provided variables
    
    Args:
        template: Prompt template string
        **kwargs: Variables to format into the template
    
    Returns:
        str: Formatted prompt
    """
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise KeyError(f"Missing required variable in prompt template: {e}")


def load_and_format_prompt(prompt_name, **kwargs):
    """Load and format a prompt in one step
    
    Args:
        prompt_name: Name of the prompt file
        **kwargs: Variables to format into the template
    
    Returns:
        str: Loaded and formatted prompt
    """
    template = load_prompt(prompt_name)
    return format_prompt(template, **kwargs)


def read_markdown_file(filename):
    """Read a markdown file from the root directory
    
    Args:
        filename: Name of the markdown file
    
    Returns:
        str: Content of the markdown file or None if not found
    """
    file_path = get_project_root() / filename
    try:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return None


def find_stage_markdown_files():
    """Find all stage markdown files in root directory
    
    Returns:
        dict: Dictionary mapping stage number to file content
    """
    root = get_project_root()
    stage_files = {}
    
    # Look for stage files with pattern stage*_*.md
    for file in root.glob('stage*_*.md'):
        try:
            # Extract stage number from filename
            name = file.stem  # e.g., 'stage1_basic_exploration'
            if name.startswith('stage'):
                stage_num = int(name[5])  # Get the digit after 'stage'
                with open(file, 'r', encoding='utf-8') as f:
                    stage_files[stage_num] = {
                        'filename': file.name,
                        'content': f.read()
                    }
        except (ValueError, IndexError):
            continue
    
    return stage_files


def cleanup_stage_files():
    """Remove stage markdown files from root directory"""
    root = get_project_root()
    for file in root.glob('stage*_*.md'):
        try:
            file.unlink()
        except Exception as e:
            print(f"Error deleting {file}: {e}")
