# MogBot Chrome Extension

This is the first frontend prototype for MogBot. It lets the user paste a job description and resume, then practice a short interview inside the extension popup using the local Flask server started by `main.py`.

## Current Scope

- Paste job description text.
- Paste resume text.
- Start a backend-backed interview session.
- Answer generated questions in the popup.
- Receive evaluator feedback from the Python backend.
- View final session notes from the coaching agent.
- See the future phone-text option as disabled.

The extension calls `http://127.0.0.1:5000`, so `main.py` must be running before starting an interview.

## API Payloads

The extension sends this payload to `POST /sessions`:

```json
{
  "job_description": "",
  "resume_text": "",
  "delivery_mode": "extension",
  "phone_number": "",
  "sms_consent": false
}
```

If the user chooses the future SMS option, `delivery_mode` can become `"sms"` after phone-number collection and consent are implemented.

Answers are sent to `POST /sessions/{session_id}/answers`:

```json
{
  "answer_text": ""
}
```

For testing that both text areas reached the `main.py` floor manager, call:

```text
GET /sessions/{session_id}/inputs
```

## Run MogBot

From the repository root:

```bash
python main.py
```

## Load In Chrome

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select the `chrome_extension` folder.
5. Pin MogBot from the extensions menu.

## Files

- `manifest.json`: Chrome extension manifest.
- `popup.html`: popup structure.
- `popup.css`: minimalist styling.
- `popup.js`: setup, backend session calls, answer submission, and summary rendering.
- `assets/mogbot-mark.svg`: popup brand mark.
