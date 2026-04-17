# Cold Email Sender

A local Flask app for sending personalized outreach emails.

## What This Public Repo Includes
- Application source code (`app.py`)
- Web UI (`templates/index.html`)
- Startup script (`start.bat`)
- Dependency list (`requirements.txt`)

## Local Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create `.env` from `.env.example`.
3. Fill environment variables with your own sender email and app password.

## Run
- Windows: double-click `start.bat`
- Or run:
  ```bash
  python app.py
  ```

The app runs on `http://localhost:5000`.

## Data and Secrets
This repo intentionally excludes private runtime files and secrets (for example `.env`, contact logs, and local counters).

## Template Placeholders
The app supports:
- `[name]`
- `[company]`
- `[X]` (optional)
