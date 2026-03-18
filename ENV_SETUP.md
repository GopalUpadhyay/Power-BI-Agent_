# API Key Configuration Guide

## Overview

The application now uses a `.env` file for secure API key management instead of hardcoding keys in the source code.

## Quick Start

### 1. Get Your OpenAI API Key

1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Create a new API key
3. Copy the key (starts with `sk-proj-`)

### 2. Configure the `.env` File

Edit the `.env` file in the project root:

```bash
# .env
OPENAI_API_KEY=sk-proj-your-actual-api-key-here
```

Replace `sk-proj-your-actual-api-key-here` with your actual OpenAI API key.

### 3. Run the Application

**Demo Mode (with loaded .env key):**

```bash
./.venv/bin/python run_app.py --demo
```

**Interactive Mode:**

```bash
./.venv/bin/python run_app.py --interactive
```

**Override API Key via CLI (optional):**

```bash
./.venv/bin/python run_app.py --demo --api-key sk-proj-your-key
```

## Security

### ✅ What We've Done

- Created `.env` file for local configuration
- Added `.env` to `.gitignore` (never committed to git)
- Created `.env.example` as a template for other developers
- Removed hardcoded API keys from source code
- Use `python-dotenv` library to securely load environment variables

### 🔒 Best Practices

1. **Never commit `.env` to version control**
2. **Never share your API key** - if exposed, revoke it immediately
3. **Use environment variables** for all sensitive data
4. **For production**, use a secure secrets manager (e.g., AWS Secrets Manager, Azure Key Vault)

## File Structure

```
/home/gopal-upadhyay/AI_Bot_MAQ/
├── .env                     ← Your local API key (NOT committed)
├── .env.example             ← Template for setup
├── .gitignore              ← Excludes .env from git
├── requirements.txt        ← Updated to include python-dotenv
├── assistant_app/
│   ├── core.py            ← Updated to use load_dotenv()
│   └── cli.py
└── ...
```

## How It Works

In `assistant_app/core.py`:

```python
from dotenv import load_dotenv

# Load environment variables from .env file at startup
load_dotenv()

def configure_openai_client(api_key: Optional[str] = None):
    # Read from environment variable
    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    ...
```

The `load_dotenv()` function automatically reads the `.env` file and loads all variables into `os.environ`.

## Troubleshooting

**Issue**: "OpenAI generation failed"

- Check that your API key in `.env` is correct
- Verify the key hasn't expired or been revoked
- Ensure `.env` file is in the project root

**Issue**: "OPENAI_API_KEY not found"

- Make sure `.env` file exists
- Verify the key name is exactly `OPENAI_API_KEY`
- Restart your terminal/IDE for changes to take effect

**Issue**: "Module 'dotenv' not found"

- Run: `./.venv/bin/python -m pip install python-dotenv`

## Next Steps

1. ✅ Copy your OpenAI API key
2. ✅ Update `.env` with your key
3. ✅ Run the app: `./.venv/bin/python run_app.py --demo`
4. ✅ Verify output shows "OpenAI client configured"

## For Team/Production

Create a `.env.production` or use CI/CD secrets:

- **GitHub Actions**: Use Secrets in settings
- **Docker**: Pass environment variables at runtime
- **Cloud Platforms**: Use managed secret stores

Example GitHub Actions:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

---

**Last Updated**: 2026-03-18
