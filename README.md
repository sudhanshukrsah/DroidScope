# DroidRun UX Flow Explorer

An autonomous UI exploration agent that maps application navigation flows and generates detailed UX analysis reports.

## Overview

This project uses the DroidRun framework to automatically explore mobile/web applications, discover navigable screens, record transitions, and produce structured UX flow maps with AI-powered analysis.

## Features

- **Autonomous Exploration**: AI agent navigates apps like a human user
- **Structured Output**: Generates JSON navigation graphs with screens and transitions
- **UX Analysis**: Analyzes structural attention patterns, friction points, and discoverability issues
- **HTML Reports**: Beautiful visualizations with Chart.js and Markdown.js
- **Safety First**: Avoids destructive actions (logout, delete, posting)

## Setup

### 1. Create Virtual Environment

```powershell
python -m venv venv
```

### 2. Activate Virtual Environment

```powershell
.\venv\Scripts\Activate.ps1
```

If you encounter an execution policy error:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
API_KEY=your_openrouter_api_key_here
```

## Usage

### Run UX Flow Explorer

```powershell
python ux_flow_explorer.py
```

This will:
1. Explore the target application (configured in the script)
2. Generate `agent_result.txt` with exploration results
3. Automatically run UX analysis
4. Generate `ux_analysis_report.html` with visualizations

### Run Analysis Only (Standalone)

```powershell
python ux_analyzer.py
```

Analyzes existing `agent_result.txt` and generates HTML report.

## Output Files

- **agent_result.txt** - Raw exploration results with success status
- **discord_ux_flow.json** - Structured navigation graph (if available)
- **ux_analysis.json** - Detailed UX analysis in JSON format
- **ux_analysis_report.html** - Interactive HTML report with charts

## Configuration

### Change Target Application

Edit `ux_flow_explorer.py`:

```python
agent = DroidAgent(
    goal="Explore the [YOUR_APP_NAME] application...",
    config=config,
    llms=llm,
)
```

### Adjust Exploration Parameters

```python
config.agent.max_steps = 110  # Maximum steps for exploration
```

### Change LLM Model

```python
llm = OpenAILike(
    model="mistralai/devstral-2512:free",  # Change model here
    api_base="https://openrouter.ai/api/v1",
    api_key=openrouter_key,
    temperature=0.2
)
```

## Project Structure

```
DROIDRUN/
├── ux_flow_explorer.py    # Main exploration agent
├── ux_analyzer.py          # UX analysis and HTML generation
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create this)
├── .gitignore             # Git ignore rules
└── trajectories/          # Exploration session data
```

## Requirements

- Python 3.8+
- DroidRun framework
- OpenRouter API key (for free LLM access)
- Android device/emulator or browser (depending on target)

## Deactivate Virtual Environment

When done:

```powershell
deactivate
```

## License

MIT

## Contributing

Feel free to submit issues or pull requests.
