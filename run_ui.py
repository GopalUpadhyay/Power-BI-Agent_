import os

# CRITICAL: Enable LLM code generation (Groq provider)
os.environ["FABRIC_ASSISTANT_USE_LLM"] = "1"

from assistant_app.ui import main


if __name__ == "__main__":
    main()
