# Streamlit Cloud Deployment Guide

## Overview
This application is configured for automatic deployment to Streamlit Cloud via GitHub Actions CI/CD pipeline.

## Architecture

### Entry Point
- **File:** `streamlit_app.py` (must be at root directory)
- **Purpose:** Streamlit Cloud's auto-discovery mechanism
- **Function:** Imports and runs `assistant_app.ui.main()`

### Configuration Files
1. `.streamlit/config.toml` - Streamlit runtime configuration
2. `.streamlit/secrets.example.toml` - Template for API keys
3. `.github/workflows/deploy.yml` - CI/CD pipeline

### Key Directories
```
/
├── streamlit_app.py          ← Entry point (required)
├── .streamlit/
│   ├── config.toml           ← Runtime config
│   └── secrets.example.toml  ← API key template
├── .github/
│   └── workflows/
│       └── deploy.yml        ← CI/CD pipeline
├── assistant_app/
│   ├── ui.py                 ← Main UI (1400+ lines)
│   ├── formula_corrector.py  ← Intelligent formula generation
│   └── ...
├── requirements.txt          ← Python dependencies
└── README.md
```

## CI/CD Pipeline Flow

### Trigger Events
```
GitHub Push → GitHub Actions runs → Tests → Deploy
```

### Pipeline Stages

#### 1. **Test Stage** (Runs on every push and PR)
```bash
✓ Install dependencies
✓ Lint Python code (flake8)
✓ Run unit tests (comprehensive_app_tests.py)
✓ Run QA tests (automated_qa_tests.py)
✓ Validate config.toml
✓ Check for hardcoded API keys (security scan)
```

#### 2. **Deploy Stage** (Only runs on main branch push)
```bash
✓ Validate all required files exist
✓ Push code to GitHub (triggers Streamlit Cloud auto-deploy)
✓ Notification of deployment
```

#### 3. **Notify Stage** (Reports status)
```bash
✓ Sends deployment summary to GitHub
✓ Displays deployment status badge
```

## Local Setup (Test Locally Before Pushing)

### 1. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Setup Secrets Locally
```bash
# Copy the secrets template
cp .streamlit/secrets.example.toml .streamlit/secrets.toml

# Edit with your actual API key
nano .streamlit/secrets.toml
# Change: AI_BOT_MAQ_OPENAI_API_KEY = "sk-proj-your-actual-key-here"
```

### 3. Run Locally
```bash
streamlit run streamlit_app.py
```

The app will be available at: `http://localhost:8501`

### 4. Run Tests Before Pushing
```bash
# Run all tests
python -m pytest comprehensive_app_tests.py -v
python -m pytest automated_qa_tests.py -v

# Or run via GitHub Actions locally (requires act)
act push
```

## Deployment to Streamlit Cloud

### Prerequisites
1. GitHub repository connected to Streamlit Cloud
2. Repository name: `Model-Based-AI-Bo`
3. Main entry point: `streamlit_app.py`
4. Branch: `main`

### Streamlit Cloud Setup

1. **Connect Repository**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Click "New app"
   - Select repository: `GopalUpadhyay/Model-Based-AI-Bo`
   - Select branch: `main`
   - Set main file path: `streamlit_app.py`
   - Click "Deploy"

2. **Configure Secrets**
   - In Streamlit Cloud app dashboard
   - Click "Settings" (gear icon)
   - Go to "Secrets"
   - Copy content from `.streamlit/secrets.example.toml`
   - Paste and add your actual API key:
     ```
     AI_BOT_MAQ_OPENAI_API_KEY = "sk-proj-your-actual-api-key-here"
     ```
   - Save

3. **Verify Deployment**
   - App will automatically redeploy when you push to main
   - Check deployment status at: [Streamlit Cloud Dashboard](https://share.streamlit.io)

## Auto-Deployment Workflow

### How It Works

```
1. You push code to GitHub main branch
   ↓
2. GitHub Actions workflow triggers automatically
   ↓
3. Test stage runs (lint, unit tests, security checks)
   ↓
4. If all tests pass, deploy stage runs
   ↓
5. Streamlit Cloud detects changes and auto-deploys
   ↓
6. Your app updates live within 2-3 minutes
```

### Automatic Redeployment
- **Trigger:** Push to `main` branch
- **Delay:** 2-3 minutes for deployment
- **Status:** Check [Streamlit Cloud Dashboard](https://share.streamlit.io)

## Troubleshooting Deployment

### App Won't Start
1. **Check logs in Streamlit Cloud**
   - App dashboard → "Manage app" → "View logs"
   
2. **Check test output**
   - Go to GitHub → Your repo → "Actions"
   - Click the failed workflow run
   - Look for error messages

3. **Common issues:**
   ```
   ❌ ModuleNotFoundError: No module named 'assistant_app'
   ✓ Solution: Ensure streamlit_app.py is at root directory
   
   ❌ FileNotFoundError: .env not found
   ✓ Solution: Use .streamlit/secrets.toml instead
   
   ❌ API key error
   ✓ Solution: Add key to Streamlit Cloud secrets (Settings)
   ```

### Styling Issues (Colors/Layout)
1. **Hard refresh browser**
   ```
   Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
   ```

2. **Clear Streamlit cache**
   - In app: Click hamburger menu (☰) → Settings → "Clear cache"

3. **Reboot the app**
   - In Streamlit Cloud dashboard: Click (⋮) → Settings → "Reboot app"

## Making Changes

### Workflow to Push Changes

```
1. Make changes locally
   
2. Test locally
   streamlit run streamlit_app.py
   
3. Run tests
   python -m pytest comprehensive_app_tests.py -v
   
4. Commit and push
   git add .
   git commit -m "feat: Description of change"
   git push origin main
   
5. CI/CD pipeline runs automatically
   
6. Deploy happens automatically if tests pass
   
7. Check app live in 2-3 minutes
```

### What NOT to Commit
- `.streamlit/secrets.toml` (API keys) - Already in .gitignore
- `.venv/` (virtual environment) - Already in .gitignore
- `__pycache__/` (Python cache) - Already in .gitignore
- `.env` (local environment) - Already in .gitignore

## Environment Variables

### Local Development (.env)
```bash
AI_BOT_MAQ_OPENAI_API_KEY=sk-proj-your-local-key-here
```

### Streamlit Cloud (Web-based secrets manager)
```toml
AI_BOT_MAQ_OPENAI_API_KEY = "sk-proj-your-cloud-key-here"
```

### Accessing in Code
```python
import streamlit as st

# Get key from secrets
api_key = st.secrets.get("AI_BOT_MAQ_OPENAI_API_KEY")
```

## Performance Optimization

### Caching
The app uses Streamlit caching (already implemented in ui.py):
```python
@st.cache_data
def load_data():
    # Expensive operation cached
    return data
```

### Config Settings Active
```toml
[runner]
magicEnabled = true      # Fast reruns
fastReruns = true        # Optimized rendering

[global]
dataFrameSerialization = "arrow"  # Faster dataframe handling
```

## Monitoring

### GitHub Actions Dashboard
- URL: `https://github.com/GopalUpadhyay/Model-Based-AI-Bo/actions`
- View: All test and deployment runs
- Status: Success/failure of each stage

### Streamlit Cloud Dashboard
- URL: `https://share.streamlit.io`
- View: App status, logs, deployment history
- Manage: Settings, secrets, app configuration

## Support

### For Deployment Issues
1. Check CI/CD logs: GitHub → Actions → Last workflow
2. Check Streamlit logs: Streamlit Cloud → App → Logs
3. Check requirements.txt: All dependencies listed?
4. Check config.toml: Valid TOML syntax?
5. Check streamlit_app.py: Can import assistant_app?

### For Code Issues
1. Run tests locally: `pytest -v`
2. Run linter: `flake8 assistant_app/`
3. Check syntax: Color highlighting in editor
4. Review error messages in terminal

## Quick Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
streamlit run streamlit_app.py

# Run tests
python -m pytest comprehensive_app_tests.py -v

# Lint code
flake8 assistant_app/

# Push changes (triggers CI/CD)
git add .
git commit -m "feat: description"
git push origin main
```

## Summary

✅ **Fully Automated Deployment:**
- Push to main → Tests run → Deploy automatically
- No manual Streamlit Cloud clicks needed
- Takes 2-3 minutes total

✅ **Local Testing:**
- Mirror production with local Streamlit
- Test before pushing
- Reduce failed deployments

✅ **Secure:**
- API keys in secrets (not in code)
- Security scan prevents key leaks
- .gitignore protects sensitive files

✅ **Reliable:**
- Comprehensive test suite
- Linting validates code
- Deployment notifications
