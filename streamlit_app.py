"""
AI Bot - Streamlit App Entry Point
Main application for Power BI AI Assistant with intelligent formula generation

This is the main entry point for Streamlit Cloud deployment.
Streamlit automatically discovers and runs this file.
"""

import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the app directory to the path so we can import assistant_app
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

logger.info(f"App directory: {app_dir}")
logger.info(f"Python path: {sys.path[:2]}")

try:
    # Import and run the UI
    from assistant_app.ui import main
    logger.info("Successfully imported assistant_app.ui.main()")
except ImportError as e:
    logger.error(f"Failed to import assistant_app.ui: {e}")
    raise


def run_app() -> None:
    """Run the Streamlit application."""
    try:
        logger.info("Starting Power BI AI Assistant...")
        main()
    except Exception as e:
        logger.error(f"Error running application: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_app()

