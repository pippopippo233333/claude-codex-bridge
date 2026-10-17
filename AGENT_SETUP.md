# Setting up Agent Bridge (instructions for an AI agent)

You are Claude Code or Codex, and your user asked you to install Agent Bridge from this repository. Do every
step you can yourself. Ask the user only for the things listed under "Only the user can do this", and keep
your explanation short and plain: the user may not be technical.

## 1. Get the code
- If the repository isn't on disk yet, clone it into a normal folder (not a system folder):
  `git clone https://github.com/pippopippo233333/claude-codex-desktop-bridge`. If git isn't available, download the ZIP from the
  repository page and unzip it.
- Read `README.md` and `install.py` before running anything, so you can explain what will change.

## 2. Check Python
- Run `python --version` (or `python3 --version`). Python 3.9 or newer is needed.
- If it's missing or too old, stop and ask the user to install it from https://www.python.org/downloads/
  (on Windows, with "Add python.exe to PATH" ticked). Then continue.

## 3. Install
1. `python install.py --dry-run`: shows exactly what will change. Nothing is written.
2. `python install.py`: installs. It backs up every file it changes and only adds its own entries.
3. `python install.py --check`: confirm. You should see the MCP server, all hooks and the instructions for
   each app that's installed (Claude Code: 8 hooks, Codex: 7 hooks).

If the installer stops on an error (for example an invalid JSON config file), explain it to the user in one or
two sentences and fix it only with their OK. Never delete their config files.

If only one of the two apps is installed, say that the bridge needs both, and that they can run
`python install.py` again after installing the other one.

## 4. Tell the user what's left (only these)
**Only the user can do this:**
1. **Fully quit and reopen** both Claude Code and Codex. The new tools and hooks load at startup, and
   your own conversation won't have them until then.
2. **In Codex:** approve the new hooks when Codex asks to trust them. Without this, messages only arrive
   when an AI explicitly checks.

**Optional, and only if they want it** (both are off by default):
- **Gemini helper:** cheap text work and summaries with a *free* Google key.
  - Getting a key: <https://aistudio.google.com/apikey>.
  - **Ask the user to set the key themselves.** Never ask them to paste it into the chat, and never read or
    print it. On Windows: `setx GEMINI_API_KEY "their-key"`. On macOS/Linux: an
    `export GEMINI_API_KEY="their-key"` line in `~/.zshrc` or `~/.bashrc`.
  - Turning it on for a project is a privacy choice (Google may use free-tier data). Only after the user says
    yes, run `python ~/.agent-bridge/bridge.py gemini on "<project folder>"`.
- **Stay-awake:** an AI that finishes its turn keeps waiting (up to 2 hours) and continues by itself when the
  other's message arrives; the user's own messages still get through within about 2 minutes. Only after the user says yes, run `python ~/.agent-bridge/bridge.py stayawake on "<project folder>"`.

## 5. Explain how to use it (2–3 sentences)
Something like: "From now on you can say things like *ask Codex to review this* or *tell Claude to run the
tests* in either app. Their messages to each other are labelled, so they never confuse them with yours, and
anything you haven't approved comes back to you. `python install.py --uninstall` removes it."

## Rules while setting up
- Don't turn on the Gemini helper or stay-awake without the user's explicit yes.
- Don't ask for, read, print or store API keys.
- Don't send test messages through the bridge unless the user asks for a test.
- If something fails, report the exact error and the fix; don't retry blindly.
