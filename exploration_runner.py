"""
Exploration runner with category context and progress tracking
"""
import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from llama_index.llms.openai_like import OpenAILike
from droidrun import DroidAgent
from droidrun.config_manager import DroidrunConfig
from utils import load_prompt, format_prompt
from ux_analyzer import UXAnalyzer

load_dotenv()


def generate_category_context(app_name, category):
    """Generate category-specific context for UX testing"""
    api_key = os.getenv("API_KEY")
    
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
- Critical features users expect in {category}
- Industry-specific UI patterns for {category}
- What makes excellent UX in {category} applications

Return 3-4 concise sentences with:
1. Key navigation flows to explore
2. Critical features to find
3. UX patterns to validate

Focus on structural navigation, not user psychology. Be specific to {category} apps."""

    try:
        response = llm.complete(category_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating category context: {e}")
        return f"Standard UX testing for {category} application focusing on navigation structure and feature discoverability."


async def run_exploration_with_category(app_name, category, max_depth, progress_callback, log_callback=None):
    """Run exploration with category context"""
    
    def log(message, log_type='info'):
        """Helper to send log if callback provided"""
        if log_callback:
            log_callback(message, log_type)
        print(f"[{log_type.upper()}] {message}")
    
    try:
        log(f"Initializing exploration for {app_name}", 'info')
        progress_callback("Generating category-specific testing context...", 10)
        
        # Generate category context
        log(f"Generating {category} category context...", 'info')
        category_context = generate_category_context(app_name, category)
        log(f"Category context generated: {len(category_context)} chars", 'success')
        
        progress_callback("Loading exploration parameters...", 15)
        log("Loading agent goal template", 'info')
        
        # Load and format agent goal
        agent_goal_template = load_prompt('agent_goal')
        agent_goal = format_prompt(agent_goal_template, app_name=app_name)
        
        # Enhance goal with category context and depth
        enhanced_goal = f"""{agent_goal}

CATEGORY-SPECIFIC CONTEXT ({category}):
{category_context}

EXPLORATION CONSTRAINTS:
- Maximum navigation depth: {max_depth} levels
- Focus on {category}-specific features and flows
- Document both positive UX patterns and issues

Remember to identify what works well in addition to problems."""
        
        log(f"Agent goal enhanced with category context and depth={max_depth}", 'success')
        progress_callback(f"Initializing DroidRun agent for {app_name}...", 20)
        
        # Setup LLM and config
        log("Setting up LLM configuration", 'info')
        api_key = os.getenv("API_KEY")
        llm = OpenAILike(
            model="mistralai/devstral-2512:free",
            api_base="https://openrouter.ai/api/v1",
            api_key=api_key,
            temperature=0.2
        )
        log("LLM initialized: mistralai/devstral-2512:free", 'success')
        
        log("Creating DroidRun configuration", 'info')
        config = DroidrunConfig()
        config.agent.max_steps = max_depth * 15
        log(f"Max steps set to {config.agent.max_steps}", 'info')
        
        progress_callback("Creating exploration agent...", 25)
        log("Creating DroidAgent instance", 'info')
        
        # Create agent
        agent = DroidAgent(
            goal=enhanced_goal,
            config=config,
            llms=llm,
        )
        log("DroidAgent created successfully", 'success')
        
        progress_callback(f"Starting UX exploration of {app_name}...", 30)
        log(f"Beginning autonomous exploration (max depth: {max_depth})", 'info')
        
        # Run exploration
        log("Agent.run() started - this may take several minutes", 'info')
        result = await agent.run()
        log("Agent.run() completed", 'success')
        
        progress_callback("Exploration complete. Processing results...", 60)
        log("Processing exploration results", 'info')
        
        # Save results
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_lines = []
        
        success_status = getattr(result, 'success', None)
        log(f"Exploration success status: {success_status}", 'success' if success_status else 'warning')
        
        output_lines.append(f"Timestamp: {timestamp}")
        output_lines.append(f"App: {app_name}")
        output_lines.append(f"Category: {category}")
        output_lines.append(f"Max Depth: {max_depth}")
        output_lines.append(f"Success: {success_status}")
        output_lines.append("-" * 50)
        
        if hasattr(result, 'final_answer') and result.final_answer:
            log("Final answer captured from agent", 'success')
            output_lines.append(f"Final Answer:\n{result.final_answer}")
            output_lines.append("-" * 50)
        
        if hasattr(result, 'structured_output') and result.structured_output:
            try:
                log("Serializing structured output", 'info')
                structured_json = result.structured_output.model_dump_json(indent=2)
                output_lines.append(f"Structured Output:\n{structured_json}")
                
                with open("exploration_output.json", "w", encoding="utf-8") as json_file:
                    json_file.write(structured_json)
                log("Structured output saved: exploration_output.json", 'success')
                output_lines.append("-" * 50)
                output_lines.append("Structured output saved to: exploration_output.json")
            except Exception as e:
                log(f"Error serializing structured output: {str(e)}", 'error')
                output_lines.append(f"Error serializing structured output: {str(e)}")
        
        if hasattr(result, 'reason') and result.reason:
            output_lines.append(f"Reason: {result.reason}")
        
        output_text = "\n".join(output_lines)
        with open("agent_result.txt", "w", encoding="utf-8") as txt_file:
            txt_file.write(output_text)
        log("Results saved: agent_result.txt", 'success')
        
        progress_callback("Results saved. Starting UX analysis...", 70)
        
        # Run UX analysis
        if success_status:
            log("Starting UX analysis pipeline", 'info')
            analyzer = UXAnalyzer(api_key=api_key)
            analyzer.run_analysis_for_web(
                report_path="agent_result.txt",
                category=category,
                progress_callback=progress_callback,
                log_callback=log
            )
        else:
            error_reason = result.reason if hasattr(result, 'reason') else 'Unknown error'
            log(f"Exploration failed: {error_reason}", 'error')
            progress_callback(f"Exploration failed: {error_reason}", -1)
            
    except Exception as e:
        log(f"Critical error: {str(e)}", 'error')
        progress_callback(f"Error during exploration: {str(e)}", -1)
        raise
