from droidrun import DroidAgent
from droidrun.config_manager import DroidrunConfig
from llama_index.llms.openai_like import OpenAILike
import asyncio
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
import json
from dotenv import load_dotenv
import os
from ux_analyzer import UXAnalyzer

load_dotenv()

# Set your OpenRouter API key

openrouter_key = os.getenv("API_KEY")

# Pydantic Model 
class Screen(BaseModel):
    id: str = Field(description="Unique identifier or hash of the screen")
    title: str = Field(description="Human-readable name of the screen")
    depth: int = Field(description="Depth level in navigation flow")


class Transition(BaseModel):
    from_screen: str = Field(description="Source screen ID")
    to_screen: str = Field(description="Destination screen ID")
    action: str = Field(description="UI action that caused the transition")


class UXFlow(BaseModel):
    screens: List[Screen] = Field(description="List of discovered screens")
    transitions: List[Transition] = Field(description="Navigation transitions")
    total_screens: int = Field(description="Total number of unique screens")
    max_depth: int = Field(description="Maximum depth explored")
    exploration_time: float = Field(description="Exploration time in seconds")


# Create OpenRouter LLM with Mistral model
llm = OpenAILike(
    model="mistralai/devstral-2512:free",  # or other Mistral models
    api_base="https://openrouter.ai/api/v1",
    api_key=openrouter_key,
    temperature=0.2
)

config = DroidrunConfig()
config.agent.max_steps = 110

agent = DroidAgent(
    goal=('''Explore the Instagram application by performing visible UI interactions only.
Open primary tabs, menus, profiles, and settings that are explicitly present on the screen.
Interact using taps, scrolls, and long-presses only when a visible UI affordance exists.

Do not infer user intent, behavior, engagement, or opinions.
Do not describe how users feel or why a screen exists.
Do not assume functionality beyond what is directly observable.

Avoid destructive or irreversible actions such as logout, account deletion, blocking, posting, liking, commenting, or sending messages.

Navigate the interface to discover distinct UI states reachable through explicit taps, long-presses, or menu selections.
Prefer breadth-first exploration before deeper navigation, but stop if no new UI states appear.

Do not attempt to complete tasks, workflows, or goals.
Do not follow content endlessly (e.g., infinite scrolling beyond context discovery).

For each distinct UI state:
- Record it as a screen only when the visible layout or controls change.
- Assign a unique identifier.
- Name the screen using visible labels or UI elements only (tabs, headers, menu titles).
- Assign navigation depth relative to the starting screen.

For each navigation event:
- Record the source screen identifier.
- Record the destination screen identifier.
- Record the exact user action performed (e.g., "Tapped Reels tab", "Opened profile menu").

Continue exploration until a reasonable structural coverage is reached or no new screens are discovered.

Generate a markdown report containing:
- A summary with total screens discovered, maximum depth, and exploration time.
- A table of screens with identifiers, names, and depths.
- A table of transitions with source, destination, and action.

Export the generated report to a `.md` file.
Output markdown only.'''
),
    config=config,
    llms=llm,  # Single LLM for all agents
    
    
)

async def main():
    result = await agent.run()
    
    # Prepare output data
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_lines = []
    
    try:
        # Capture success status
        success_status = getattr(result, 'success', None)
        output_lines.append(f"Timestamp: {timestamp}")
        output_lines.append(f"Success: {success_status}")
        output_lines.append("-" * 50)
        
        # Capture final answer if available
        if hasattr(result, 'final_answer') and result.final_answer:
            output_lines.append(f"Final Answer:\n{result.final_answer}")
            output_lines.append("-" * 50)
        
        # Capture structured output if available
        if hasattr(result, 'structured_output') and result.structured_output:
            try:
                structured_json = result.structured_output.model_dump_json(indent=2)
                output_lines.append(f"Structured Output:\n{structured_json}")
                
                # Also save structured output as separate JSON file
                with open("discord_ux_flow.json", "w", encoding="utf-8") as json_file:
                    json_file.write(structured_json)
                output_lines.append("-" * 50)
                output_lines.append("Structured output saved to: discord_ux_flow.json")
            except Exception as e:
                output_lines.append(f"Error serializing structured output: {str(e)}")
        
        # Capture reason if available
        if hasattr(result, 'reason') and result.reason:
            output_lines.append(f"Reason: {result.reason}")
        
        # Write to text file
        output_text = "\n".join(output_lines)
        with open("agent_result.txt", "w", encoding="utf-8") as txt_file:
            txt_file.write(output_text)
        
        print(f"Success: {success_status}")
        print(f"Results saved to: agent_result.txt")
        
        # Run UX Analysis if exploration was successful
        if success_status:
            print("\n" + "="*60)
            print("Starting UX Analysis...")
            print("="*60)
            try:
                analyzer = UXAnalyzer(api_key=openrouter_key)
                analyzer.run_analysis(
                    report_path="agent_result.txt",
                    output_path="ux_analysis_report.html"
                )
            except Exception as analysis_error:
                print(f"⚠️  UX Analysis failed: {str(analysis_error)}")
                print("Main results still saved successfully.")
        
    except Exception as e:
        error_msg = f"Error processing results: {str(e)}\nTimestamp: {timestamp}"
        with open("agent_result.txt", "w", encoding="utf-8") as txt_file:
            txt_file.write(error_msg)
        print(f"Error occurred: {str(e)}")
        print("Error details saved to: agent_result.txt")

if __name__ == "__main__":
    asyncio.run(main())
