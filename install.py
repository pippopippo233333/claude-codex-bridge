#!/usr/bin/env python3
"""Agent Bridge installer: connects Claude Code and Codex so they can message each other.

  python install.py              install or update (for every app found)
  python install.py --check      show what is installed; changes nothing
  python install.py --dry-run    show what install would change; changes nothing
  python install.py --uninstall  remove it from both apps (keeps the chat history)
  python install.py --uninstall --purge   also delete ~/.agent-bridge with all its data
  python install.py --only claude|codex   limit install/uninstall to one app

Every config file it changes is backed up first (<file>.bak-agent-bridge). It only touches its own
entries: other MCP servers, hooks and instructions stay as they are. Python 3.9+, standard library only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
REPO = Path(__file__).resolve().parent
INSTALL_DIR = HOME / ".agent-bridge"
BRIDGE = INSTALL_DIR / "bridge.py"
FILES = ["bridge.py", "gemini_helper.py", "viewer.py"]
PY = sys.executable

CLAUDE_DIR = HOME / ".claude"
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"
CLAUDE_STATE = HOME / ".claude.json"           # user-scope MCP servers
CLAUDE_MD = CLAUDE_DIR / "CLAUDE.md"
CODEX_DIR = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
CODEX_CONFIG = CODEX_DIR / "config.toml"
CODEX_HOOKS = CODEX_DIR / "hooks.json"
CODEX_MD = CODEX_DIR / "AGENTS.md"

START, END = "<!-- agent-bridge:start -->", "<!-- agent-bridge:end -->"
CLAUDE_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact",
                 "PostCompact", "StopFailure", "Stop"]
CODEX_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact",
                "PostCompact", "Stop"]
STOP_TIMEOUT = 600    # stay-awake waits inside the Stop hook
HOOK_TIMEOUT = 10

DRY = False
changes = []


def say(msg):
    print(msg)


def note(msg):
    changes.append(msg)
    say(("  would " if DRY else "  ") + msg)


# ---------------------------------------------------------------- helpers

def backup(path):
    if path.exists() and not DRY:
        shutil.copy2(path, path.with_name(path.name + ".bak-agent-bridge"))


def write_text(path, text):
    if DRY:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    tmp = path.with_name(path.name + ".tmp-agent-bridge")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"Can't read {path} (invalid JSON: {e}). Fix or move that file, then run again. Nothing changed.")


def is_ours(hook):
    """A hook entry that runs ~/.agent-bridge/bridge.py (from this installer or a manual setup)."""
    joined = " ".join([str(hook.get("command", ""))] + [str(a) for a in hook.get("args") or []])
    return ".agent-bridge" in joined and "bridge.py" in joined


def strip_our_hooks(hooks_by_event):
    """Remove the bridge's hook entries, keep everything else."""
    removed = 0
    for event in list(hooks_by_event):
        groups = []
        for group in hooks_by_event[event]:
            inner = [h for h in group.get("hooks", []) if not is_ours(h)]
            removed += len(group.get("hooks", [])) - len(inner)
            if inner:
                groups.append({**group, "hooks": inner})
        if groups:
            hooks_by_event[event] = groups
        else:
            del hooks_by_event[event]
    return removed


def find_app(name, folder):
    return folder.exists() or shutil.which(name) is not None


def instructions(name):
    return (REPO / "instructions" / name).read_text(encoding="utf-8").strip()


def set_block(path, body):
    """Put the instructions between markers in a global instructions file (replacing an older block)."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    block = f"{START}\n{body}\n{END}"
    if START in text and END in text:
        new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
        if new == text:
            return False
    else:
        if body.splitlines()[0] in text:
            say(f"  note: {path} already has an Agent Bridge section without markers; left it as it is.")
            return False
        new = text.rstrip() + ("\n\n" if text.strip() else "") + block + "\n"
    write_text(path, new)
    return True


def remove_block(path):
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if START not in text:
        return False
    new = re.sub(r"\n*" + re.escape(START) + r".*?" + re.escape(END) + r"\n?", "\n", text, flags=re.S)
    write_text(path, new.strip() + "\n" if new.strip() else "")
    return True


def toml_str(s):
    return json.dumps(str(s))  # a JSON string is a valid TOML basic string


def strip_toml_table(text, table):
    """Remove [table] and its keys (up to the next table header)."""
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        header = re.match(r"\s*\[\[?([^\]]+)\]\]?\s*(#.*)?$", line)
        if header:
            skipping = header.group(1).strip() == table
        if not skipping:
            out.append(line)
    return "".join(out)


# ---------------------------------------------------------------- Claude Code

def claude_hook():
    return {"type": "command", "command": PY, "args": [str(BRIDGE), "hook", "--as", "claude"]}


def install_claude():
    say("Claude Code:")
    # MCP server (user scope = every folder)
    server = {"type": "stdio", "command": PY, "args": [str(BRIDGE), "mcp", "--as", "claude"], "env": {}}
    cli = shutil.which("claude")
    done = False
    if cli and not DRY:
        subprocess.run([cli, "mcp", "remove", "agent-bridge", "--scope", "user"], capture_output=True, text=True)
        r = subprocess.run([cli, "mcp", "add-json", "agent-bridge", json.dumps(server), "--scope", "user"],
                           capture_output=True, text=True)
        done = r.returncode == 0
    if not done:
        state = read_json(CLAUDE_STATE)
        if state.get("mcpServers", {}).get("agent-bridge") != server:
            state.setdefault("mcpServers", {})["agent-bridge"] = server
            write_text(CLAUDE_STATE, json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    note("register the agent-bridge MCP server (all folders)")
    # Hooks
    settings = read_json(CLAUDE_SETTINGS)
    hooks = settings.setdefault("hooks", {})
    strip_our_hooks(hooks)
    for event in CLAUDE_EVENTS:
        group = {"hooks": [{**claude_hook(), "timeout": STOP_TIMEOUT if event == "Stop" else HOOK_TIMEOUT}]}
        if event == "SessionStart":
            group = {"matcher": "compact", **group}
        hooks.setdefault(event, []).append(group)
    write_text(CLAUDE_SETTINGS, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    note(f"add {len(CLAUDE_EVENTS)} hooks to {CLAUDE_SETTINGS}")
    if set_block(CLAUDE_MD, instructions("for-claude.txt")):
        note(f"add teammate instructions to {CLAUDE_MD}")


def uninstall_claude():
    say("Claude Code:")
    cli = shutil.which("claude")
    if cli and not DRY:
        subprocess.run([cli, "mcp", "remove", "agent-bridge", "--scope", "user"], capture_output=True, text=True)
    state = read_json(CLAUDE_STATE)
    if "agent-bridge" in state.get("mcpServers", {}):
        del state["mcpServers"]["agent-bridge"]
        write_text(CLAUDE_STATE, json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    note("remove the agent-bridge MCP server")
    settings = read_json(CLAUDE_SETTINGS)
    if strip_our_hooks(settings.get("hooks", {})):
        if not settings.get("hooks"):
            settings.pop("hooks", None)
        write_text(CLAUDE_SETTINGS, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
        note("remove the bridge hooks")
    if remove_block(CLAUDE_MD):
        note("remove the teammate instructions")


def check_claude():
    state = read_json(CLAUDE_STATE)
    settings = read_json(CLAUDE_SETTINGS)
    n = sum(1 for groups in settings.get("hooks", {}).values() for g in groups for h in g.get("hooks", [])
            if is_ours(h))
    text = CLAUDE_MD.read_text(encoding="utf-8") if CLAUDE_MD.exists() else ""
    say(f"Claude Code: MCP server {'yes' if 'agent-bridge' in state.get('mcpServers', {}) else 'no'}, "
        f"hooks {n}/{len(CLAUDE_EVENTS)}, instructions {'yes' if 'Codex teammate (Agent Bridge)' in text else 'no'}")


# ---------------------------------------------------------------- Codex

def codex_command():
    return f"{shell_quote(PY)} {shell_quote(BRIDGE)} hook --as codex"


def shell_quote(p):
    p = str(p)
    return f'"{p}"' if " " in p else p


def install_codex():
    say("Codex:")
    text = CODEX_CONFIG.read_text(encoding="utf-8") if CODEX_CONFIG.exists() else ""
    new = strip_toml_table(text, "mcp_servers.agent_bridge").rstrip()
    new += ("\n\n" if new else "") + (
        "[mcp_servers.agent_bridge]\n"
        f"command = {toml_str(PY)}\n"
        f"args = [{toml_str(BRIDGE)}, \"mcp\", \"--as\", \"codex\"]\n"
        "tool_timeout_sec = 600\n")
    if new != text:
        write_text(CODEX_CONFIG, new)
    note(f"register the agent_bridge MCP server in {CODEX_CONFIG}")
    data = read_json(CODEX_HOOKS)
    hooks = data.setdefault("hooks", {})
    strip_our_hooks(hooks)
    for event in CODEX_EVENTS:
        hooks.setdefault(event, []).append({"hooks": [{
            "type": "command", "command": codex_command(),
            "timeout": STOP_TIMEOUT if event == "Stop" else HOOK_TIMEOUT}]})
    write_text(CODEX_HOOKS, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    note(f"add {len(CODEX_EVENTS)} hooks to {CODEX_HOOKS}")
    if set_block(CODEX_MD, instructions("for-codex.txt")):
        note(f"add teammate instructions to {CODEX_MD}")


def uninstall_codex():
    say("Codex:")
    if CODEX_CONFIG.exists():
        text = CODEX_CONFIG.read_text(encoding="utf-8")
        new = strip_toml_table(text, "mcp_servers.agent_bridge")
        if new != text:
            write_text(CODEX_CONFIG, new)
            note("remove the agent_bridge MCP server")
    data = read_json(CODEX_HOOKS)
    if strip_our_hooks(data.get("hooks", {})):
        write_text(CODEX_HOOKS, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        note("remove the bridge hooks")
    if remove_block(CODEX_MD):
        note("remove the teammate instructions")


def check_codex():
    text = CODEX_CONFIG.read_text(encoding="utf-8") if CODEX_CONFIG.exists() else ""
    data = read_json(CODEX_HOOKS)
    n = sum(1 for groups in data.get("hooks", {}).values() for g in groups for h in g.get("hooks", [])
            if is_ours(h))
    md = CODEX_MD.read_text(encoding="utf-8") if CODEX_MD.exists() else ""
    say(f"Codex: MCP server {'yes' if '[mcp_servers.agent_bridge]' in text else 'no'}, "
        f"hooks {n}/{len(CODEX_EVENTS)}, instructions {'yes' if 'Claude Code teammate (Agent Bridge)' in md else 'no'}")


# ---------------------------------------------------------------- main

def gemini_key_set():
    if os.environ.get("GEMINI_API_KEY"):
        return True
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return bool(winreg.QueryValueEx(k, "GEMINI_API_KEY")[0])
        except OSError:
            return False
    return False


def next_steps(apps):
    bridge = f'python "{BRIDGE}"'
    key_cmd = ('setx GEMINI_API_KEY "your-key"' if os.name == "nt"
               else 'echo \'export GEMINI_API_KEY="your-key"\' >> ~/.zshrc   (or ~/.bashrc)')
    say("\nWHAT YOU NEED TO DO")
    say("  1. Fully quit and reopen " + " and ".join(apps) + " (so they load the bridge).")
    if "Codex" in apps:
        say("  2. In Codex, approve the new hooks if it asks you to trust them (needed for automatic delivery).")
    if "Codex" not in apps or "Claude Code" not in apps:
        say("  !  Only one app was found. The bridge needs both Claude Code and Codex installed.")
    say("\nOPTIONAL (each one is off until you turn it on)")
    say("  - Gemini helper: cheap summaries/search with a FREE Google key (https://aistudio.google.com/apikey).")
    say(f"    Set the key yourself (never paste it into a chat):  {key_cmd}")
    say(f"    Then allow it per project (free tier data may be used by Google):  {bridge} gemini on \"<project folder>\"")
    say(f"  - Stay-awake: an AI that finishes while the other is still working waits and continues by itself:")
    say(f"    {bridge} stayawake on \"<project folder>\"")
    say("\nHOW TO USE: in either app, just say e.g. \"ask Codex to review this\" or \"tell Claude to run the tests\".")
    say(f"To watch them talk live:  python \"{INSTALL_DIR / 'viewer.py'}\"")
    if gemini_key_set():
        say("(A GEMINI_API_KEY is already set on this computer.)")


def main():
    global DRY
    ap = argparse.ArgumentParser(description="Install Agent Bridge for Claude Code and Codex.")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--purge", action="store_true")
    ap.add_argument("--only", choices=["claude", "codex"])
    a = ap.parse_args()
    DRY = a.dry_run
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 or newer is needed.")

    want_claude = a.only in (None, "claude")
    want_codex = a.only in (None, "codex")
    has_claude = find_app("claude", CLAUDE_DIR)
    has_codex = find_app("codex", CODEX_DIR)

    if a.check:
        say(f"Bridge files: {'installed in ' + str(INSTALL_DIR) if BRIDGE.exists() else 'not installed'}")
        check_claude() if has_claude else say("Claude Code: not found")
        check_codex() if has_codex else say("Codex: not found")
        if BRIDGE.exists():
            subprocess.run([PY, str(BRIDGE), "projects"])
        say(f"Gemini key: {'set' if gemini_key_set() else 'not set'}")
        return

    if a.uninstall:
        if want_claude and has_claude:
            uninstall_claude()
        if want_codex and has_codex:
            uninstall_codex()
        if a.purge and INSTALL_DIR.exists():
            note(f"delete {INSTALL_DIR} (chat history, settings)")
            if not DRY:
                shutil.rmtree(INSTALL_DIR)
        say("\nDone. Restart both apps." if not DRY else "\nDry run: nothing was changed.")
        return

    if not (has_claude or has_codex):
        sys.exit("Neither Claude Code (~/.claude) nor Codex (~/.codex) was found. Install at least one, run it once, "
                 "then run this again.")
    say(f"Installing Agent Bridge with Python {sys.version.split()[0]} ({PY})")
    say("Bridge files:")
    for name in FILES:
        if not DRY:
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "bridge" / name, INSTALL_DIR / name)
    note(f"copy the bridge to {INSTALL_DIR}")
    apps = []
    if want_claude and has_claude:
        install_claude()
        apps.append("Claude Code")
    if want_codex and has_codex:
        install_codex()
        apps.append("Codex")
    if DRY:
        say("\nDry run: nothing was changed.")
        return
    say("\nInstalled. Backups of changed files end in .bak-agent-bridge.")
    next_steps(apps)


if __name__ == "__main__":
    main()
