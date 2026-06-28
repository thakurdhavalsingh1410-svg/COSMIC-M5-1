# COSMIC Mark5 Render Cloud

This is the cloud-safe COSMIC Mark5 build for Render.

## What this version can do

- Open from anywhere through a Render URL
- Chat through Gemini
- Run background research missions
- Store cloud memory, tasks, goals, and calendar data
- Work from phone even when Dhaval's laptop is off

## What this version cannot do

- Directly control Dhaval's laptop while the laptop is off
- Use Windows voice
- Open local Windows apps/files
- Perform shutdown/restart/delete actions on Dhaval's laptop

Use local Mark5 for laptop control. Use Render Mark5 for always-online intelligence.

## Render setup

1. Create a new Render Web Service.
2. Upload/push this folder to GitHub, then connect that repo to Render.
3. Use:
   - Build command: `pip install -r requirements-cloud.txt`
   - Start command: `python cloud_app.py`
4. Add environment variables:
   - `GEMINI_API_KEY` = your Gemini API key
   - `COSMIC_WEB_PIN` = a private PIN for opening COSMIC
   - `PYTHON_VERSION` = `3.12.10`
   - optional: `COSMIC_TEXT_MODEL` = `gemini-2.5-flash`
5. Deploy.

## Persistent memory

Render's normal filesystem can be temporary. For permanent cloud memory/research/calendar:

1. Add a Render persistent disk.
2. Mount it at `/var/data`.
3. Add env var:
   - `COSMIC_STATE_DIR=/var/data/cosmic`

Without a persistent disk, COSMIC can still run, but memory may reset after redeploys/restarts.

## Open COSMIC

After deploy, open your Render URL. If `COSMIC_WEB_PIN` is set, COSMIC will ask for the PIN.
