"""
AI Bot - Streamlit App Entry Point
Main application for Power BI AI Assistant with intelligent formula generation

This is the main entry point for Streamlit Cloud deployment.
Streamlit automatically discovers and runs this file.
"""

import sys
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Keep Streamlit Cloud behavior aligned with local launcher (run_ui.py)
os.environ.setdefault("FABRIC_ASSISTANT_USE_LLM", "1")

# Add the app directory to the path so we can import assistant_app
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

logger.info(f"App directory: {app_dir}")
logger.info(f"Python path: {sys.path[:2]}")

# Prefer Streamlit Secrets key in cloud if env var is not already present.
try:
    import streamlit as st

    secret_groq_key = str(st.secrets.get("GROQ_API_KEY", "")).strip()
    if secret_groq_key and not os.getenv("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = secret_groq_key
        logger.info("Loaded GROQ_API_KEY from Streamlit Secrets")
except Exception:
    # Local runs may not have streamlit secrets configured; continue with env/.env.
    pass

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

