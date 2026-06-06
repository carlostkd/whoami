# whoami — Public Profile Aggregator + AI Profiler

```
██╗    ██╗██╗  ██╗ ██████╗  █████╗ ███╗   ███╗██╗
██║    ██║██║  ██║██╔═══██╗██╔══██╗████╗ ████║██║
██║ █╗ ██║███████║██║   ██║███████║██╔████╔██║██║
██║███╗██║██╔══██║██║   ██║██╔══██║██║╚██╔╝██║██║
╚███╔███╔╝██║  ██║╚██████╔╝██║  ██║██║ ╚═╝ ██║██║
 ╚══╝╚══╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝
```

**Search a username or email across 17+ social networks, leak databases, and the dark web — then generate an AI personality profile from everything found.**

---

## Features

- **17 social platforms**: Reddit, GitHub, Hacker News, Bluesky, Mastodon, Telegram, YouTube, Twitter/X, Instagram, Threads, Gravatar
- **Fediverse & more**: Pixelfed, PeerTube, Lemmy, Dev.to, Medium, Pinterest
- **Deep web search**: IntelX (leaks/pastes/darknet) and Ahmia (Tor `.onion` sites)
- **AI profile generation**: Sends collected data to an LLM (Anthropic, OpenAI, Google Gemini, Groq, Lumo, Ollama) for behavioral analysis
- **Scan mode**: `--scan username` checks every platform automatically
- **Two versions**: CLI (`osint_profiler.py`) and GUI (`osint_profiler_gui.py`)
- **Rich formatted output**: Tables, panels, colored output via the `rich` library

---

## Installation

```bash
# Clone or copy the files
git clone <repo>  # or just download osint_profiler.py and osint_profiler_gui.py

# Install dependencies
pip install requests

# Optional: rich output
pip install rich

# Optional: AI profile generation
pip install anthropic openai google-genai groq

# Optional: GUI
# (tkinter is included with Python on most systems)
```

No Docker, no config files — just run it.

> A pre-filled `.env.example` is included. Rename it to `.env` for easy configuration of API keys (IntelX, Reddit, Telegram, etc.).

---

## Usage — CLI

### Quick scan (all platforms)

```bash
python osint_profiler.py --scan johndoe
python osint_profiler.py --scan johndoe --ai --save
```

### Individual platforms

```bash
python osint_profiler.py --reddit torvalds
python osint_profiler.py --github torvalds --hackernews tptacek
python osint_profiler.py --bluesky alice.bsky.social --ai
python osint_profiler.py --email user@example.com --ai --llm openai
python osint_profiler.py --telegram username
python osint_profiler.py --youtube @channel --ai
python osint_profiler.py --twitter elonmusk --ai
python osint_profiler.py --instagram username
python osint_profiler.py --threads username
python osint_profiler.py --pixelfed username
python osint_profiler.py --peertube username
python osint_profiler.py --lemmy username
python osint_profiler.py --devto username
python osint_profiler.py --medium @username
python osint_profiler.py --pinterest username
python osint_profiler.py --mastodon Gargron --mastodon-instance mastodon.social
```

### Deep web search

```bash
python osint_profiler.py --reddit torvalds --intelx           # IntelX uses 'torvalds'
python osint_profiler.py --intelx johndoe                     # IntelX only, inline query
python osint_profiler.py --email user@example.com --darkweb   # Ahmia search
python osint_profiler.py --github torvalds --intelx --darkweb --ai --save
```

### AI profile

```bash
python osint_profiler.py --scan johndoe --ai                              # Anthropic (default)
python osint_profiler.py --scan johndoe --ai --llm openai                 # OpenAI
python osint_profiler.py --scan johndoe --ai --llm google --llm-key AI... # Google Gemini
python osint_profiler.py --scan johndoe --ai --llm groq                   # Groq
python osint_profiler.py --scan johndoe --ai --llm ollama                 # Local LLM
```

Set API keys via env vars instead of `--llm-key`:

| Provider   | Env var               | Default model        |
|------------|-----------------------|----------------------|
| Anthropic  | `ANTHROPIC_API_KEY`   | `claude-sonnet-4-20250514` |
| OpenAI     | `OPENAI_API_KEY`      | `gpt-4o`            |
| Google     | `GOOGLE_API_KEY`      | `gemini-2.0-flash`  |
| Groq       | `GROQ_API_KEY`        | `deepseek-r1-distill-llama-70b` |
| Lumo       | `LUMO_API_KEY`        | `lumo`              |
| Ollama     | —                     | `llama3.2`          |

### IntelX / Twitter / YouTube API keys

```bash
export INTELX_API_KEY="your-key"
export INTELX_USER="your-email"
export TWITTER_BEARER_TOKEN="your-token"
export YOUTUBE_API_KEY="your-key"
```

---

## Usage — GUI

```bash
python osint_profiler_gui.py
```

The GUI has two tabs:

- **Sources** — scrollable panel with fields for all 11 platforms + IntelX/Dark Web checkboxes + API key fields  
  - **Quick Scan** bar at the top: type a username, click "Scan All", and it fills every field automatically
- **AI Profile** — enable/disable AI, select provider, model, and API key

Output area features:
- **PanedWindow** — drag the divider to resize input/output
- **Results panel** — colored platform tags showing what was found
- **Color-coded output** — ✓ green, ⚠ yellow, ✗ red
- **Copy Output** button — copies everything to clipboard
- **📜 Auto-scroll** toggle — freeze/unfreeze scroll during live output
- **Status bar** — shows current state (Ready / Searching... / Done)

---

## AI Profile Example

When you run with `--ai`, the tool aggregates data from all platforms and sends it to the LLM for analysis. Here's a real output:

```
Sending to LUMO for analysis...

╭─ LUMO Generated Profile ─────────────────────────────────────────────╮
│                                                                      │
│ 1. TECHNICAL SKILLS & EXPERTISE                                      │
│ • No direct evidence of technical skills, coding abilities, or       │
│   specialized expertise is present in the provided dataset.          │
│ • Conclusion: Cannot be determined from available metadata.          │
│                                                                      │
│ 2. TOPICS OF INTEREST & PASSIONS                                     │
│ • No observable indicators of hobbies, political views, or           │
│   entertainment preferences.                                         │
│ • Conclusion: Neutral profile; interests are obscured or             │
│   non-existent on these platforms.                                   │
│                                                                      │
│ 3. COMMUNICATION STYLE & PERSONALITY TRAITS                          │
│ • The Telegram bio states: "You can contact @Justin right away."     │
│   This suggests a functional, service-oriented communication style.  │
│ • Traits: Efficient, approachable, privacy-conscious.                │
│                                                                      │
│ 4. ONLINE BEHAVIOR PATTERNS                                          │
│ • Activity Level: Extremely low visibility.                          │
│ • Platform Consistency: Username Justin_Case is identical across     │
│   Telegram, Instagram, and Threads.                                  │
│ • Engagement Style: Passive or Private.                              │
│                                                                      │
│ 5. LIKELY PROFESSION OR BACKGROUND                                   │
│ • Full legal name on Telegram + "contact me immediately" bio         │
│   suggests a business or freelance client-facing role.               │
│                                                                      │
│ 6. COMMUNITY INVOLVEMENT                                             │
│ • No evidence of participation in groups, channels, or comments.     │
│                                                                      │
│ 7. SUMMARY                                                           │
│ This digital identity represents a minimalist and privacy-orientated │
│ presence. The subject maintains a consistent username across multiple │
│ major platforms but utilizes them as contact points rather than for  │
│ public expression. The profile reflects a user who values control   │
│ over their public image.                                             │
╰──────────────────────────────────────────────────────────────────────╯
```

---

## Data Collected Per Platform

| Platform    | Data points                                                     |
|-------------|-----------------------------------------------------------------|
| Reddit      | Karma, account age, top subreddits, post titles, comments       |
| GitHub      | Bio, location, followers, repos, languages, topics, stars       |
| Hacker News | Karma, about, submission titles, comments                       |
| Bluesky     | Display name, bio, followers, posts, activity pattern           |
| Mastodon    | Display name, bio, fields, followers, toots                     |
| Gravatar    | Name, about, location, job, linked accounts                     |
| Telegram    | Display name, bio, member count (public groups)                 |
| YouTube     | Name, subscribers, video count, description                     |
| Twitter/X   | Name, bio, followers, following, tweet count, verified status   |
| Instagram   | Name, bio, followers, post count (web scrape, breaks often)     |
| Threads     | Name, bio (web scrape, breaks often)                            |
| Pixelfed    | Display name, bio, followers, posts (Mastodon API)              |
| PeerTube    | Display name, bio, followers, videos (API)                      |
| Lemmy       | Display name, bio, posts, comments (API)                        |
| Dev.to      | Name, bio, articles, followers, GitHub/Twitter links (API)      |
| Medium      | Name, bio, Twitter handle (JSON endpoint)                       |
| Pinterest   | Name, bio, followers (web scrape, breaks often)                 |
| IntelX      | Leak records, paste contents, darknet references                |
| Ahmia       | `.onion` site titles, URLs, snippets                            |

---

## File Overview

| File | Description |
|------|-------------|
| `osint_profiler.py` | CLI tool — all fetch logic, AI integration, output formatting |
| `osint_profiler_gui.py` | Tkinter GUI — wraps the CLI functions in a visual interface |
| `sources/` | Open_Intel investigation sources (paste, GitHub, GitLab scrapers) |
| `crawler/`, `search/`, `extractor/` | Open_Intel back-end modules |

---

## Requirements

- Python 3.10+
- `requests` (required)
- `rich` (optional, for formatted CLI output)
- `anthropic` / `openai` / `google-genai` / `groq` (optional, for AI profiles)
- `beautifulsoup4` (optional, for Ahmia HTML fallback)
- Tkinter (included with Python, for GUI)
