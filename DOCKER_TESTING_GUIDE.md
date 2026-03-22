# Local Docker Testing Guide

## Why Docker?
Test the exact same environment that Streamlit Cloud uses, without leaving your machine.

## Prerequisites
- Docker Desktop installed
- `.streamlit/secrets.toml` with your API key
- Python 3.10+ (no virtual env needed with Docker)

## Quick Start

### 1. Setup
```bash
# Copy secrets template
cp .streamlit/secrets.example.toml .streamlit/secrets.toml

# Edit with your API key
nano .streamlit/secrets.toml
# Change: AI_BOT_MAQ_OPENAI_API_KEY = "sk-proj-your-actual-key-here"
```

### 2. Build & Run with Docker
```bash
# Using Docker Compose (simplest)
docker-compose up --build

# Or using Docker directly (more control)
docker build -t ai-bot-streamlit .
docker run -p 8501:8501 \
  -v $(pwd)/.streamlit:/home/appuser/.streamlit \
  -v $(pwd)/assistant_app:/app/assistant_app \
  -e AI_BOT_MAQ_OPENAI_API_KEY=$AI_BOT_MAQ_OPENAI_API_KEY \
  ai-bot-streamlit
```

### 3. Access the App
```
http://localhost:8501
```

### 4. Stop the Container
```bash
# If using Docker Compose
docker-compose down

# If using Docker directly
docker stop <container_id>
```

## Common Docker Commands

### View Running Containers
```bash
docker ps
```

### View Logs
```bash
# With Docker Compose
docker-compose logs -f

# With Docker directly
docker logs -f <container_id>
```

### Rebuild After Changes
```bash
# With Docker Compose
docker-compose up --build

# With Docker directly
docker build --no-cache -t ai-bot-streamlit .
docker run -p 8501:8501 ai-bot-streamlit
```

### Remove Old Images
```bash
docker images
docker rmi <image_id>
```

### Debug Inside Container
```bash
docker exec -it <container_id> /bin/bash
```

## Validate Deployment Matches Local

### 1. UI Appearance
- [ ] Sidebar is dark (#262626)
- [ ] All text in sidebar is white
- [ ] Buttons are orange (#FF6B35)
- [ ] Button hover state is lighter orange (#F7931E)
- [ ] Main area background is dark (#1a1a1a)
- [ ] Header titles are orange colored
- [ ] Input fields have dark background with white text

### 2. Functionality
- [ ] Upload PBIX files works
- [ ] Model discovery works
- [ ] Formula generation works
- [ ] All buttons are clickable
- [ ] No console errors (check DevTools F12)

### 3. Configuration
- [ ] Config colors match what you see
- [ ] No missing dependencies
- [ ] API calls succeed
- [ ] No hardcoded API keys visible in code

### 4. Performance
- [ ] App loads in < 5 seconds
- [ ] No lag when clicking buttons
- [ ] No console errors (F12 → Console)
- [ ] No timeout issues

## If Colors Don't Match

### 1. Check config.toml
```bash
# Verify inside container
docker exec <container_id> cat /app/.streamlit/config.toml
```

### 2. Check CSS in ui.py
```bash
# Look for sidebar styling
docker exec <container_id> grep -n "stSidebar" /app/assistant_app/ui.py
```

### 3. Rebuild with Fresh Cache
```bash
docker-compose down -v
docker system prune -a
docker-compose up --build
```

### 4. Hard Refresh in Browser
```
Ctrl+Shift+R (Windows/Linux)
Cmd+Shift+R (Mac)
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs

# Common issues:
# 1. Port 8501 already in use
docker-compose down
docker-compose up

# 2. Missing .streamlit/secrets.toml
cp .streamlit/secrets.example.toml .streamlit/secrets.toml

# 3. Dependencies not installed
docker system prune -a
docker-compose up --build
```

### App Crashes with Error
```bash
# 1. Check container is still running
docker ps

# 2. View the error logs
docker-compose logs tail

# 3. Check if API key is valid
docker exec <container_id> cat /home/appuser/.streamlit/secrets.toml

# 4. Rebuild everything
docker-compose down -v
docker-compose up --build
```

### Colors Still Wrong
```bash
# Clear Streamlit cache inside container
docker exec <container_id> rm -rf /home/appuser/.cache

# Rebuild to get fresh CSS
docker-compose up --build

# What should you see:
# - Sidebar: #262626 (dark gray)
# - Buttons: #FF6B35 (orange)
# - Text: #FFFFFF (white)
# - Background: #1a1a1a (very dark)
```

## Performance Testing

### Load Testing
```bash
# Install Apache Bench (optional)
# Test response time
ab -n 10 -c 1 http://localhost:8501
```

### Memory Usage
```bash
docker stats ai-bot-streamlit
```

### Disk Space
```bash
docker du  # If available
docker system df
```

## Deploy with Confidence

Once you see the Docker container running identically to Streamlit Cloud:

```bash
# 1. Stop Docker (no longer needed)
docker-compose down

# 2. Run tests one more time
python -m pytest comprehensive_app_tests.py -v

# 3. Commit and push
git add .
git commit -m "test: verified deployment with Docker matching local"
git push origin main

# 4. Streamlit Cloud auto-deploys
# 5. Verify in Streamlit Cloud dashboard
```

## Docker Maintenance

### Clean Up Unused Images
```bash
docker image prune -a
```

### Clean Up Unused Containers
```bash
docker container prune
```

### Full System Cleanup
```bash
docker system prune -a --volumes
```

## Summary

✅ **Docker gives you:**
- Exact environment match
- No version surprises
- Easy rollback
- Easy cleanup
- Full testing confidence

✅ **Use this workflow:**
```
Code → Docker Compose (test locally)
       → Fix any issues
       → Push to GitHub
       → CI/CD validates
       → Streamlit Cloud deploys
       → Verify live app
```
