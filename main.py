import asyncio
# COSMIC_PERSONAL_MASTER_MAIN
import os
import re
import threading
import json
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

try:
    import sounddevice as sd
except ModuleNotFoundError:
    sd = None
try:
    import psutil
except ModuleNotFoundError:
    psutil = None
from google import genai
from google.genai import types
# CosmicUI is imported lazily in desktop mode so web-only mode avoids loading PyQt.
from web_server import CosmicWebServer
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.research_agent    import research_agent
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.workflow_manager  import workflow_manager
from voice.voice_manager     import handle_voice_settings, load_voice_config, speak_with_windows_config
from experience.performance_manager import handle_performance_settings, load_performance_config, set_performance_mode
from core.state_paths import config_file, runtime_state_summary, read_json
from agent.autonomy            import (
    format_autonomy_for_prompt,
    guard_tool_call,
    handle_autonomy_settings,
    load_autonomy_config,
    update_autonomy_config,
)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = config_file("api_keys.json")
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
# COSMIC_FAST_TEXT_STATUS_TRIM
TEXT_MODEL          = os.getenv("COSMIC_TEXT_MODEL", "gemini-2.5-flash")
FAST_TEXT_ENABLED   = os.getenv("COSMIC_FAST_TEXT", "1").lower() not in {"0", "false", "no"}
FAST_TEXT_CONTEXT_CHARS = int(os.getenv("COSMIC_FAST_TEXT_CONTEXT_CHARS", "9000"))
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = int(os.getenv("COSMIC_AUDIO_CHUNK", "2048"))
AUDIO_PREFILL_CHUNKS = int(os.getenv("COSMIC_AUDIO_PREFILL_CHUNKS", "3"))
AUDIO_PREFILL_TIMEOUT = float(os.getenv("COSMIC_AUDIO_PREFILL_TIMEOUT", "0.18"))
ASSISTANT_NAME      = "COSMIC"
ASSISTANT_EXPANSION = "Centralized Omniscient System for Machine Intelligence and Control"

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are COSMIC: Centralized Omniscient System for Machine Intelligence and Control. "
            "You were created by the user speaking with you. When asked who created you, say that they did. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


def _extract_response_text(response) -> str:
    pieces: list[str] = []
    direct = getattr(response, "text", None)
    if direct:
        pieces.append(str(direct))
    try:
        server_content = getattr(response, "server_content", None)
        model_turn = getattr(server_content, "model_turn", None)
        for part in getattr(model_turn, "parts", []) or []:
            text = getattr(part, "text", None)
            if text:
                pieces.append(str(text))
    except Exception:
        pass
    cleaned: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        piece = _clean_transcript(piece)
        if piece and piece not in seen:
            seen.add(piece)
            cleaned.append(piece)
    return " ".join(cleaned).strip()


def _extract_generate_content_text(response) -> str:
    """Extract text from normal Gemini generate_content responses."""
    pieces: list[str] = []
    direct = getattr(response, "text", None)
    if direct:
        pieces.append(str(direct))
    try:
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", None)
                if text:
                    pieces.append(str(text))
    except Exception:
        pass
    cleaned: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        piece = _clean_transcript(piece)
        if piece and piece not in seen:
            seen.add(piece)
            cleaned.append(piece)
    return "\n".join(cleaned).strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for quick one-shot information. Use research_agent instead for autonomous background research.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "research_agent",
        "description": (
            "Starts or manages autonomous COSMIC research missions. "
            "Use when the user asks COSMIC to research, investigate, study, learn about, "
            "track, or think through a topic on its own. It runs in the background, posts "
            "progress updates, creates a report, and can save useful findings into memory."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | status | list | get | cancel"},
                "topic": {"type": "STRING", "description": "Research topic or question for a new mission"},
                "task_id": {"type": "STRING", "description": "Mission ID for status, get, or cancel"},
                "depth": {"type": "STRING", "description": "quick | standard | deep. Default: standard"},
                "save_to_memory": {"type": "BOOLEAN", "description": "Save key findings into COSMIC long-term memory. Default: true"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'find and organize files'. "
            "DO NOT use for research missions; use research_agent. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_cosmic",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop COSMIC. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "workflow_manager",
        "description": (
            "Creates and manages reusable COSMIC workflows. Use this for named routines the user wants "
            "to save and run again. Supports create, list, get, update, delete, run, enable, and disable. "
            "For create/update, provide explicit ordered tool steps. Use agent_task for one-off multi-step work."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "create | list | get | update | delete | run | enable | disable"
                },
                "workflow_id": {"type": "STRING", "description": "Saved workflow ID"},
                "name": {"type": "STRING", "description": "Workflow name; also accepted as its identifier"},
                "new_name": {"type": "STRING", "description": "Replacement name for update"},
                "description": {"type": "STRING", "description": "What the workflow accomplishes"},
                "enabled": {"type": "BOOLEAN", "description": "Whether the workflow may run"},
                "steps": {
                    "type": "ARRAY",
                    "description": "Ordered action steps for create/update",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "tool": {"type": "STRING", "description": "COSMIC action tool name"},
                            "parameters": {
                                "type": "STRING",
                                "description": "A JSON object string containing the arguments for that tool"
                            },
                            "description": {"type": "STRING", "description": "Short purpose of this step"}
                        },
                        "required": ["tool", "parameters"]
                    }
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "voice_settings",
        "description": (
            "View, test, list, or update COSMIC voice settings. "
            "Use this when Dhaval asks to change Gemini voice, list Windows voices, "
            "test Windows voice, or prepare Windows voice mode."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "status | list | set | test"},
                "engine": {"type": "STRING", "description": "gemini | windows | hybrid"},
                "gemini_voice": {"type": "STRING", "description": "Gemini Live prebuilt voice name, e.g. Charon"},
                "voice_name": {"type": "STRING", "description": "Alias for gemini_voice"},
                "windows_voice": {"type": "STRING", "description": "Installed Windows voice name or partial name"},
                "rate": {"type": "INTEGER", "description": "Windows voice rate from -10 to 10"},
                "volume": {"type": "INTEGER", "description": "Windows voice volume from 0 to 100"},
                "text": {"type": "STRING", "description": "Text to speak during a voice test"},
                "windows_fallback": {"type": "BOOLEAN", "description": "Whether Windows voice can be used as fallback"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "performance_settings",
        "description": (
            "View or update COSMIC Mark 5 performance mode. "
            "Use this when Dhaval asks to make COSMIC faster, smoother, cinematic, balanced, or performance focused."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "status | set | update"},
                "mode": {"type": "STRING", "description": "cinematic | balanced | performance"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "autonomy_settings",
        "description": (
            "View or update COSMIC's Mark 5 safe autonomy settings. "
            "Use this when Dhaval asks to change autonomy level, research depth, background research, "
            "memory updates, or confirmation behavior."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "status | set | update"},
                "level": {"type": "STRING", "description": "low | balanced | high"},
                "research_default_depth": {"type": "STRING", "description": "quick | standard | deep"},
                "allow_background_research": {"type": "BOOLEAN", "description": "Allow autonomous research missions"},
                "allow_multistep_tasks": {"type": "BOOLEAN", "description": "Allow background multi-step tasks"},
                "allow_memory_updates": {"type": "BOOLEAN", "description": "Allow COSMIC to save useful memories"},
                "progress_updates": {"type": "BOOLEAN", "description": "Allow COSMIC to post progress updates"},
                "protected_actions_require_confirmation": {"type": "BOOLEAN", "description": "Keep risky actions behind confirmation"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, research findings, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "research — concise learned findings from completed research missions | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

class CosmicLive:

    def __init__(self, ui):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._last_net = psutil.net_io_counters() if psutil else None
        self._last_net_t = time.time()
        self._status_cache_lock = threading.Lock()
        self._status_cache = {}
        self._status_cache_t = 0.0
        self._confirmation_lock = threading.Lock()
        self._confirmations = []
        self._confirmation_counter = 0
        self._approved_guard_keys = set()


    # COSMIC_PERSONAL_MASTER_STATUS_CONFIRMATIONS
    def _confirmation_key(self, tool_name: str, parameters: dict) -> str:
        try:
            payload = json.dumps(parameters or {}, sort_keys=True, ensure_ascii=False)
        except Exception:
            payload = str(parameters)
        return f"{tool_name}:{payload}"

    def _add_confirmation(self, tool_name: str, parameters: dict, reason: str) -> dict:
        key = self._confirmation_key(tool_name, parameters)
        with self._confirmation_lock:
            for item in self._confirmations:
                if item.get("key") == key and item.get("status") == "pending":
                    return item
            self._confirmation_counter += 1
            item = {
                "id": f"confirm-{self._confirmation_counter}",
                "key": key,
                "tool": str(tool_name),
                "parameters": parameters or {},
                "reason": str(reason),
                "status": "pending",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._confirmations.insert(0, item)
            self._confirmations = self._confirmations[:20]
            return item

    def get_confirmations(self) -> dict:
        with self._confirmation_lock:
            return {"items": [dict(item) for item in self._confirmations]}

    def resolve_confirmation(self, confirmation_id: str, approved: bool) -> bool:
        selected = None
        with self._confirmation_lock:
            for item in self._confirmations:
                if item.get("id") == confirmation_id:
                    item["status"] = "approved" if approved else "denied"
                    item["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    selected = dict(item)
                    break
        if not selected:
            return False
        if not approved:
            self.ui.write_log(f"Autonomy Guard: denied {selected.get('tool')}.")
            return True
        self.ui.write_log(f"Autonomy Guard: approved {selected.get('tool')}; executing once.")
        self._approved_guard_keys.add(selected.get("key", ""))
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._execute_approved_confirmation(selected),
                self._loop,
            )
            return True
        self.ui.write_log("Autonomy Guard: Live loop is not ready, so the approved action was not executed.")
        return True

    async def _execute_approved_confirmation(self, item: dict) -> None:
        fc = SimpleNamespace(
            id=f"approved-{item.get('id', 'confirmation')}",
            name=item.get("tool"),
            args=item.get("parameters") or {},
        )
        try:
            response = await self._execute_tool(fc)
            payload = getattr(response, "response", None)
            result = payload.get("result") if isinstance(payload, dict) else payload
            self.ui.write_log(f"Autonomy Guard: approved action finished — {str(result or 'Done.')[:180]}")
        except Exception as exc:
            self.ui.write_log(f"Autonomy Guard: approved action failed — {exc}")


    def _on_text_command(self, text: str):
        self.submit_text(text)

    def submit_text(self, text: str, source: str | None = None) -> bool:
        text = str(text).strip()
        if not self._loop or not self.session:
            return False
        if not text:
            return False
        if source:
            self.ui.write_log(f"{source}: {text}")
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )
        return True



    def submit_web_message(self, text: str, source: str | None = "Web") -> bool:
        """Route browser/phone typed messages through a faster text path when safe.

        Local-control, research, workflow, and file/action requests still go through
        Gemini Live so tool calling and laptop control remain available.
        """
        text = str(text).strip()
        if not text:
            return False
        needs_live = self._should_use_live_for_text(text)
        live_ready = bool(self._loop and self.session)
        if FAST_TEXT_ENABLED and (not needs_live or not live_ready):
            if source:
                self.ui.write_log(f"{source}: {text}")
            if needs_live and not live_ready:
                self.ui.write_log("SYS: Live control mode is reconnecting; answering through fast text mode for now.")
            threading.Thread(
                target=self._fast_text_worker,
                args=(text,),
                daemon=True,
                name="CosmicFastText",
            ).start()
            return True
        return self.submit_text(text, source=source)

    def _should_use_live_for_text(self, text: str) -> bool:
        lowered = str(text or "").lower().strip()
        control_patterns = [
            r"\b(open|launch|start|close|quit|kill)\b",
            r"\b(click|type|press|scroll|screenshot|screen|desktop|computer)\b",
            r"\b(file|folder|download|upload|rename|move|copy|delete|create|save)\b",
            r"\b(remind|calendar|schedule|task|workflow|agent task)\b",
            r"\b(research|search the web|google|browse|website|youtube|play)\b",
            r"\b(send|message|whatsapp|email|call)\b",
            r"\b(settings|performance|voice|mute|unmute|shutdown|restart)\b",
            r"\b(install|run|execute|terminal|powershell|cmd)\b",
        ]
        return any(re.search(pattern, lowered) for pattern in control_patterns)

    def _fast_text_system_instruction(self) -> str:
        from datetime import datetime

        now = datetime.now().strftime("%A, %B %d, %Y — %I:%M %p")
        identity_ctx = (
            f"You are {ASSISTANT_NAME}, short for {ASSISTANT_EXPANSION}. "
            "You were created by Dhaval, the user speaking with you. "
            "Never identify yourself as JARVIS."
        )
        try:
            mem_str = format_memory_for_prompt(load_memory())
        except Exception:
            mem_str = ""
        if mem_str and len(mem_str) > FAST_TEXT_CONTEXT_CHARS:
            mem_str = mem_str[:FAST_TEXT_CONTEXT_CHARS] + "\n[Memory context trimmed for fast response mode.]"
        try:
            sys_prompt = _load_system_prompt()
        except Exception:
            sys_prompt = ""
        if sys_prompt and len(sys_prompt) > FAST_TEXT_CONTEXT_CHARS:
            sys_prompt = sys_prompt[:FAST_TEXT_CONTEXT_CHARS] + "\n[System prompt trimmed for fast response mode.]"

        return "\n\n".join(
            part
            for part in [
                identity_ctx,
                f"Current local time: {now}.",
                format_autonomy_for_prompt(),
                mem_str,
                sys_prompt,
                (
                    "FAST WEB TEXT MODE: Answer typed web/phone questions directly, clearly, and quickly. "
                    "Do not pretend to control the laptop in this mode. If the user asks for laptop control, "
                    "research, files, workflows, or protected actions, say it should be routed to COSMIC Live/control mode."
                ),
            ]
            if part
        )

    def _generate_fast_text_response(self, text: str) -> str:
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"},
        )
        model = os.getenv("COSMIC_TEXT_MODEL", TEXT_MODEL)
        system_instruction = self._fast_text_system_instruction()
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                ),
            )
        except TypeError:
            # Older google-genai builds may not accept config objects exactly the same way.
            response = client.models.generate_content(
                model=model,
                contents=f"{system_instruction}\n\nDhaval: {text}\n\nCOSMIC:",
            )
        answer = _extract_generate_content_text(response)
        if not answer:
            answer = "I received that, but the fast text model did not return a readable response."
        return answer

    def _fast_text_worker(self, text: str) -> None:
        start = time.perf_counter()
        self.ui.set_state("THINKING")
        try:
            answer = self._generate_fast_text_response(text)
            elapsed = time.perf_counter() - start
            self.ui.write_log(f"Cosmic: {answer}")
            self.ui.write_log(f"SYS: Fast text response delivered in {elapsed:.1f}s.")
            if not self.ui.muted:
                self.speak(answer)
        except Exception as exc:
            self.ui.write_log(f"ERR: Fast text route failed — {exc}")
            if self._loop and self.session:
                self.ui.write_log("SYS: Falling back to Gemini Live route.")
                self.submit_text(text, source=None)
        finally:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    def _voice_engine(self) -> str:
        try:
            return str(load_voice_config().get("engine", "windows")).lower().strip()
        except Exception:
            return "windows"

    def _use_windows_voice(self) -> bool:
        return self._voice_engine() == "windows"

    def _speak_windows_async(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return

        def _worker():
            self.set_speaking(True)
            try:
                speak_with_windows_config(text, wait=True)
            except Exception as exc:
                self.ui.write_log(f"ERR: Windows voice failed — {exc}")
            finally:
                self.set_speaking(False)

        threading.Thread(target=_worker, daemon=True, name="CosmicWindowsVoice").start()

    def get_status(self) -> dict:
        now = time.time()
        with self._status_cache_lock:
            if self._status_cache and now - self._status_cache_t < 1.25:
                return dict(self._status_cache)
        metrics = self._system_snapshot()
        live_connected = bool(self.session and self._loop and self._loop.is_running())
        text_connected = bool(FAST_TEXT_ENABLED)
        payload = {
            "name": ASSISTANT_NAME,
            "expanded_name": ASSISTANT_EXPANSION,
            "connected": bool(live_connected or text_connected),
            "live_connected": live_connected,
            "text_connected": text_connected,
            "state": self.ui.get_state(),
            "muted": bool(self.ui.muted),
            "metrics": metrics,
            "voice": load_voice_config(),
            "autonomy": load_autonomy_config(),
            "background_tasks": self._background_task_snapshot(),
            "research_tasks": self._research_task_snapshot(),
            "performance": load_performance_config(),
            "runtime_state": runtime_state_summary(),
            "confirmations": self.get_confirmations().get("items", []),
        }
        with self._status_cache_lock:
            self._status_cache = dict(payload)
            self._status_cache_t = now
        return payload

    def _background_task_snapshot(self) -> list[dict]:
        try:
            from agent.task_queue import get_queue
            return get_queue().get_all_statuses()[-8:]
        except Exception:
            return []

    def _research_task_snapshot(self) -> list[dict]:
        try:
            path = config_file("research_tasks.json")
            data = read_json(path, {})
            tasks = data.get("tasks", []) if isinstance(data, dict) else []
            if not isinstance(tasks, list):
                return []
            summary: list[dict] = []
            for task in tasks[:8]:
                if not isinstance(task, dict):
                    continue
                progress = task.get("progress", [])
                if isinstance(progress, list):
                    progress = progress[-3:]
                else:
                    progress = []
                result = str(task.get("result") or "")
                summary.append(
                    {
                        "id": task.get("id", ""),
                        "topic": task.get("topic", ""),
                        "depth": task.get("depth", ""),
                        "status": task.get("status", ""),
                        "created_at": task.get("created_at", ""),
                        "updated_at": task.get("updated_at", ""),
                        "confidence": task.get("confidence", ""),
                        "source_count": task.get("source_count", 0),
                        "progress": progress,
                        "report_path": task.get("report_path", ""),
                        "result_preview": result[:240] if result else "",
                    }
                )
            return summary
        except Exception:
            return []

    def set_performance(self, mode: str) -> bool:
        try:
            previous = str(load_performance_config().get("mode", "performance")).lower().strip()
            config = set_performance_mode(mode)
            current = str(config.get("mode", "performance")).lower().strip()
            if current != previous:
                self.ui.write_log(f"Web: Performance mode set to {current}.")
            return True
        except Exception as exc:
            self.ui.write_log(f"Web: Performance setting failed: {exc}")
            return False

    def set_autonomy(self, level: str) -> bool:
        try:
            config = update_autonomy_config({"level": level})
            self.ui.write_log(f"Web: Autonomy level set to {config.get('level', 'balanced')}.")
            return True
        except Exception as exc:
            self.ui.write_log(f"Web: Autonomy setting failed: {exc}")
            return False

    def set_muted(self, muted: bool) -> bool:
        self.ui.muted = bool(muted)
        state = "muted" if self.ui.muted else "active"
        self.ui.write_log(f"Web: Microphone {state}.")
        return True

    def _system_snapshot(self) -> dict:
        if psutil is None:
            return {
                "available": False,
                "cpu": 0,
                "memory": 0,
                "network_mbps": 0,
                "processes": 0,
                "uptime_seconds": 0,
                "health": 0,
                "health_label": "Unavailable",
            }

        try:
            cpu = float(psutil.cpu_percent(interval=None))
            memory = float(psutil.virtual_memory().percent)
            now = time.time()
            net = psutil.net_io_counters()
            network_mbps = 0.0
            if self._last_net is not None:
                elapsed = max(0.001, now - self._last_net_t)
                traffic = (
                    net.bytes_sent
                    - self._last_net.bytes_sent
                    + net.bytes_recv
                    - self._last_net.bytes_recv
                )
                network_mbps = traffic / elapsed / (1024 * 1024)
            self._last_net = net
            self._last_net_t = now
            processes = len(psutil.pids())
            uptime_seconds = max(0, int(now - psutil.boot_time()))

            cpu_penalty = max(0.0, cpu - 55) * 0.55
            memory_penalty = max(0.0, memory - 65) * 0.85
            network_penalty = min(18.0, network_mbps * 1.8)
            health = max(0, min(100, round(100 - cpu_penalty - memory_penalty - network_penalty)))
            if health >= 80:
                label = "Optimal"
            elif health >= 55:
                label = "Busy"
            else:
                label = "High Load"

            return {
                "available": True,
                "cpu": round(cpu, 1),
                "memory": round(memory, 1),
                "network_mbps": round(network_mbps, 2),
                "processes": processes,
                "uptime_seconds": uptime_seconds,
                "health": health,
                "health_label": label,
            }
        except Exception:
            return {
                "available": False,
                "cpu": 0,
                "memory": 0,
                "network_mbps": 0,
                "processes": 0,
                "uptime_seconds": 0,
                "health": 0,
                "health_label": "Unavailable",
            }

    async def _run_workflow_step(self, tool_name: str, parameters: dict) -> str:
        step_call = SimpleNamespace(
            id=f"workflow-{tool_name}",
            name=tool_name,
            args=parameters,
        )
        response = await self._execute_tool(step_call)
        payload = getattr(response, "response", None)
        if isinstance(payload, dict):
            result = str(payload.get("result", "Done."))
        else:
            result = str(payload or "Done.")
        if result.startswith("Unknown tool:") or (result.startswith("Tool '") and " failed:" in result):
            raise RuntimeError(result)
        return result

    def set_speaking(self, value: bool):
        value = bool(value)
        with self._speaking_lock:
            if self._is_speaking == value:
                return
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if self._use_windows_voice():
            self._speak_windows_async(text)
            return
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        identity_ctx = (
            f"[IDENTITY]\nYour name is {ASSISTANT_NAME}, short for "
            f"{ASSISTANT_EXPANSION}.\n"
            "You were created by the user speaking with you. If asked who created you, "
            "say clearly that the user did. Never identify yourself as JARVIS.\n\n"
        )
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [identity_ctx, time_ctx, format_autonomy_for_prompt()]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        voice_cfg = load_voice_config()
        voice_engine = str(voice_cfg.get("engine", "windows")).lower().strip()
        if voice_engine == "windows":
            # Gemini Live currently connects most reliably with audio output.
            # COSMIC discards Gemini audio in Windows voice mode, uses the
            # output transcript as text, then speaks it through Windows SAPI.
            return types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                output_audio_transcription={},
                input_audio_transcription={},
                system_instruction="\n".join(parts),
                tools=[{"function_declarations": TOOL_DECLARATIONS}],
                session_resumption=types.SessionResumptionConfig(),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_cfg.get("gemini_voice", "Charon")
                        )
                    )
                ),
            )

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_cfg.get("gemini_voice", "Charon")
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        guard_key = self._confirmation_key(name, args)
        guard_override = guard_key in self._approved_guard_keys
        if guard_override:
            self._approved_guard_keys.discard(guard_key)
            allowed, guard_message = True, "Approved once by Dhaval."
        else:
            allowed, guard_message = guard_tool_call(name, args)
        if not allowed:
            item = self._add_confirmation(name, args, guard_message)
            self.ui.write_log(f"Autonomy Guard: {guard_message} (waiting as {item.get('id')})")
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": guard_message, "blocked": True, "confirmation_id": item.get("id")},
            )

        print(f"[COSMIC] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "voice_settings":
                r = await loop.run_in_executor(None, lambda: handle_voice_settings(args))
                result = r or "Voice settings updated."

            elif name == "performance_settings":
                result = handle_performance_settings(args)
                self.ui.write_log("Performance: " + str(result).splitlines()[0])

            elif name == "autonomy_settings":
                result = handle_autonomy_settings(args)
                self.ui.write_log("Autonomy: " + str(result).splitlines()[0])

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                def _task_progress(task_id: str, message: str):
                    self.ui.write_log(f"Task {task_id}: {message}")
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak, on_progress=_task_progress)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "research_agent":
                def _progress(message: str):
                    self.ui.write_log(f"Research: {message}")

                r = await loop.run_in_executor(
                    None,
                    lambda: research_agent(parameters=args, progress_callback=_progress)
                )
                result = r or "Research mission updated."

            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "workflow_manager":
                result = await workflow_manager(
                    parameters=args,
                    step_runner=self._run_workflow_step,
                )

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shutdown_cosmic":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[COSMIC] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[COSMIC] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                cosmic_speaking = self._is_speaking
            if not cosmic_speaking and not self.ui.muted:
                data = indata.tobytes()
                def _push_input():
                    try:
                        if self.out_queue.full():
                            try:
                                self.out_queue.get_nowait()
                            except Exception:
                                pass
                        self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                    except Exception:
                        pass
                loop.call_soon_threadsafe(_push_input)

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[COSMIC] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[COSMIC] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[COSMIC] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    text_delta = _extract_response_text(response)
                    if text_delta:
                        out_buf.append(text_delta)

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        if not self._use_windows_voice():
                            self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Cosmic: {full_out}")
                                if self._use_windows_voice():
                                    self._speak_windows_async(full_out)
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[COSMIC] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[COSMIC] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[COSMIC] Audio playback started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            latency="high",
        )
        stream.start()

        async def _next_chunk(timeout: float = 0.1):
            return await asyncio.wait_for(self.audio_in_queue.get(), timeout=timeout)

        try:
            while True:
                try:
                    first = await _next_chunk(0.12)
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                buffered = [first]
                deadline = asyncio.get_running_loop().time() + AUDIO_PREFILL_TIMEOUT
                while (
                    len(buffered) < max(1, AUDIO_PREFILL_CHUNKS)
                    and asyncio.get_running_loop().time() < deadline
                ):
                    try:
                        buffered.append(await _next_chunk(0.025))
                    except asyncio.TimeoutError:
                        break

                self.set_speaking(True)
                for chunk in buffered:
                    await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[COSMIC] Playback error: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[COSMIC] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                live_model = os.getenv("COSMIC_LIVE_MODEL", LIVE_MODEL)

                async with (
                    client.aio.live.connect(model=live_model, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue(maxsize=120)
                    self.out_queue      = asyncio.Queue(maxsize=30)
                    self._turn_done_event = asyncio.Event()

                    print("[COSMIC] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: COSMIC online.")

                    tg.create_task(self._receive_audio())
                    if _is_web_only_mode():
                        self.ui.write_log("SYS: Web-only mode active. Local mic/audio streams are disabled.")
                    else:
                        tg.create_task(self._send_realtime())
                        tg.create_task(self._listen_audio())
                        if not self._use_windows_voice():
                            tg.create_task(self._play_audio())

            except Exception as e:
                self.ui.write_log(f"ERR: Live connection failed — {e}")
                print(f"[COSMIC] Live connection failed: {e}")
                traceback.print_exc()
            self.session = None
            self._loop = None
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[COSMIC] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)


def _is_web_only_mode() -> bool:
    return (
        "--web-only" in sys.argv
        or "--no-desktop" in sys.argv
        or os.getenv("COSMIC_WEB_ONLY", "0").lower() in {"1", "true", "yes"}
    )


class HeadlessCosmicUI:
    """Minimal UI adapter for Mark5 web-only mode.

    It keeps COSMIC's backend, tools, logs, web dashboard, phone access,
    and laptop-control abilities alive without creating the heavy PyQt window.
    """

    def __init__(self):
        self.on_text_command = None
        self.current_file = None
        self.muted = os.getenv("COSMIC_WEB_ONLY_MIC", "0").lower() not in {"1", "true", "yes"}
        self._state_value = "STARTING"
        self._log_history: list[str] = []
        self._log_history_start = 0
        self._log_history_lock = threading.Lock()
        self._last_log_text = ""
        self._performance_warning_seen = False
        self.write_log("SYS: COSMIC Mark5 web-only mode starting. Desktop UI disabled.")
        self.write_log("SYS: Local mic/audio streams are disabled for performance. Use browser/phone commands.")

    def wait_for_api_key(self):
        if not API_CONFIG_PATH.exists():
            raise RuntimeError(
                f"Gemini API key config is missing: {API_CONFIG_PATH}. "
                "Open full COSMIC once to configure it, or create config/api_keys.json."
            )
        try:
            data = read_json(API_CONFIG_PATH, {})
        except Exception as exc:
            raise RuntimeError(f"Could not read API key config: {exc}") from exc
        if not data.get("gemini_api_key"):
            raise RuntimeError("Gemini API key is missing in config/api_keys.json.")

    def set_state(self, state: str):
        self._state_value = str(state or "STARTING")

    def get_state(self) -> str:
        return self._state_value

    def write_log(self, text: str):
        text = str(text)
        if not text.strip():
            return
        if text == getattr(self, "_last_log_text", ""):
            return
        if "Performance setting failed" in text:
            if getattr(self, "_performance_warning_seen", False):
                return
            self._performance_warning_seen = True
        self._last_log_text = text
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] {text}")
        with self._log_history_lock:
            self._log_history.append(text)
            if len(self._log_history) > 400:
                overflow = len(self._log_history) - 400
                self._log_history = self._log_history[overflow:]
                self._log_history_start += overflow

    def get_logs(self, after: int = 0) -> dict:
        with self._log_history_lock:
            after = max(self._log_history_start, int(after or 0))
            relative = min(after - self._log_history_start, len(self._log_history))
            return {
                "start": after,
                "next": self._log_history_start + len(self._log_history),
                "items": self._log_history[relative:],
            }

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

def main():
    web_only = _is_web_only_mode()
    if web_only:
        os.environ.setdefault("COSMIC_PERFORMANCE_MODE", "performance")
        os.environ.setdefault("COSMIC_PHONE_ACCESS", "1")
        os.environ.setdefault("COSMIC_VOICE_ENGINE", "windows")
        ui = HeadlessCosmicUI()
        ui.wait_for_api_key()
    else:
        from ui import CosmicUI
        ui = CosmicUI(str(BASE_DIR / "face.png"))

    def runner():
        ui.wait_for_api_key()
        cosmic = CosmicLive(ui)
        try:
            phone_access = (
                web_only
                or "--phone" in sys.argv
                or "--mobile" in sys.argv
                or os.getenv("COSMIC_PHONE_ACCESS", "0").lower() in {"1", "true", "yes"}
            )
            web_host = "0.0.0.0" if phone_access else None
            web_kwargs = {"host": web_host} if web_host else {}
            web_console = CosmicWebServer(
                submit_message=lambda text: cosmic.submit_web_message(text, source="Web"),
                get_status=cosmic.get_status,
                get_logs=ui.get_logs,
                set_muted=cosmic.set_muted,
                set_autonomy=cosmic.set_autonomy,
                set_performance=cosmic.set_performance,
                get_confirmations=cosmic.get_confirmations,
                resolve_confirmation=cosmic.resolve_confirmation,
                write_log=ui.write_log,
                **web_kwargs,
            )
            web_url = web_console.start()
            ui.write_log(f"SYS: Web console available at {web_url}")
            if web_only:
                ui.write_log("SYS: Web-only performance mode active. Desktop window skipped.")
            if phone_access:
                ui.write_log("SYS: Phone access enabled. Use Tailscale for mobile-data access.")
                urls = web_console.access_urls()
                for url in urls.get("tailscale", []):
                    ui.write_log(f"PHONE: Tailscale link {url}")
                for url in urls.get("network", [])[:3]:
                    ui.write_log(f"PHONE: Same Wi-Fi link {url}")
            print(f"[COSMIC] Web console: {web_url}")
            if phone_access:
                print("[COSMIC] Phone access URLs:")
                for label, urls in web_console.access_urls().items():
                    if isinstance(urls, list):
                        for url in urls:
                            print(f"  {label}: {url}")
            if "--open-web" in sys.argv or web_only:
                import webbrowser
                webbrowser.open(web_url)
        except Exception as exc:
            ui.write_log(f"ERR: Web console could not start — {exc}")
            print(f"[COSMIC] Web console failed: {exc}")
        try:
            asyncio.run(cosmic.run())
        except KeyboardInterrupt:
            print("Shutting down...")

    worker = threading.Thread(target=runner, daemon=not web_only, name="CosmicMark5Runner")
    worker.start()
    if web_only:
        print("[COSMIC] Mark5 web-only mode is running. Close this window or press Ctrl+C to stop.")
        try:
            while worker.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("[COSMIC] Web-only mode stopped.")
    else:
        ui.root.mainloop()


if __name__ == "__main__":
    main()
