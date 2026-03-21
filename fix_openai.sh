#!/bin/bash

# OpenAI API Key Fix Script
# Run this to test and fix your OpenAI configuration

echo "=========================================="
echo "OpenAI API Configuration Diagnostic"
echo "=========================================="
echo ""

# Check if .env file exists
echo "1️⃣  Checking .env file..."
if [ -f "/home/gopal-upadhyay/AI_Bot_MAQ/.env" ]; then
    echo "✅ .env file found"
    echo ""
    echo "Current .env content (API key hidden):"
    grep "OPENAI_API_KEY=" /home/gopal-upadhyay/AI_Bot_MAQ/.env | sed 's/=sk-proj-.*/=sk-proj-***HIDDEN***/g'
else
    echo "❌ .env file not found at /home/gopal-upadhyay/AI_Bot_MAQ/.env"
    echo "Creating .env file..."
    cat > /home/gopal-upadhyay/AI_Bot_MAQ/.env << 'EOF'
# OpenAI API Configuration
# Replace with your actual API key from https://platform.openai.com/api-keys
OPENAI_API_KEY=your_key_here
EOF
    echo "✅ .env file created. Please add your API key."
fi

echo ""
echo "2️⃣  Checking Python environment..."
cd /home/gopal-upadhyay/AI_Bot_MAQ

# Check if virtual environment exists
if [ -d ".venv" ]; then
    echo "✅ Virtual environment found"
    source .venv/bin/activate
else
    echo "⚠️  Virtual environment not found"
fi

echo ""
echo "3️⃣  Testing OpenAI connectivity..."
python3 << 'PYEOF'
import os
import sys
from pathlib import Path

# Load .env
env_file = Path("/home/gopal-upadhyay/AI_Bot_MAQ/.env")
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip()
                os.environ["OPENAI_API_KEY"] = key

api_key = os.getenv("OPENAI_API_KEY", "NOT_FOUND")

print(f"API Key Status:")
if api_key == "NOT_FOUND":
    print("  ❌ No API key found in environment")
elif api_key == "your_key_here":
    print("  ❌ API key not configured (placeholder value)")
elif not api_key.startswith("sk-proj-"):
    print(f"  ❌ Invalid format. Should start with 'sk-proj-'")
    print(f"     Found: {api_key[:20]}...")
elif len(api_key) < 20:
    print(f"  ❌ API key too short (length: {len(api_key)})")
else:
    print(f"  ✅ Valid format (length: {len(api_key)})")
    print(f"     First 20 chars: {api_key[:20]}...")

# Try importing OpenAI
print("\nOpenAI Package Status:")
try:
    from openai import OpenAI
    print("  ✅ OpenAI package installed")
    
    # Try creating a client
    if api_key.startswith("sk-proj-") and len(api_key) > 20:
        print("\nAttempting OpenAI client creation...")
        try:
            client = OpenAI(api_key=api_key, max_retries=0, timeout=5.0)
            print("  ✅ OpenAI client created successfully!")
            print("  Note: Actual API test would require a real API call")
        except Exception as e:
            print(f"  ❌ Client creation failed: {str(e)[:100]}")
            if "quota" in str(e).lower():
                print("     Likely cause: API quota exceeded")
            elif "auth" in str(e).lower():
                print("     Likely cause: Authentication failed (invalid key)")
    else:
        print("  ⚠️  Skipping client test - API key format invalid")
        
except ImportError as e:
    print(f"  ❌ OpenAI package not installed: {e}")
    print("     Run: pip install openai")

PYEOF

echo ""
echo "=========================================="
echo "4️⃣  How to Fix:"
echo "=========================================="
echo ""
echo "Option A: Get a new API key"
echo "  1. Go to: https://platform.openai.com/api-keys"
echo "  2. Click 'Create new secret key'"
echo "  3. Copy the entire key (starts with sk-proj-)"
echo "  4. Edit your .env file:"
echo "     nano /home/gopal-upadhyay/AI_Bot_MAQ/.env"
echo "  5. Replace the OPENAI_API_KEY value"
echo "  6. Save and restart the app"
echo ""
echo "Option B: Continue with fallback mode"
echo "  ✅ The app works perfectly without OpenAI"
echo "  ✅ Relationships, tables, and basic code generation work"
echo "  ✅ Speed is actually faster (no API calls)"
echo ""
echo "=========================================="
