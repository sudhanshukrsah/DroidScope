"""
Stage-based exploration runner with persona support and database storage
"""
import asyncio
import json
import os
import sys
import threading
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
from dotenv import load_dotenv
from llama_index.llms.openai_like import OpenAILike
from droidrun import DroidAgent
from droidrun.config_manager import DroidrunConfig
from utils import load_prompt, format_prompt, read_markdown_file, find_stage_markdown_files, cleanup_stage_files
from database import (
    create_exploration, update_exploration_status, update_exploration_stage,
    create_stage, update_stage, get_stages, save_result, get_setting
)

load_dotenv()


class LogCapture:
    """Captures stdout/stderr - accumulates for 3 seconds then sends via callback"""
    def __init__(self, log_callback, log_type='info'):
        self.log_callback = log_callback
        self.log_type = log_type
        self.text_buffer = ""
        self.last_flush_time = datetime.now()
        self.flush_interval = 3  # Reduced to 3 seconds for better responsiveness
        self.original_stdout = sys.__stdout__
        self.lock = threading.Lock()
        self.running = True
        
        # Start background flush thread
        self.flush_thread = threading.Thread(target=self._auto_flush_loop, daemon=True)
        self.flush_thread.start()
    
    def _auto_flush_loop(self):
        """Flush buffer every 3 seconds"""
        while self.running:
            try:
                threading.Event().wait(self.flush_interval)
                with self.lock:
                    if self.text_buffer.strip():
                        self._send_buffer()
            except Exception as e:
                if self.original_stdout:
                    self.original_stdout.write(f"[LogCapture] Flush error: {e}\n")
                    self.original_stdout.flush()
    
    def _send_buffer(self):
        """Send accumulated buffer - must be called with lock held"""
        try:
            if self.text_buffer.strip() and self.log_callback:
                self.log_callback(self.text_buffer.strip(), self.log_type)
                
                # Server console log
                if self.original_stdout:
                    self.original_stdout.write(f"[BATCH-{self.log_type.upper()}] {self.text_buffer}")
                    self.original_stdout.flush()
                
                self.text_buffer = ""
                self.last_flush_time = datetime.now()
        except Exception as e:
            if self.original_stdout:
                self.original_stdout.write(f"[LogCapture] Send error: {e}\n")
                self.original_stdout.flush()
            self.text_buffer = ""  # Clear buffer on error
    
    def write(self, message):
        try:
            with self.lock:
                self.text_buffer += message
        except Exception:
            pass  # Silently fail to avoid breaking the agent
        return len(message)
    
    def flush(self):
        try:
            with self.lock:
                self._send_buffer()
            if self.original_stdout:
                self.original_stdout.flush()
        except Exception:
            pass
    
    def isatty(self):
        return False
    
    def close(self):
        """Flush and stop"""
        self.running = False
        try:
            with self.lock:
                self._send_buffer()
        except Exception:
            pass


STAGE_NAMES = {
    1: 'Basic Exploration',
    2: 'Persona Analysis',
    3: 'Stress Testing',
    4: 'Final Analysis'
}

PERSONA_SLUGS = {
    'UX Designer': 'ux_designer',
    'QA Engineer': 'qa_engineer',
    'Product Manager': 'product_manager'
}


class StageExplorationRunner:
    """Runs 4-stage exploration with persona support"""
    
    def __init__(self, request_id, app_name, category, persona, custom_navigation='',
                 max_depth=6, save_to_memory=True, progress_callback=None, 
                 log_callback=None, stage_callback=None, stop_flag=None):
        self.request_id = request_id
        self.app_name = app_name
        self.category = category
        self.persona = persona
        self.persona_slug = PERSONA_SLUGS.get(persona, 'ux_designer')
        self.custom_navigation = custom_navigation
        self.max_depth = max_depth
        self.save_to_memory = save_to_memory
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.stage_callback = stage_callback
        self.stop_flag = stop_flag
        self.exploration_id = None
        self.current_stage = 0
        self.stage_results = {}
        
        # Setup LLM
        self.api_key = get_setting('api_key') or os.getenv("API_KEY")
        self.model = get_setting('llm_model') or os.getenv("LLM_MODEL", "mistralai/devstral-2512:free")
        self.api_base = get_setting('api_base') or os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
        
        # NVIDIA API requires model-specific endpoints
        final_api_base = self.api_base
        if "nvidia.com" in self.api_base:
            # For NVIDIA API, construct model-specific endpoint
            # Format: https://integrate.api.nvidia.com/v1/{model}
            base_url = self.api_base.rstrip('/v1').rstrip('/')
            final_api_base = f"{base_url}/v1"
            print(f"[INFO] Using NVIDIA model endpoint: {final_api_base}")
        
        self.llm = OpenAILike(
            model=self.model,
            api_base=final_api_base,
            api_key=self.api_key,
            temperature=0.15,
            is_chat_model=True
        )
    
    def log(self, message, log_type='info'):
        """Send log message"""
        if self.log_callback:
            self.log_callback(message, log_type)
        print(f"[{log_type.upper()}] {message}")
    
    def progress(self, message, percentage):
        """Send progress update"""
        if self.progress_callback:
            self.progress_callback(message, percentage)
    
    def stage_update(self, stage_num, status, message=''):
        """Send stage status update"""
        if self.stage_callback:
            self.stage_callback(stage_num, status, message)
    
    def check_stop(self):
        """Check if stop was requested"""
        if self.stop_flag and self.stop_flag.is_set():
            self.log("Agent execution stopped by user", 'warning')
            raise KeyboardInterrupt("Agent stopped by user request")
    
    async def run(self):
        """Run all 4 stages"""
        try:
            # Create exploration record
            self.exploration_id = create_exploration(
                self.request_id, self.app_name, self.category,
                self.persona, self.custom_navigation, self.max_depth
            )
            self.log(f"Created exploration #{self.exploration_id}", 'info')
            
            # Clean up any previous stage files
            cleanup_stage_files()
            
            # Stage 1: Basic Exploration
            self.check_stop()
            success = await self.run_stage_1()
            if not success:
                self.fail_exploration("Stage 1 failed")
                return False
            
            # Stage 2: Persona Analysis
            self.check_stop()
            success = await self.run_stage_2()
            if not success:
                self.fail_exploration("Stage 2 failed")
                return False
            
            # Stage 3: Stress Testing
            self.check_stop()
            success = await self.run_stage_3()
            if not success:
                self.fail_exploration("Stage 3 failed")
                return False
            
            # Stage 4: Final Analysis
            self.check_stop()
            success = await self.run_stage_4()
            if not success:
                self.fail_exploration("Stage 4 failed")
                return False
            
            # After all stages complete, save JSON results to database
            self.check_stop()
            self.log("Saving results to database...", 'info')
            self.progress("Saving results to database...", 95)
            
            if await self.save_results_to_database():
                # Mark exploration as completed
                update_exploration_status(self.exploration_id, 'completed')
                self.progress("Exploration completed successfully!", 100)
                self.log("All stages completed successfully!", 'success')
                return True
            else:
                self.fail_exploration("Failed to save results to database")
                return False
            
        except KeyboardInterrupt:
            self.fail_exploration("Stopped by user")
            return False
        except Exception as e:
            self.fail_exploration(str(e))
            raise
    
    def fail_exploration(self, error_message):
        """Mark exploration as failed"""
        if self.exploration_id:
            update_exploration_status(self.exploration_id, 'failed', error_message)
        self.log(f"Exploration failed: {error_message}", 'error')
        self.progress(f"Failed: {error_message}", -1)
    
    async def save_results_to_database(self):
        """Read ux_analysis_blocks.json and save to database"""
        try:
            json_filename = 'ux_analysis_blocks.json'
            
            # Check if file exists
            if not os.path.exists(json_filename):
                self.log(f"Error: {json_filename} not found in {os.getcwd()}", 'error')
                return False
            
            # Read JSON file
            with open(json_filename, 'r', encoding='utf-8') as f:
                analysis_json = json.load(f)
            
            self.log(f"Read analysis from {json_filename} ({len(json.dumps(analysis_json))} bytes)", 'info')
            
            # Extract UX score
            ux_score = analysis_json.get('ux_confidence_score', {}).get('score', 5)
            
            # Validate exploration_id
            if not self.exploration_id:
                self.log("Error: No exploration_id set, cannot save to database", 'error')
                return False
            
            # Save to database
            self.log(f"Saving to database: exploration_id={self.exploration_id}, ux_score={ux_score}", 'info')
            save_result(self.exploration_id, analysis_json, ux_score)
            
            # Verify save was successful
            from database import get_result
            verify = get_result(self.exploration_id)
            if verify:
                self.log(f"✅ Results verified in database (exploration_id: {self.exploration_id})", 'success')
                return True
            else:
                self.log(f"⚠️ Save completed but verification failed for exploration_id: {self.exploration_id}", 'warning')
                return True  # Still return True as save_result was called
            
        except json.JSONDecodeError as e:
            self.log(f"Error parsing JSON file: {e}", 'error')
            return False
        except Exception as e:
            self.log(f"Error saving to database: {e}", 'error')
            return False
    
    async def run_stage_1(self):
        """Stage 1: Basic Exploration"""
        stage_num = 1
        self.current_stage = stage_num
        update_exploration_stage(self.exploration_id, stage_num)
        
        self.log(f"Starting Stage 1: Basic Exploration", 'info')
        self.stage_update(stage_num, 'running', 'Starting basic exploration...')
        self.progress("Stage 1: Basic Exploration", 5)
        
        # Create stage record
        stage_id = create_stage(self.exploration_id, stage_num, STAGE_NAMES[stage_num])
        
        try:
            # Load and format prompt
            prompt_template = load_prompt('stage1_basic_exploration')
            goal = format_prompt(prompt_template, app_name=self.app_name, category=self.category)
            
            # Run agent
            success, reason = await self._run_agent(goal, stage_num, stage_id)
            
            if success:
                # Extract markdown from reason or read from file
                content = read_markdown_file('stage1_basic_exploration.md')
                
                # If no file was created, use the reason as content
                if not content and reason:
                    content = reason
                    # Save to file for consistency
                    with open('stage1_basic_exploration.md', 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.log("Created markdown file from agent output", 'info')
                
                if content:
                    self.stage_results[stage_num] = content
                    update_stage(stage_id, 'completed', content)
                    self.stage_update(stage_num, 'completed', 'Basic exploration complete')
                    self.log("Stage 1 completed successfully", 'success')
                    return True
                else:
                    update_stage(stage_id, 'failed', error_message='No markdown output generated')
                    self.stage_update(stage_num, 'failed', 'No output generated')
                    return False
            else:
                update_stage(stage_id, 'failed', error_message='Agent execution failed')
                self.stage_update(stage_num, 'failed', 'Agent failed')
                return False
                
        except Exception as e:
            update_stage(stage_id, 'failed', error_message=str(e))
            self.stage_update(stage_num, 'failed', str(e))
            self.log(f"Stage 1 error: {e}", 'error')
            return False
    
    async def run_stage_2(self):
        """Stage 2: Persona Analysis"""
        stage_num = 2
        self.current_stage = stage_num
        update_exploration_stage(self.exploration_id, stage_num)
        
        self.log(f"Starting Stage 2: {self.persona} Analysis", 'info')
        self.stage_update(stage_num, 'running', f'Starting {self.persona} analysis...')
        self.progress(f"Stage 2: {self.persona} Analysis", 25)
        
        stage_id = create_stage(self.exploration_id, stage_num, f'{STAGE_NAMES[stage_num]} ({self.persona})')
        
        try:
            # Load persona prompt
            persona_prompt = load_prompt(f'persona_{self.persona_slug}')
            persona_prompt = format_prompt(persona_prompt, app_name=self.app_name, category=self.category)
            
            # Load stage prompt with custom navigation if provided
            stage_template = load_prompt('stage2_persona_analysis')
            
            custom_instruction = ""
            if self.custom_navigation:
                custom_instruction = f"Follow these custom navigation instructions: {self.custom_navigation}"
            else:
                custom_instruction = "No custom navigation provided. Explore naturally as the persona would."
            
            goal = format_prompt(
                stage_template,
                app_name=self.app_name,
                category=self.category,
                persona=self.persona,
                persona_slug=self.persona_slug,
                max_depth=self.max_depth,
                custom_navigation_instruction=custom_instruction
            )
            
            # Combine prompts
            full_goal = f"{persona_prompt}\n\n{goal}"
            
            success, reason = await self._run_agent(full_goal, stage_num, stage_id)
            
            if success:
                filename = f'stage2_{self.persona_slug}_analysis.md'
                content = read_markdown_file(filename)
                
                # If no file was created, use the reason as content
                if not content and reason:
                    content = reason
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.log("Created markdown file from agent output", 'info')
                
                if content:
                    self.stage_results[stage_num] = content
                    update_stage(stage_id, 'completed', content)
                    self.stage_update(stage_num, 'completed', f'{self.persona} analysis complete')
                    self.log("Stage 2 completed successfully", 'success')
                    return True
                else:
                    update_stage(stage_id, 'failed', error_message='No markdown output generated')
                    self.stage_update(stage_num, 'failed', 'No output generated')
                    return False
            else:
                update_stage(stage_id, 'failed', error_message='Agent execution failed')
                self.stage_update(stage_num, 'failed', 'Agent failed')
                return False
                
        except Exception as e:
            update_stage(stage_id, 'failed', error_message=str(e))
            self.stage_update(stage_num, 'failed', str(e))
            self.log(f"Stage 2 error: {e}", 'error')
            return False
    
    async def run_stage_3(self):
        """Stage 3: Stress Testing"""
        stage_num = 3
        self.current_stage = stage_num
        update_exploration_stage(self.exploration_id, stage_num)
        
        self.log("Starting Stage 3: Stress Testing", 'info')
        self.stage_update(stage_num, 'running', 'Starting stress testing...')
        self.progress("Stage 3: Stress Testing", 50)
        
        stage_id = create_stage(self.exploration_id, stage_num, STAGE_NAMES[stage_num])
        
        try:
            # Load prompt with custom navigation if provided
            prompt_template = load_prompt('stage3_stress_exploration')
            
            custom_instruction = ""
            if self.custom_navigation:
                custom_instruction = f"Follow these custom navigation instructions: {self.custom_navigation}"
            else:
                custom_instruction = "No custom navigation provided. Simulate imperfect user behavior with random navigation and mistaps."
            
            goal = format_prompt(
                prompt_template,
                app_name=self.app_name,
                category=self.category,
                custom_navigation_instruction=custom_instruction
            )
            
            success, reason = await self._run_agent(goal, stage_num, stage_id)
            
            if success:
                content = read_markdown_file('stage3_stress_exploration.md')
                
                # If no file was created, use the reason as content
                if not content and reason:
                    content = reason
                    with open('stage3_stress_exploration.md', 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.log("Created markdown file from agent output", 'info')
                
                if content:
                    self.stage_results[stage_num] = content
                    update_stage(stage_id, 'completed', content)
                    self.stage_update(stage_num, 'completed', 'Stress testing complete')
                    self.log("Stage 3 completed successfully", 'success')
                    return True
                else:
                    update_stage(stage_id, 'failed', error_message='No markdown output generated')
                    self.stage_update(stage_num, 'failed', 'No output generated')
                    return False
            else:
                update_stage(stage_id, 'failed', error_message='Agent execution failed')
                self.stage_update(stage_num, 'failed', 'Agent failed')
                return False
                
        except Exception as e:
            update_stage(stage_id, 'failed', error_message=str(e))
            self.stage_update(stage_num, 'failed', str(e))
            self.log(f"Stage 3 error: {e}", 'error')
            return False
    
    async def run_stage_4(self):
        """Stage 4: Final Analysis - LLM synthesizes all data"""
        stage_num = 4
        self.current_stage = stage_num
        update_exploration_stage(self.exploration_id, stage_num)
        
        self.log("Starting Stage 4: Final Analysis", 'info')
        self.stage_update(stage_num, 'running', 'Generating final analysis...')
        self.progress("Stage 4: Final Analysis", 75)
        
        stage_id = create_stage(self.exploration_id, stage_num, STAGE_NAMES[stage_num])
        
        try:
            # Collect all stage data
            all_stage_data = find_stage_markdown_files()
            
            if len(all_stage_data) < 3:
                self.log("Warning: Not all stages have data", 'warning')
            
            # Combine all stage content
            combined_content = ""
            for stage_n in sorted(all_stage_data.keys()):
                combined_content += f"\n\n=== STAGE {stage_n}: {STAGE_NAMES.get(stage_n, 'Unknown')} ===\n\n"
                combined_content += all_stage_data[stage_n]['content']
            
            # Generate final analysis using LLM
            analysis_prompt = self._build_analysis_prompt(combined_content)
            
            self.log("Sending data to LLM for final analysis...", 'info')
            response = self.llm.complete(analysis_prompt)
            analysis_text = response.text.strip()
            
            # Parse JSON response
            if analysis_text.startswith("```json"):
                analysis_text = analysis_text.split("```json")[1].split("```")[0].strip()
            elif analysis_text.startswith("```"):
                analysis_text = analysis_text.split("```")[1].split("```")[0].strip()
            
            analysis_json = json.loads(analysis_text)
            
            # Ensure required fields
            analysis_json = self._ensure_analysis_fields(analysis_json)
            
            # Save to file - DB save happens after all stages complete
            json_filename = 'ux_analysis_blocks.json'
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(analysis_json, f, indent=2)
            
            self.log(f"Analysis saved to {json_filename}", 'success')
            
            update_stage(stage_id, 'completed', json.dumps(analysis_json))
            self.stage_update(stage_num, 'completed', 'Final analysis complete')
            self.log("Stage 4 completed successfully", 'success')
            
            return True
            
        except json.JSONDecodeError as e:
            update_stage(stage_id, 'failed', error_message=f'JSON parse error: {e}')
            self.stage_update(stage_num, 'failed', 'Failed to parse analysis')
            self.log(f"Stage 4 JSON error: {e}", 'error')
            return False
        except Exception as e:
            update_stage(stage_id, 'failed', error_message=str(e))
            self.stage_update(stage_num, 'failed', str(e))
            self.log(f"Stage 4 error: {e}", 'error')
            return False
    
    async def _run_agent(self, goal, stage_num, stage_id):
        """Run DroidAgent with given goal"""
        # Setup stdout/stderr capture for this agent run
        stdout_capture = LogCapture(self.log_callback, 'info') if self.log_callback else None
        stderr_capture = LogCapture(self.log_callback, 'error') if self.log_callback else None
        
        # Save original stdout/stderr
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            self.log(f"Initializing agent for stage {stage_num}...", 'info')
            
            # Replace stdout/stderr with our captures
            if stdout_capture:
                sys.stdout = stdout_capture
            if stderr_capture:
                sys.stderr = stderr_capture
            
            config = DroidrunConfig()
            # Set max_steps based on stage (stress test gets less)
            if stage_num == 3:  # Stress test
                config.agent.max_steps = 100  # Limit stress test actions
            else:
                config.agent.max_steps = 200
            
            agent = DroidAgent(
                goal=goal,
                config=config,
                llms=self.llm,
            )
            
            self.log(f"Agent running for stage {stage_num}...", 'info')
            
            # Run agent with periodic stop checking
            agent_task = agent.run()
            result_future = asyncio.ensure_future(agent_task)
            
            while not result_future.done():
                # Check stop flag every 2 seconds
                await asyncio.sleep(2)
                if self.stop_flag and self.stop_flag.is_set():
                    self.log("Stop requested - cancelling agent", 'warning')
                    result_future.cancel()
                    try:
                        await result_future
                    except asyncio.CancelledError:
                        self.log("Agent cancelled successfully", 'warning')
                        return False, 'Stopped by user'
            
            result = await result_future
            
            if result is None:
                return False, 'Stopped by user'
            
            success = getattr(result, 'success', False)
            reason = getattr(result, 'reason', '')
            
            self.log(f"Agent stage {stage_num} completed: {'✅' if success else '❌'}", 
                     'success' if success else 'warning')
            
            return success, reason
            
        except asyncio.CancelledError:
            self.log(f"Agent stage {stage_num} cancelled by user", 'warning')
            return False, 'Stopped by user'
        except KeyboardInterrupt:
            self.log(f"Agent stage {stage_num} interrupted by user", 'warning')
            return False, 'Stopped by user'
        except Exception as e:
            self.log(f"Agent error in stage {stage_num}: {e}", 'error')
            return False, ''
        finally:
            # Restore original stdout/stderr
            try:
                sys.stdout = original_stdout
                sys.stderr = original_stderr
            except Exception as e:
                if original_stdout:
                    original_stdout.write(f"[ERROR] Failed to restore stdout/stderr: {e}\n")
            
            # Close captures to flush remaining buffers
            if stdout_capture:
                try:
                    stdout_capture.close()
                except Exception as e:
                    if original_stdout:
                        original_stdout.write(f"[ERROR] Failed to close stdout capture: {e}\n")
            if stderr_capture:
                try:
                    stderr_capture.close()
                except Exception as e:
                    if original_stdout:
                        original_stdout.write(f"[ERROR] Failed to close stderr capture: {e}\n")
    
    def _build_analysis_prompt(self, combined_content):
        """Build the final analysis prompt"""
        return f'''You are analyzing UX exploration data for {self.app_name}, a {self.category} app.
The exploration was conducted from a {self.persona} perspective.

Below is the combined data from all exploration stages:

{combined_content}

Based on this data, generate a comprehensive UX analysis report in JSON format with the following structure:
{{
    "summary": "2-3 sentence executive summary",
    "positive": [
        {{"aspect": "string", "description": "string", "location": "string"}}
    ],
    "issues": [
        {{"category": "string", "description": "string", "severity": "High|Medium|Low", "location": "string", "impact": "string"}}
    ],
    "recommendations": [
        {{"recommendation": "string", "priority": "High|Medium|Low", "rationale": "string", "effort": "High|Medium|Low"}}
    ],
    "app_metadata": {{
        "screens_discovered": number,
        "total_interactions": number,
        "core_flows": ["string"]
    }},
    "exploration_coverage": {{
        "screens_discovered": number,
        "clickable_elements_found": number,
        "successful_actions_pct": number,
        "dead_elements_pct": number,
        "navigation_loops_detected": boolean
    }},
    "navigation_metrics": {{
        "avg_depth": number,
        "max_depth": number,
        "backtracking_frequency": "low|medium|high",
        "orphan_screens": number,
        "hub_screen_count": number,
        "architecture_quality": "poor|moderate|good|excellent"
    }},
    "interaction_feedback": {{
        "visible_feedback_rate_pct": number,
        "loading_state_presence_pct": number,
        "error_message_clarity": number,
        "silent_failures": number,
        "feedback_quality": "poor|moderate|good|excellent"
    }},
    "visual_hierarchy": {{
        "cta_visibility": number,
        "tap_target_compliance_pct": number,
        "icon_label_clarity": number,
        "clarity_rating": "poor|moderate|good|excellent"
    }},
    "consistency": {{
        "reused_patterns": ["string"],
        "inconsistent_labels": number,
        "action_placement_variance": "low|medium|high",
        "pattern_violations": number
    }},
    "error_handling": {{
        "preventable_errors": number,
        "recovery_paths_available": boolean,
        "error_explanation_quality": number,
        "handling_rating": "poor|moderate|good|excellent"
    }},
    "ux_confidence_score": {{
        "score": number,
        "factors": {{
            "exploration_coverage": number,
            "interaction_consistency": number,
            "feedback_reliability": number,
            "recovery_robustness": number
        }}
    }},
    "complexity_score": number,
    "dark_patterns_detected": ["string"],
    "actor_analysis": [
        {{
            "actor_type": "string (e.g., New User, Power User, Content Creator)",
            "needs_score": number,
            "pain_points": ["string"],
            "relevant_features": ["string"]
        }}
    ],
    "persona_insights": {{
        "persona": "{self.persona}",
        "key_observations": ["string"],
        "alignment_score": number
    }}
}}

IMPORTANT: Generate the JSON based ONLY on the actual data provided above. Do not invent or assume data that was not observed. If a metric cannot be determined, use reasonable defaults.

Return only valid JSON, no markdown code blocks.'''
    
    def _ensure_analysis_fields(self, data):
        """Ensure all required fields exist with defaults"""
        defaults = {
            'summary': 'UX analysis completed.',
            'positive': [],
            'issues': [],
            'recommendations': [],
            'app_metadata': {'screens_discovered': 0, 'total_interactions': 0, 'core_flows': []},
            'exploration_coverage': {'screens_discovered': 0, 'clickable_elements_found': 0, 'successful_actions_pct': 0, 'dead_elements_pct': 0, 'navigation_loops_detected': False},
            'navigation_metrics': {'avg_depth': 0, 'max_depth': 0, 'backtracking_frequency': 'low', 'orphan_screens': 0, 'hub_screen_count': 0, 'architecture_quality': 'moderate'},
            'interaction_feedback': {'visible_feedback_rate_pct': 0, 'loading_state_presence_pct': 0, 'error_message_clarity': 5, 'silent_failures': 0, 'feedback_quality': 'moderate'},
            'visual_hierarchy': {'cta_visibility': 5, 'tap_target_compliance_pct': 0, 'icon_label_clarity': 5, 'clarity_rating': 'moderate'},
            'consistency': {'reused_patterns': [], 'inconsistent_labels': 0, 'action_placement_variance': 'low', 'pattern_violations': 0},
            'error_handling': {'preventable_errors': 0, 'recovery_paths_available': False, 'error_explanation_quality': 5, 'handling_rating': 'moderate'},
            'ux_confidence_score': {'score': 5, 'factors': {'exploration_coverage': 5, 'interaction_consistency': 5, 'feedback_reliability': 5, 'recovery_robustness': 5}},
            'complexity_score': 5,
            'dark_patterns_detected': [],
            'actor_analysis': [],
            'persona_insights': {'persona': self.persona, 'key_observations': [], 'alignment_score': 5}
        }
        
        for key, default_value in defaults.items():
            if key not in data:
                data[key] = default_value
            elif isinstance(default_value, dict):
                for sub_key, sub_default in default_value.items():
                    if sub_key not in data[key]:
                        data[key][sub_key] = sub_default
        
        return data


async def run_staged_exploration(request_id, app_name, category, persona, custom_navigation='',
                                  max_depth=6, save_to_memory=True, progress_callback=None,
                                  log_callback=None, stage_callback=None, stop_flag=None):
    """Main entry point for staged exploration"""
    runner = StageExplorationRunner(
        request_id=request_id,
        app_name=app_name,
        category=category,
        persona=persona,
        custom_navigation=custom_navigation,
        max_depth=max_depth,
        save_to_memory=save_to_memory,
        progress_callback=progress_callback,
        log_callback=log_callback,
        stage_callback=stage_callback,
        stop_flag=stop_flag
    )
    
    return await runner.run()
