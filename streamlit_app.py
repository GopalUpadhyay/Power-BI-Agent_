"""
AI Bot - Streamlit App Entry Point
Main application for Power BI AI Assistant with intelligent formula generation
"""

import sys
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent))

# Import and run the UI
from assistant_app.ui import main

if __name__ == "__main__":
    main()
