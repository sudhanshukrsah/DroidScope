# DroidScope v2 - Multi-Stage UX Exploration Tool

An autonomous UX exploration and analysis tool for Android applications, powered by DroidRun framework and LLM-based analysis.

## What's New in v2

### Multi-Stage Exploration
DroidScope v2 introduces a 4-stage exploration pipeline:

1. **Stage 1: Basic Exploration**
   - Opens the target app
   - Scans screen structure and navigation
   - Documents buttons, inputs, scrollable areas
   - Creates initial app inventory

2. **Stage 2: Persona Analysis**
   - Adopts one of three personas (UX Designer, QA Engineer, Product Manager)
   - Evaluates app through role-specific lens
   - Category-aware analysis
   - Detailed role-specific findings

3. **Stage 3: Custom Navigation / Stress Test**
   - Executes custom navigation paths (if provided)
   - Tests app resilience with erratic user behavior
   - Edge case exploration
   - Dark pattern detection
   - Breakability assessment

4. **Stage 4: Final Analysis**
   - Combines all stage data
   - LLM-powered comprehensive analysis
   - Generates actionable insights and scores
   - Produces visualization-ready data

### Personas

- **UX Designer**: Focuses on visual hierarchy, interaction design, affordance, consistency, and emotional design
- **QA Engineer**: Focuses on functional testing, edge cases, error handling, performance, and stability
- **Product Manager**: Focuses on user value, feature completeness, conversion, engagement, and competitive positioning

### New Features

- **SQLite Database**: Persistent storage for all explorations and results
- **Results Library**: Browse and revisit past exploration results
- **Comparison View**: Compare results across apps, categories, and personas
- **Settings Management**: Configure API keys and model via frontend
- **Stage-wise Progress**: Real-time visualization of exploration stages
- **Save to Memory**: Option to save results for future comparison

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd DroidScope

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API key
```

## Configuration

Create a `.env` file with:

```env
API_KEY=your_openrouter_api_key
LLM_MODEL=mistralai/devstral-2512:free
LLM_API_BASE=https://openrouter.ai/api/v1
```

Or configure via the Settings modal in the UI.

## Running

```bash
# Run the v2 application
python run_v2.py

# Or directly
python app_v2.py
```

Open http://localhost:5000 in your browser.

## Usage

1. **Connect Device**: Ensure Android device is connected via ADB
2. **Configure Exploration**:
   - Enter app name
   - Select category
   - (Optional) Add custom navigation instructions
   - Choose analysis persona
   - (Optional) Enable "Save to memory" for comparison
3. **Start Exploration**: Click the button and monitor progress
4. **View Results**: Automatically switches to results when complete
5. **Library**: Browse past explorations
6. **Compare**: Compare results across different apps/personas

## Project Structure

```
DroidScope/
├── app_v2.py                 # Flask backend (v2)
├── run_v2.py                 # Launcher script
├── exploration_runner_v2.py  # Multi-stage exploration logic
├── database.py               # SQLite database operations
├── utils.py                  # Utility functions
├── ux_analyzer.py            # LLM-based UX analysis
├── verify_setup.py           # Setup verification
├── templates/
│   ├── index_v2.html         # Main UI (v2)
│   └── index.html            # Original UI (v1)
├── static/
│   ├── script_v2.js          # Frontend JS (v2)
│   └── script.js             # Original JS (v1)
├── prompts/
│   ├── stage1_basic_exploration.txt
│   ├── stage2_persona_analysis.txt
│   ├── stage3_custom_stress.txt
│   ├── stage4_final_analysis.txt
│   ├── persona_ux_designer.txt
│   ├── persona_qa_engineer.txt
│   ├── persona_product_manager.txt
│   └── ...
├── explorations/             # Stage output files (per exploration)
├── droidscope.db            # SQLite database
└── requirements.txt
```

## API Endpoints

### Exploration
- `POST /api/run-test` - Start multi-stage exploration
- `POST /api/stop-agent` - Stop running exploration
- `GET /api/progress` - SSE stream for progress updates
- `GET /api/logs` - SSE stream for execution logs
- `GET /api/stages` - SSE stream for stage status

### Results
- `GET /api/results` - Get latest/specific results
- `GET /api/results/<id>` - Get results by exploration ID

### Library
- `GET /api/library` - Get all explorations
- `GET /api/library/categories` - Get category list
- `GET /api/library/personas` - Get persona list

### Comparison
- `GET /api/compare` - Get comparison data
- `POST /api/compare/snapshot` - Create comparison snapshot

### Settings
- `GET /api/settings` - Get current settings
- `POST /api/settings` - Update settings

### Device
- `GET /api/device-status` - Check device connection

## Output Format

The final analysis produces a comprehensive JSON with:

- **summary**: Executive summary
- **app_metadata**: Screen count, interaction count, core flows
- **exploration_coverage**: Success rates, dead elements
- **navigation_metrics**: Depth, backtracking, architecture quality
- **interaction_feedback**: Feedback rates, silent failures
- **visual_hierarchy**: CTA visibility, tap targets, clarity
- **consistency**: Pattern reuse, violations
- **error_handling**: Preventable errors, recovery paths
- **stress_test_results**: Breakability, resilience scores
- **positive**: Good UX patterns found
- **issues**: Problems with severity and impact
- **dark_patterns**: Manipulative patterns detected
- **recommendations**: Prioritized improvements with effort/impact
- **ux_confidence_score**: Overall reliability score
- **graph_data**: Chart-ready visualization data

## Legacy Support

The original v1 files (`app.py`, `index.html`, `script.js`) are preserved for backward compatibility. Use `python app.py` to run the original version.

## License

MIT License
