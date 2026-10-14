# fashion-trend-radar

Python project for collecting Google Trends fashion signals through Bright Data.

## Setup

1. Create virtual environment:
   - `python -m venv .venv`
2. Activate it:
   - macOS/Linux: `source .venv/bin/activate`
   - Windows: `.venv\\Scripts\\activate`
3. Install dependencies:
   - `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your Bright Data token.
5. Run:
   - `python run.py`

## Output

- Raw JSON files: `data/raw/`
- Flattened CSV: `data/exports/trends_timeseries_*.csv`
- Summary CSV: `data/exports/trends_summary_*.csv`
