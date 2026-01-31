"""
Multi-stage exploration runner with batch processing and database integration
Implements 4-stage exploration: Basic -> Persona -> Stress Test -> Final Analysis
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Callable, Optional
from dotenv import load_dotenv
from llama_index.llms.openai_like import OpenAILike
from droidrun import DroidAgent
from droidrun.config_manager import DroidrunConfig

from utils import load_prompt, format_prompt
from database import (
    init_db, get_setting, create_exploration, update_exploration_status,
    update_stage, get_stage, get_all_stages, save_result, get_result,
    create_comparison_snapshot
)

load_dotenv()

# Stage configuration
STAGES = {
    1: {'name': 'Basic Exploration', 'prompt_file': 'stage1_basic_exploration', 'output_file': 'stage1_basic_exploration.md'},
    2: {'name': 'Persona Analysis', 'prompt_file': 'stage2_persona_analysis', 'output_file': 'stage2_persona_analysis.md'},
    3: {'name': 'Custom Navigation / Stress Test', 'prompt_file': 'stage3_custom_stress', 'output_file': 'stage3_stress_test.md'},
    4: {'name': 'Final Analysis', 'prompt_file': 'stage4_final_analysis', 'output_file': None}  # No agent run, LLM only
}

PERSONA_PROMPTS = {
    'ux_designer': 'persona_ux_designer',
    'qa_engineer': 'persona_qa_engineer',
    'product_manager': 'persona_product_manager'
}

PERSONA_SLUGS = {
    'UX Designer': 'ux_designer',
    'QA Engineer': 'qa_engineer',
    'Product Manager': 'product_manager'
}


class StageExplorationRunner:
    """Runs multi-stage exploration with proper error handling and database integration"""
    
    def __init__(
        self,
        exploration_id: str,
        app_name: str,
        category: str,
        persona: str,
        custom_navigation: str = None,
        max_depth: int = 6,
        progress_callback: Callable = None,
        log_callback: Callable = None,
        stage_callback: Callable = None,
        stop_flag = None
    ):
        self.exploration_id = exploration_id
        self.app_name = app_name
        self.category = category
        self.persona = persona
        self.persona_slug = PERSONA_SLUGS.get(persona, 'ux_designer')
        self.custom_navigation = custom_navigation
        self.max_depth = max_depth
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.stage_callback = stage_callback
        self.stop_flag = stop_flag
        
        # Output directory for this exploration
        self.output_dir = os.path.join('explorations', exploration_id)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # LLM setup
        self.api_key = get_setting('api_key') or os.getenv("API_KEY")
        self.model = get_setting('llm_model') or os.getenv("LLM_MODEL", "mistralai/devstral-2512:free")
        self.api_base = get_setting('api_base') or os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
        
        self.llm = OpenAILike(
            model=self.model,
            api_base=self.api_base,
            api_key=self.api_key,
            temperature=0.2
        )
        
        # Stage data storage
        self.stage_data = {}
    
    def log(self, message: str, log_type: str = 'info'):
        """Send log message"""
        if self.log_callback:
            self.log_callback(message, log_type)
        print(f"[{log_type.upper()}] {message}")
    
    def progress(self, message: str, percentage: int):
        """Send progress update"""
        if self.progress_callback:
            self.progress_callback(message, percentage)
    
    def stage_update(self, stage_num: int, stage_name: str, status: str):
        """Send stage status update"""
        if self.stage_callback:
            self.stage_callback({
                'stage': stage_num,
                'name': stage_name,
                'status': status,
                'total_stages': 4
            })
    
    def check_stop(self):
        """Check if stop was requested"""
        if self.stop_flag and self.stop_flag.is_set():
            self.log("Exploration stopped by user", 'warning')
            raise KeyboardInterrupt("Exploration stopped by user request")
    
    def get_persona_prompt(self) -> str:
        """Load the appropriate persona prompt"""
        prompt_file = PERSONA_PROMPTS.get(self.persona_slug, 'persona_ux_designer')
        return load_prompt(prompt_file)
    
    def build_stage_prompt(self, stage_num: int) -> str:
        """Build the complete prompt for a stage"""
        stage_config = STAGES[stage_num]
        base_prompt = load_prompt(stage_config['prompt_file'])
        
        if stage_num == 1:
            # Basic exploration - simple substitution
            return format_prompt(base_prompt, app_name=self.app_name, category=self.category)
        
        elif stage_num == 2:
            # Persona analysis - include persona prompt
            persona_prompt = self.get_persona_prompt()
            return format_prompt(
                base_prompt,
                app_name=self.app_name,
                category=self.category,
                persona=self.persona,
                persona_slug=self.persona_slug,
                persona_prompt=persona_prompt,
                max_depth=self.max_depth
            )
        
        elif stage_num == 3:
            # Custom navigation / stress test
            if self.custom_navigation:
                custom_nav_section = f"""
## CUSTOM NAVIGATION INSTRUCTIONS

The user has requested specific navigation testing:

{self.custom_navigation}

Please execute these specific navigation steps FIRST, then proceed with stress testing.
Document the results of each custom navigation step.
"""
                custom_nav_results = """
[Document results of custom navigation steps here]
"""
            else:
                custom_nav_section = """
## NO CUSTOM NAVIGATION

No specific navigation was requested. Proceed directly with stress testing.
Act as a "dumb user" - scroll randomly, mistap, navigate erratically to test app resilience.
"""
                custom_nav_results = "N/A - No custom navigation requested"
            
            return format_prompt(
                base_prompt,
                app_name=self.app_name,
                category=self.category,
                custom_navigation_section=custom_nav_section,
                custom_nav_results_section=custom_nav_results
            )
        
        elif stage_num == 4:
            # Final analysis - combine all stage data
            stage1_data = self.stage_data.get(1, 'No data from Stage 1')
            stage2_data = self.stage_data.get(2, 'No data from Stage 2')
            stage3_data = self.stage_data.get(3, 'No data from Stage 3')
            
            return format_prompt(
                base_prompt,
                app_name=self.app_name,
                category=self.category,
                persona=self.persona,
                exploration_id=self.exploration_id,
                stage1_data=stage1_data,
                stage2_data=stage2_data,
                stage3_data=stage3_data
            )
        
        return base_prompt
    
    async def run_agent_stage(self, stage_num: int) -> str:
        """Run a single agent exploration stage"""
        stage_config = STAGES[stage_num]
        stage_name = stage_config['name']
        output_file = stage_config['output_file']
        
        self.log(f"Starting Stage {stage_num}: {stage_name}", 'info')
        self.stage_update(stage_num, stage_name, 'running')
        update_stage(self.exploration_id, stage_num, 'running')
        
        try:
            self.check_stop()
            
            # Build stage-specific prompt
            stage_prompt = self.build_stage_prompt(stage_num)
            
            # Configure agent
            config = DroidrunConfig()
            config.agent.max_steps = self.max_depth * 10 if stage_num == 1 else self.max_depth * 15
            
            # Create agent with stage-specific goal
            agent = DroidAgent(
                goal=stage_prompt,
                config=config,
                llms=self.llm,
            )
            
            self.log(f"Agent configured for Stage {stage_num}", 'success')
            
            # Capture output
            import sys
            from io import StringIO
            
            class BufferedOutput:
                def __init__(self, original, callback, buffer_size=2048):
                    self.original = original
                    self.callback = callback
                    self.buffer = []
                    self.buffer_size = buffer_size
                    self.total_chars = 0
                
                def write(self, data):
                    if not data:
                        return
                    self.original.write(data)
                    self.buffer.append(data)
                    self.total_chars += len(data)
                    
                    if self.callback and self.total_chars >= self.buffer_size:
                        self._flush()
                
                def _flush(self):
                    if not self.buffer:
                        return
                    combined = ''.join(self.buffer)
                    lines = [l for l in combined.split('\n') if l.strip()]
                    if lines and self.callback:
                        self.callback('\n'.join(lines), 'agent')
                    self.buffer = []
                    self.total_chars = 0
                
                def flush(self):
                    self.original.flush()
                    self._flush()
            
            original_stdout = sys.stdout
            buffered = BufferedOutput(original_stdout, self.log_callback)
            sys.stdout = buffered
            
            try:
                # Run agent
                result = await agent.run()
                sys.stdout.flush()
            finally:
                sys.stdout = original_stdout
            
            # Extract result content
            md_content = ""
            if hasattr(result, 'final_answer') and result.final_answer:
                md_content = result.final_answer
            elif hasattr(result, 'structured_output') and result.structured_output:
                md_content = str(result.structured_output)
            
            # Save to file
            if output_file:
                output_path = os.path.join(self.output_dir, output_file)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                self.log(f"Stage {stage_num} output saved: {output_file}", 'success')
            
            # Store for later stages
            self.stage_data[stage_num] = md_content
            
            # Update database
            update_stage(
                self.exploration_id, stage_num, 'completed',
                md_content=md_content
            )
            
            self.stage_update(stage_num, stage_name, 'completed')
            self.log(f"Stage {stage_num} completed successfully", 'success')
            
            return md_content
            
        except Exception as e:
            error_msg = str(e)
            self.log(f"Stage {stage_num} failed: {error_msg}", 'error')
            self.stage_update(stage_num, stage_name, 'failed')
            update_stage(
                self.exploration_id, stage_num, 'failed',
                error_message=error_msg
            )
            raise
    
    async def run_final_analysis(self) -> dict:
        """Run Stage 4: Final LLM analysis (no agent, just LLM)"""
        stage_num = 4
        stage_name = STAGES[stage_num]['name']
        
        self.log(f"Starting Stage {stage_num}: {stage_name}", 'info')
        self.stage_update(stage_num, stage_name, 'running')
        update_stage(self.exploration_id, stage_num, 'running')
        
        try:
            self.check_stop()
            
            # Build the final analysis prompt with all stage data
            analysis_prompt = self.build_stage_prompt(stage_num)
            
            self.log("Sending combined data to LLM for final analysis...", 'info')
            
            # Call LLM for final analysis
            response = self.llm.complete(analysis_prompt)
            analysis_text = response.text.strip()
            
            # Parse JSON response
            if analysis_text.startswith("```json"):
                analysis_text = analysis_text.split("```json")[1].split("```")[0].strip()
            elif analysis_text.startswith("```"):
                analysis_text = analysis_text.split("```")[1].split("```")[0].strip()
            
            analysis_json = json.loads(analysis_text)
            
            # Ensure all required fields exist
            analysis_json = self.ensure_complete_json(analysis_json)
            
            # Save to file
            output_path = os.path.join(self.output_dir, 'final_analysis.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(analysis_json, f, indent=2)
            
            # Also save to standard location for backward compatibility
            with open('ux_analysis_blocks.json', 'w', encoding='utf-8') as f:
                json.dump(analysis_json, f, indent=2)
            
            self.log("Final analysis completed", 'success')
            
            # Save to database
            ux_score = analysis_json.get('ux_confidence_score', {}).get('score', 0)
            complexity_score = analysis_json.get('complexity_score', 0)
            
            save_result(
                exploration_id=self.exploration_id,
                summary=analysis_json.get('summary', ''),
                positive_findings=analysis_json.get('positive', []),
                issues=analysis_json.get('issues', []),
                recommendations=analysis_json.get('recommendations', []),
                metrics={
                    'exploration_coverage': analysis_json.get('exploration_coverage', {}),
                    'navigation_metrics': analysis_json.get('navigation_metrics', {}),
                    'interaction_feedback': analysis_json.get('interaction_feedback', {}),
                    'visual_hierarchy': analysis_json.get('visual_hierarchy', {}),
                    'stress_test_results': analysis_json.get('stress_test_results', {}),
                    'graph_data': analysis_json.get('graph_data', {})
                },
                ux_score=ux_score,
                complexity_score=complexity_score,
                full_json=analysis_json
            )
            
            update_stage(
                self.exploration_id, stage_num, 'completed',
                json_data=analysis_json
            )
            
            self.stage_update(stage_num, stage_name, 'completed')
            
            return analysis_json
            
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse LLM response as JSON: {e}", 'error')
            update_stage(self.exploration_id, stage_num, 'failed', error_message=str(e))
            self.stage_update(stage_num, stage_name, 'failed')
            raise
        except Exception as e:
            self.log(f"Stage 4 failed: {e}", 'error')
            update_stage(self.exploration_id, stage_num, 'failed', error_message=str(e))
            self.stage_update(stage_num, stage_name, 'failed')
            raise
    
    def ensure_complete_json(self, data: dict) -> dict:
        """Ensure all required fields exist in the analysis JSON"""
        # Default structures
        defaults = {
            'summary': 'Analysis completed.',
            'app_metadata': {'screens_discovered': 0, 'total_interactions': 0, 'core_flows': []},
            'exploration_coverage': {'screens_discovered': 0, 'clickable_elements_found': 0, 'successful_actions_pct': 0, 'dead_elements_pct': 0, 'navigation_loops_detected': False},
            'navigation_metrics': {'avg_depth': 0, 'max_depth': 0, 'backtracking_frequency': 'low', 'orphan_screens': 0, 'label_action_match_score': 5, 'hub_screen_count': 0, 'architecture_quality': 'moderate'},
            'interaction_feedback': {'visible_feedback_rate_pct': 0, 'loading_state_presence_pct': 0, 'error_message_clarity': 5, 'silent_failures': 0, 'feedback_quality': 'moderate'},
            'visual_hierarchy': {'cta_visibility': 5, 'tap_target_compliance_pct': 0, 'icon_label_clarity': 5, 'hierarchy_issues': 0, 'clarity_rating': 'moderate'},
            'consistency': {'reused_patterns': [], 'inconsistent_labels': 0, 'action_placement_variance': 'low', 'pattern_violations': 0},
            'error_handling': {'preventable_errors': 0, 'recovery_paths_available': True, 'error_explanation_quality': 5, 'handling_rating': 'moderate'},
            'stress_test_results': {'breakability_score': 5, 'navigation_stability': 5, 'state_consistency': 5, 'error_resilience': 5, 'recovery_capability': 5, 'dark_patterns_found': 0, 'critical_bugs': 0},
            'positive': [],
            'issues': [],
            'dark_patterns': [],
            'recommendations': [],
            'ux_confidence_score': {'score': 5, 'factors': {'exploration_coverage': 5, 'interaction_consistency': 5, 'feedback_reliability': 5, 'recovery_robustness': 5, 'stress_resilience': 5}},
            'complexity_score': 5,
            'overall_rating': {'score': 5, 'grade': 'C', 'summary': 'Average UX quality'},
            'graph_data': {'radar_metrics': {'navigation': 5, 'feedback': 5, 'consistency': 5, 'accessibility': 5, 'error_handling': 5, 'visual_design': 5}, 'severity_distribution': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}, 'category_comparison': {'app_score': 5, 'category_average': 7}}
        }
        
        # Merge defaults with actual data
        for key, default_value in defaults.items():
            if key not in data:
                data[key] = default_value
            elif isinstance(default_value, dict):
                for subkey, subvalue in default_value.items():
                    if subkey not in data[key]:
                        data[key][subkey] = subvalue
        
        return data
    
    async def run_all_stages(self):
        """Run all 4 stages in sequence"""
        try:
            # Stage 1: Basic Exploration (5-25%)
            self.progress("Stage 1: Basic Exploration", 5)
            await self.run_agent_stage(1)
            self.progress("Stage 1 completed", 25)
            
            self.check_stop()
            
            # Stage 2: Persona Analysis (25-50%)
            self.progress("Stage 2: Persona Analysis", 30)
            await self.run_agent_stage(2)
            self.progress("Stage 2 completed", 50)
            
            self.check_stop()
            
            # Stage 3: Custom Navigation / Stress Test (50-75%)
            self.progress("Stage 3: Stress Testing", 55)
            await self.run_agent_stage(3)
            self.progress("Stage 3 completed", 75)
            
            self.check_stop()
            
            # Stage 4: Final Analysis (75-100%)
            self.progress("Stage 4: Final Analysis", 80)
            result = await self.run_final_analysis()
            self.progress("All stages completed!", 100)
            
            # Mark exploration as completed
            update_exploration_status(self.exploration_id, 'completed', 4)
            
            # Create comparison snapshot if save_to_memory is enabled
            # (This is handled by the calling code based on save_to_memory flag)
            
            return result
            
        except KeyboardInterrupt:
            update_exploration_status(self.exploration_id, 'stopped')
            raise
        except Exception as e:
            update_exploration_status(self.exploration_id, 'failed')
            raise


async def run_staged_exploration(
    app_name: str,
    category: str,
    persona: str,
    custom_navigation: str = None,
    max_depth: int = 6,
    save_to_memory: bool = False,
    progress_callback: Callable = None,
    log_callback: Callable = None,
    stage_callback: Callable = None,
    stop_flag = None
) -> dict:
    """
    Main entry point for running staged exploration
    Returns the final analysis JSON
    """
    # Initialize database
    init_db()
    
    # Create exploration record
    exploration_id = create_exploration(
        app_name=app_name,
        category=category,
        persona=persona,
        custom_navigation=custom_navigation,
        save_to_memory=save_to_memory
    )
    
    if log_callback:
        log_callback(f"Exploration ID: {exploration_id}", 'info')
    
    # Create and run the staged exploration
    runner = StageExplorationRunner(
        exploration_id=exploration_id,
        app_name=app_name,
        category=category,
        persona=persona,
        custom_navigation=custom_navigation,
        max_depth=max_depth,
        progress_callback=progress_callback,
        log_callback=log_callback,
        stage_callback=stage_callback,
        stop_flag=stop_flag
    )
    
    result = await runner.run_all_stages()
    
    # Create comparison snapshot if save_to_memory
    if save_to_memory:
        create_comparison_snapshot(exploration_id)
        if log_callback:
            log_callback("Results saved to memory for future comparison", 'success')
    
    return result


# Backward compatibility - keep old function signature working
async def run_exploration_with_category(app_name, category, max_depth, progress_callback, log_callback=None, stop_flag=None):
    """Legacy function for backward compatibility"""
    return await run_staged_exploration(
        app_name=app_name,
        category=category,
        persona='UX Designer',  # Default persona
        max_depth=max_depth,
        progress_callback=progress_callback,
        log_callback=log_callback,
        stop_flag=stop_flag
    )
