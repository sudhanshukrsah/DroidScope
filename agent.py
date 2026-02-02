import asyncio
from droidrun import DroidAgent, DroidrunConfig
from llama_index.llms.openai_like import OpenAILike

async def main():
    # Use default configuration with built-in LLM profiles
    config = DroidrunConfig()
    
    model = "mistralai/devstral-2-123b-instruct-2512"
    api_base = "https://integrate.api.nvidia.com/v1"
    api_key = "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"
    
    # NVIDIA requires model-specific endpoints
    # Format: https://integrate.api.nvidia.com/v1/{model}
    nvidia_endpoint = f"{api_base}"
    print(f"Using NVIDIA endpoint: {nvidia_endpoint}")
    print(f"Model: {model}")
    
    llm = OpenAILike(
        model=model,
        temperature=0.15,
        api_base=nvidia_endpoint,
        api_key=api_key,
        is_chat_model=True
    )
    

    # Create agent
    # LLMs are automatically loaded from config.llm_profiles
    agent = DroidAgent(
        goal="Open Settings and check battery level",
        config=config,
        llms=llm
        
    )

    # Run agent
    result = await agent.run()

    # Check results (result is a ResultEvent object)
    print(f"Success: {result.success}")
    print(f"Reason: {result.reason}")
    print(f"Steps: {result.steps}")

if __name__ == "__main__":
    asyncio.run(main())