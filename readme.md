# COSMIC

## Centralized Omniscient System for Machine Intelligence and Control

COSMIC is a real-time personal AI assistant that can hear, see, reason, manage files, control the computer, run reusable workflows, and accept commands from either its desktop application or a local web browser.

This customized assistant identifies the current user as its creator. When asked who created it, COSMIC answers: **"You created me."**

## Capabilities

| Feature | Description |
|---|---|
| Real-time voice | Low-latency multilingual conversation through Gemini Live |
| Desktop access | Native PyQt desktop console with microphone and typed commands |
| Local web access | COSMIC dashboard served locally at `http://localhost:8765` |
| Phone access | Install COSMIC to your phone home screen and connect through Wi-Fi or Tailscale |
| Reusable workflows | Create, inspect, update, enable/disable, delete, and run named workflows |
| Autonomous research | Start background research missions, get progress updates, save reports, and keep useful findings in memory |
| System control | Launch apps, manage files, control settings, and automate browser tasks |
| Visual awareness | Analyze the screen or webcam |
| Persistent memory | Remember projects, preferences, and personal context |
| File processing | Work with documents, images, code, audio, video, archives, and spreadsheets |

## Quick start

```bash
pip install -r requirements.txt
playwright install
python main.py
```

## App launcher

Use the Desktop shortcut named **COSMIC App Launcher** to open a small local launcher window. It works offline and can:

- start COSMIC
- open the local web dashboard
- open the project folder
- check that the main project files exist

Launcher files:

- `cosmic_app_launcher.pyw` - the small launcher app
- `Start COSMIC App Launcher.bat` - starts the launcher app
- `Start COSMIC.bat` - starts COSMIC directly
- `Start COSMIC Phone Access.bat` - starts COSMIC with phone/PWA access enabled
- `assets/cosmic.ico` - COSMIC launcher icon

COSMIC starts the desktop application and its local web dashboard together. Open the web dashboard automatically with:

```bash
python main.py --open-web
```

The web server binds to `127.0.0.1` by default, so it is available only on the same computer. The host and port can be changed with `COSMIC_WEB_HOST` and `COSMIC_WEB_PORT` environment variables. Only expose it to a network you trust, because web commands can invoke COSMIC's computer-control tools.

## COSMIC on your phone

COSMIC can now run as a phone-installable web app while the real COSMIC core keeps running on your laptop.

Use the new launcher:

```bash
Start COSMIC Phone Access.bat
```

Or run:

```bash
python main.py --phone --open-web
```

Phone behavior:

- laptop = COSMIC core, memory, tools, workflows, research missions, and computer control
- phone = portable command panel
- Android/iPhone can install COSMIC to the home screen as a PWA
- the mobile layout keeps the command bar, logs, tasks, system status, and mute button usable on a phone

To use COSMIC on the same Wi-Fi:

1. Start COSMIC with `Start COSMIC Phone Access.bat`.
2. Open the COSMIC web dashboard on your laptop.
3. In the Home panel, copy the **Same Wi-Fi** phone link.
4. Open that link on your phone.
5. Install it:
   - Android Chrome: menu `⋮` -> `Add to Home screen` or `Install app`
   - iPhone Safari: Share -> `Add to Home Screen`

Note: full PWA install prompts work best over HTTPS. On plain `http://` links, your phone browser may show "Add to Home Screen" as a shortcut instead of a full install prompt. That is still usable as the COSMIC phone launcher.

To use COSMIC outside your house with mobile data:

1. Install Tailscale on your laptop and phone.
2. Sign in to the same Tailscale account on both devices.
3. Keep your laptop on, awake, connected to the internet, and running COSMIC in phone mode.
4. Open the COSMIC Home panel and use the **Tailscale / mobile data** link if shown.
5. If a Tailscale link is not shown, open Tailscale on your phone, copy your laptop's `100.x.x.x` address, and open:

```text
http://YOUR-TAILSCALE-IP:8765
```

Security note: do not expose COSMIC with public router port forwarding. COSMIC can control your laptop, so use Tailscale or another private VPN for outside-home access.

The built-in `localhost:8765` page now matches the native COSMIC dashboard style and includes:

- interactive Home, Memory, Knowledge, Tasks, Calendar, and System panels
- editable browser-side Tasks schedule
- live backend status, health, CPU, memory, network, process count, and uptime
- COSMIC AI log/chat card
- command input connected to COSMIC
- web mute/unmute button connected to COSMIC's real microphone state
- phone/PWA install support with responsive mobile layout

If you specifically want to serve the optional built React `dist/` app instead, set `COSMIC_WEB_USE_DIST=1` before launching COSMIC.

## COSMIC React dashboard

The new futuristic laptop dashboard lives in `src/` and runs as a local Vite web app.

```bash
npm install
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
```

When COSMIC's Python backend is also running on `http://127.0.0.1:8765`, the React command bar can send commands to it during development.

To build the React dashboard into COSMIC's built-in web server:

```bash
npm run build
python main.py --open-web
```

After `npm run build`, `python main.py --open-web` can serve the React dashboard from `dist/` when `COSMIC_WEB_USE_DIST=1` is set. Otherwise, COSMIC uses the built-in dashboard from `web_server.py`.

Dashboard files:

- `package.json` - React, Tailwind, Vite, and lucide-react setup
- `index.html` - web app entry page
- `src/App.jsx` - main dashboard layout
- `src/components/` - sidebar, header, COSMIC orb, cards, schedule, actions, and command bar
- `src/index.css` - Tailwind layers, glassmorphism, stars, particles, glowing borders, orb, and waveform animations

## COSMIC native desktop dashboard

The local desktop app in `ui.py` now uses the same COSMIC command-center style as the web dashboard:

- dark cosmic animated background
- neon cyan and purple glow
- glassmorphism sidebar, cards, schedule, and action panels
- animated AI orb/cosmic eye
- animated waveform
- bottom command input bar
- file intake card
- live activity log
- interactive Home, Memory, Knowledge, Tasks, Calendar, and System panels
- editable Tasks schedule stored in `config/ui_tasks.json`
- accurate live system status for CPU, memory, network, processes, uptime, and health
- preserved microphone mute, fullscreen, setup overlay, command callback, state updates, and local web log bridge

## Workflows

Workflows are saved in `config/workflows.json` when first created. They contain ordered COSMIC tool calls and remain available between launches.

Example voice or text commands:

- "Create a workflow named morning briefing that checks the weather and opens my calendar."
- "List my workflows."
- "Disable the morning briefing workflow."
- "Run my morning briefing workflow."
- "Update the morning briefing workflow to open email too."
- "Delete the morning briefing workflow."

COSMIC uses `workflow_manager` for reusable routines and keeps `agent_task` for one-time multi-step requests.

## Autonomous research missions

COSMIC can now research a topic in the background, post progress updates to the desktop/web log, save a full report, and store a concise useful finding in long-term memory.

Example voice or text commands:

- "COSMIC, research quantum computing basics for me."
- "Do a deep research mission on AI agents and save what you learn."
- "List my research missions."
- "Get the status of research mission `<task_id>`."
- "Cancel research mission `<task_id>`."

Research task history is saved in `config/research_tasks.json`. Full reports are saved in `memory/research_reports/`.

## Requirements

| Requirement | Details |
|---|---|
| OS | Windows 10/11, macOS, or Linux |
| Python | 3.11 or 3.12 |
| Node.js | Needed for the React dashboard |
| Microphone | Required for voice interaction |
| API key | Gemini API key |

## Project structure added for COSMIC

- `actions/workflow_manager.py` - persistent workflow storage and execution
- `web_server.py` - dependency-free local web console and JSON API
- `core/prompt.txt` - COSMIC identity, creator attribution, and tool-routing rules
- `src/` - React/Tailwind dashboard UI

## License and attribution

Personal and non-commercial use only under [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

COSMIC is a customized build based on the original MARK XXXIX project by [FatihMakes](https://www.youtube.com/@FatihMakes). Original project video: [YouTube setup guide](https://youtu.be/ej1f5OE3SNQ?si=lCxDhJix9ungq1Ry).

## COSMIC Mark 3 security and research memory

- Remote phone commands are protected by a local phone PIN stored in config/phone_access.json.
- Local laptop access does not require the phone PIN.
- Research missions now save reports with source links, confidence level, date researched, and rich entries in memory/research_knowledge.json.
- The web Knowledge panel shows recent research mission status and progress.

## Mark 4 performance pass

COSMIC Mark 4 is optimized for smoother use on Dhaval's laptop:

- local starfield and orb repaint rates are reduced
- dashboard telemetry refreshes every 3 seconds instead of every second
- web/phone polling is reduced to about 2.5 seconds
- browser particle/star counts are reduced
- heavy blur and glow intensity are reduced slightly
- web dashboard honors OS reduced-motion settings
- local UI log history is capped to reduce long-session memory/UI overhead

These changes keep the same COSMIC look while lowering CPU/GPU pressure.

## Mark 4 voice stability pass

COSMIC Mark 4 includes a voice stability pass for smoother Gemini Live audio:

- audio chunk size increased from 1024 to 2048 samples by default
- output playback uses a more stable high-latency stream
- playback pre-buffers a few chunks before speaking
- repeated UI speaking-state updates are ignored instead of repainting on every audio chunk
- mic queue overflow is guarded so temporary lag does not throw callback errors
- audio queues are slightly larger to absorb short CPU/network spikes

If needed, the defaults can be changed with environment variables:

- `COSMIC_AUDIO_CHUNK`
- `COSMIC_AUDIO_PREFILL_CHUNKS`
- `COSMIC_AUDIO_PREFILL_TIMEOUT`

## COSMIC Mark 5 Part 1 foundation

Mark 5 starts as a safe branch of Mark 4. Part 1 adds the Windows voice foundation while keeping Gemini Live as the default voice engine.

Added:

- `voice/windows_voice.py` - Windows SAPI voice access using installed Windows voices
- `voice/voice_manager.py` - shared voice configuration and voice testing
- `config/voice.json` - Mark 5 voice settings
- `voice_settings` COSMIC tool - list, test, status, and update voice settings
- configurable Gemini voice name instead of hardcoded `Charon`
- Windows voice test launchers

Default engine remains `gemini` for stability. Mark 5 can later move fully to Windows voice output after the assistant response loop is refactored from Gemini Live audio to text-first responses.

## COSMIC Mark 5 full Windows voice mode

Mark 5 can now run with Windows voice output as the primary voice system.

How it works:

- Gemini Live is used for listening, reasoning, tools, and text responses.
- COSMIC requests text responses with `response_modalities=["TEXT"]`.
- COSMIC collects the final text response.
- Windows SAPI speaks the response using the voice selected in `config/voice.json`.
- Gemini-generated audio is no longer played in Windows voice mode.

Default Mark 5 voice config:

```json
"engine": "windows"
```

Useful commands inside COSMIC:

- "List Windows voices."
- "Test Windows voice."
- "Set Windows voice to Microsoft David."
- "Set Windows voice rate to 1."
- "Show voice settings."

If the selected Gemini Live model does not support text responses, set `COSMIC_LIVE_TEXT_MODEL` in the launcher/environment to a Live model that supports text responses.

## COSMIC Mark 5 Part 2 intelligence core

Part 2 adds the Mark 5 intelligence core:

- Safe Autonomy Governor with `low`, `balanced`, and `high` modes
- Protected-action guard for destructive or external actions
- Background task progress tracking
- Research mission progress visibility
- Configurable default research depth
- Autonomy controls in the web/phone System tab
- Autonomy status included in the COSMIC runtime prompt

Protected actions still require Dhaval's explicit confirmation:

- deleting or moving files
- sending messages to other people
- shutdown/restart/power actions
- uninstall/system destructive changes
- deleting workflows

## COSMIC Mark 5 Part 3 experience layer

Part 3 adds the final experience layer:

- Performance mode config in `config/performance.json`
- Performance/cinematic/balanced controls in the web/phone System tab
- Dynamic web polling based on performance mode
- Local UI animation timing reads performance config on startup
- Mark5 launcher scripts
- Mark5 self-check diagnostics
- Safe desktop shortcut installer
- Phone/web cache bump so the latest dashboard shell loads

Recommended final launch:

1. Run `Run COSMIC Mark5 Self Check.bat`
2. Run `Test COSMIC Windows Voice.bat`
3. Run `Start COSMIC Mark5.bat`
4. Optional: run `Install COSMIC Mark5 Desktop Shortcut.bat`

## Editable local calendar

COSMIC Mark5 now includes a local-first editable calendar in the web/phone dashboard.

- Events are saved in `data/calendar_events.json`.
- The Calendar tab shows a real month grid.
- You can add, edit, and delete events from the Calendar tab.
- You can export events as `cosmic-calendar.ics`.
- You can paste/import `.ics` calendar text from Google Calendar, Outlook, or Windows-compatible calendar exports.

This is intentionally local-first. Google Calendar live sync requires an online OAuth flow, while Windows Calendar does not expose a simple dependable local API. The `.ics` bridge keeps the calendar usable offline and compatible with common calendar apps.

## COSMIC Mark5 web-only mode

Mark5 includes a fast web-only launch mode for lower-end laptop performance.

Run:

`Start COSMIC Mark5 Web Only.bat`

This mode:

- keeps the COSMIC backend running locally on the laptop
- keeps laptop-control tools available
- opens the web dashboard automatically
- enables phone access
- skips the heavy PyQt desktop window
- disables local mic/audio streams for performance
- keeps Windows voice output available

Use the normal `Start COSMIC Mark5.bat` when you want the full desktop window.

## COSMIC Mark5 Live connection fix

Windows voice mode now connects to Gemini Live using audio-compatible output settings and uses output transcription for text. COSMIC still speaks through Windows voice, but the Live session no longer requests unsupported text-only output.

If COSMIC says "still connecting", check the console/web log for `ERR: Live connection failed`.

## COSMIC Mark 5 top utility buttons

- `⌁` opens install / launcher help.
- `🔔` opens recent runtime notifications.
- `🎙` opens direct voice settings and Windows voice testing.
- `⚙` opens the System tab.
- `◉` opens COSMIC status/profile shortcuts.

## Expanded Calendar UI

- Calendar tab now hides bottom quick cards to give the calendar more space.
- Month grid and event editor expand across the full workspace.
- Existing add/edit/delete and .ics import/export behavior is unchanged.

## Editable Active Goals

- Tasks tab Active Context and Goals can now be edited and saved.
- Saved project title, progress, objectives, recents, and notes are stored in `data/active_goals.json`.
- The schedule task editor remains separate.

