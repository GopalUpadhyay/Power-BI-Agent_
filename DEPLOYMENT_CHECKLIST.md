# 🚀 Streamlit Cloud Deployment Checklist

**Last Updated:** March 23, 2026  
**Target Deployment:** https://model-based-ai-bo-crrqfqhq2rbnapakscp2vu.streamlit.app/  
**Provider:** Groq (migrated from OpenAI/ChatGPT)

---

## ✅ Pre-Deployment (COMPLETED)

- [x] Migrated application from OpenAI to Groq
- [x] Installed Groq Python SDK (`pip install groq`)
- [x] Updated all imports (`Groq` client instead of `OpenAI`)
- [x] Added `groq` to `requirements.txt`
- [x] Implemented model fallback logic (handles decommissioned models)
- [x] Updated all UI references ("ChatGPT" → "Groq")
- [x] Fixed backward compatibility (added `configure_openai_client` alias)
- [x] Pushed all changes to GitHub ✅
- [x] Added `requirements.txt: groq>=0.9.0` ✅

---

## 🔧 NEXT STEPS (Manual - On Streamlit Cloud Dashboard)

### **Step 1: Rerun App with Latest Code**
1. Visit [share.streamlit.io](https://share.streamlit.io)
2. Find your app: "model-based-ai-bo..."
3. Click the **three-dot menu (⋮)** → **"Rerun app"**
   - This forces Streamlit Cloud to pull latest code from GitHub and redeploy

### **Step 2: Configure GROQ_API_KEY Secret** ⚠️ **REQUIRED**
1. In Streamlit Cloud dashboard → Select your app
2. Click **⚙️ Settings** (gear icon)
3. Click **"Secrets"** tab
4. Paste this exactly:
```toml
GROQ_API_KEY = "gsk_your_groq_api_key_here"
```
5. Click **"Save"**
6. ⏳ Wait 30-60 seconds for app to reboot with new secrets

### **Step 3: Verify Deployment**
After app reboots, test:

- [ ] App loads without errors
- [ ] Sidebar shows **"Groq API Key (optional override)"** (not "OpenAI API Key")
- [ ] Can generate code (Measure, Column, etc.)
- [ ] Generated items have correct names
  - ✅ Good: `sales_measure_ytd`, `product_name_column`
  - ❌ Bad: `dax_measure_YOU_ARE_A_DAX_CODE_GENERATION_EXPERT...`
- [ ] No errors about API key
- [ ] No "model_decommissioned" errors (should fallback silently)

---

## 📊 Current Code Status

| File | Change | Status |
|------|--------|--------|
| `requirements.txt` | Added `groq>=0.9.0` | ✅ Pushed |
| `run_ui.py` | Enable LLM flag | ✅ Pushed |
| `fabric_universal.py` | Groq client + fallback logic | ✅ Pushed |
| `ui.py` | API key input updated to Groq | ✅ Pushed |
| `core.py` | DAX generator uses Groq | ✅ Pushed |
| `cli.py` | Help text updated | ✅ Pushed |
| `.env` | GROQ_API_KEY placeholder | ⚠️ Local only |

---

## 🔑 Environment Variables

### **Streamlit Cloud (Set in Secrets tab)**
```toml
GROQ_API_KEY = "gsk_your_groq_api_key_here"
```

### **Local Development (in `.env`)**
```
GROQ_API_KEY=gsk_your_groq_api_key_here
FABRIC_ASSISTANT_USE_LLM=1
```

### **Optional (for advanced config)**
```
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODELS=llama-3.1-8b-instant,llama-2-7b-chat
```

---

## 🆘 Troubleshooting

### **❌ "API Key Missing" Error**
- **Cause:** `GROQ_API_KEY` not set in Streamlit Cloud Secrets
- **Fix:** Add to Secrets tab (Step 2 above)

### **❌ "model_decommissioned" Error**
- **Cause:** Groq decommissioned the model mid-request
- **Fix:** System will automatically retry with fallback model (llama-3.1-8b-instant)
  - If persists: Update `GROQ_FALLBACK_MODELS` in Secrets

### **❌ App Shows Old Version**
- **Cause:** Streamlit Cloud cached old code
- **Fix:** 
  1. Click Settings → "Advanced settings"
  2. Click "Reboot app"
  3. Or: Commit dummy change locally and push to GitHub

### **❌ "ModuleNotFoundError: No module named 'groq'"**
- **Cause:** `groq` not in `requirements.txt`
- **Fix:** ✅ Already fixed! Pushed `groq>=0.9.0` to requirements.txt

---

## 📝 Logs to Check

After deployment, check logs for:
- `Successfully imported assistant_app.ui.main()` ✅
- `Groq API key configured` or similar ✅
- No `ImportError` or `ModuleNotFoundError` ✅
- No `GROQ_API_KEY not set` ✅

---

## 🎯 Success Criteria

App is successfully deployed when all of these are true:

1. ✅ https://model-based-ai-bo-crrqfqhq2rbnapakscp2vu.streamlit.app/ **loads without errors**
2. ✅ Sidebar shows **"Groq"** (not "ChatGPT" or "OpenAI")
3. ✅ **API key field** accepts Groq key
4. ✅ **Code generation works** (create measure/column/table)
5. ✅ **Generated item names are correct** (not pollution)
6. ✅ **No crashes** on code generation request
7. ✅ **Multiple requests work** (doesn't run out of quota)

---

## 🔄 Local Testing (Optional)

Test locally before cloud deployment:

```bash
cd /home/gopal-upadhyay/AI_Bot_MAQ

# Ensure dependencies installed
pip install -r requirements.txt

# Run app
streamlit run streamlit_app.py

# Should open: http://localhost:8501
```

---

## 📞 Support

If deployment fails:
1. Check Streamlit Cloud **Logs** tab for error messages
2. Verify `GROQ_API_KEY` is set in **Secrets**
3. Check GitHub commits: Is `groq>=0.9.0` in `requirements.txt`? ✅
4. Reboot app from Streamlit Cloud Settings

---

**Ready to deploy!** Follow steps 1-3 above. 🚀
