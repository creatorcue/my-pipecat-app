# 🤖 Vobiz + Pipecat AI Voice Assistant

A real-time AI voice assistant that integrates **Vobiz telephony** with **Pipecat's full STT → LLM → TTS pipeline**. When an outbound call is answered, the caller is connected to an AI assistant powered by OpenAI Whisper (speech-to-text), GPT-4o (language model), and OpenAI TTS (text-to-speech).

---

## 🏗️ Architecture

```
phone.py ──► Vobiz API ──► Calls destination phone
                                    │
                             Phone is answered
                                    │
                                    ▼
                        POST /answer (Vobiz webhook)
                                    │
                             Returns XML with WSS URL
                                    │
                                    ▼
                        WebSocket /ws (audio stream)
                                    │
                  ┌─────────────────▼─────────────────┐
                  │         Pipecat Pipeline           │
                  │  Vobiz Audio → STT → LLM → TTS    │
                  │  (Whisper)    (GPT-4o) (OpenAI)   │
                  └─────────────────┬─────────────────┘
                                    │
                             Audio sent back
                                    │
                                    ▼
                            Caller hears AI
```

---

## 📋 Prerequisites

- Python 3.11+
- [zrok](https://zrok.io) account and CLI installed
- Vobiz account with API credentials
- OpenAI API key

---

## ⚙️ Environment Variables

Create a `.env` file in the root of the project:

```env
# ─── OpenAI ───────────────────────────────────────────────
# Your OpenAI API key — used for Whisper STT, GPT-4o LLM, and TTS
OPENAI_API_KEY=sk-...

# ─── Vobiz ────────────────────────────────────────────────
# Found in your Vobiz console under Account Settings
VOBIZ_AUTH_ID=MA_XXXXXXXX

# Found in your Vobiz console under Account Settings
VOBIZ_AUTH_TOKEN=your_auth_token_here

# Your Vobiz DID number in E.164 format (the "from" number for outbound calls)
# Found in your Vobiz console under Phone Numbers
VOBIZ_DID=91XXXXXXXXXX

# ─── Tunnel ───────────────────────────────────────────────
# Your public zrok tunnel URL (no trailing slash, no /ws suffix)
# Update this every time you restart zrok — the URL changes each time
PUBLIC_URL=https://XXXXXXXXXXXXXX.share.zrok.io
```

## 📁 Project Structure

```
my-pipecat-app/
├── vobiz/
│   ├── server.py          # Main FastAPI + Pipecat server
│   └── phone.py           # Script to trigger outbound calls
├── .env                   # Environment variables (never commit this)
├── .env.example           # Example env file (safe to commit)
├── requirements.txt       # Python dependencies
└── README.md
```

---

## 📦 Requirements

Install them:
```bash
pip install -r requirements.txt
```

---

## 🚀 Running the Project

Follow these steps **in order** every time you start the project.

### Step 1 — Activate virtual environment

```bash
cd my-pipecat-app
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### Step 2 — Start zrok tunnel

```bash
zrok share public http://localhost:7860
```

You will see output like:
```
https://abc123xyz.share.zrok.io
```

Copy this URL and update `PUBLIC_URL` in your `.env` file:
```env
PUBLIC_URL=https://abc123xyz.share.zrok.io
```

> ⚠️ The zrok URL changes every time you restart zrok. Always update `.env` after restarting.
> ⚠️ Keep this terminal open. Do not close it.

### Step 3 — Start the FastAPI server (new terminal)

```bash
source .venv/bin/activate
python vobiz/server.py
```

You should see:
```
INFO: Uvicorn running on http://0.0.0.0:7860
```

> ⚠️ Keep this terminal open. Do not close it.

### Step 4 — Verify the tunnel is working

```bash
curl -X POST https://abc123xyz.share.zrok.io/answer \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "test=1"
```

You should see an XML response. If you get a 502 or timeout, zrok is not running or the URL is wrong.

### Step 5 — Make a call

Edit `phone.py` and set the destination number:

```python
if __name__ == "__main__":
    make_the_call("+91XXXXXXXXXX")  # replace with your target number
```

Then run it:

```bash
python vobiz/phone.py
```

You should see:
```
Status Code: 201
Success! Call fired. SID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

The destination phone will ring. When answered, the AI will greet the caller and respond to their voice.

---

## 🔁 Startup Order (Quick Reference)

```
1. source .venv/bin/activate
2. zrok share public http://localhost:7860   ← get public URL
3. Update PUBLIC_URL in .env with new zrok URL
4. python vobiz/server.py                   ← start server on :7860
5. python vobiz/phone.py                    ← trigger the call
```

> ⚠️ Always start zrok BEFORE the server so the correct `PUBLIC_URL` is loaded on startup.

---

## 📞 Server Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/answer` | Vobiz webhook — called when call is answered, returns XML to start audio stream |
| `WS` | `/ws` | WebSocket — receives and sends audio to/from Vobiz |
