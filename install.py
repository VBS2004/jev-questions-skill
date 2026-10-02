#!/usr/bin/env python3
"""Install the jev-questions skill into the coding agents you use. Standard library only.

    python3 install.py                      checklist of agents, then global or project
    python3 install.py --list               every known agent and where it reads skills
    python3 install.py --yes                every agent found on this machine, no prompts
    python3 install.py --agents claude,codex,hermes
    python3 install.py --all                every known agent, found or not
    python3 install.py --project            into this project's skill folders instead
    python3 install.py --uninstall

    curl -fsSL https://raw.githubusercontent.com/VBS2004/jev-questions-skill/main/install.py | python3 -

The ecosystem installer does the same job: `npx skills add VBS2004/jev-questions-skill`.
This one needs only Python.

Other options: --copy (copy instead of symlink), --dry-run, --force (replace something
already at the target; the old one is moved aside to `.bak`), --path DIR (also install into
DIR), --update (re-fetch the skill first).

Global installs symlink to one copy of the skill (this checkout, or
~/.local/share/jev-questions-skill when run from a pipe), so updating is one `git pull`.
Project installs are copied, because a symlink to your home directory cannot be committed.
Nothing is overwritten unless it is ours.

Where each agent reads skills comes from the table published by vercel-labs/skills
(https://github.com/vercel-labs/skills#supported-agents), checked 2026-10-02; refresh the
AGENT_TABLE below from there. Tools that share a folder are one row: install once, all read it.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

NAME = "jev-questions"
TARBALL = "https://github.com/VBS2004/jev-questions-skill/archive/refs/heads/main.tar.gz"
MARKER = ".installed-by-jev-questions"

# name | --agent ids | project path | global path   (from vercel-labs/skills, 2026-10-02)
AGENT_TABLE = """\
AiderDesk | aider-desk | .aider-desk/skills/ | ~/.aider-desk/skills/
Amp, Replit, Universal | amp,replit,universal | .agents/skills/ | ~/.config/agents/skills/
Antigravity | antigravity | .agents/skills/ | ~/.gemini/antigravity/skills/
Antigravity CLI | antigravity-cli | .agents/skills/ | ~/.gemini/antigravity-cli/skills/
AstrBot | astrbot | data/skills/ | ~/.astrbot/data/skills/
Autohand Code CLI | autohand-code | .autohand/skills/ | ~/.autohand/skills/
Augment | augment | .augment/skills/ | ~/.augment/skills/
IBM Bob | bob | .bob/skills/ | ~/.bob/skills/
Claude Code | claude-code | .claude/skills/ | ~/.claude/skills/
OpenClaw | openclaw | skills/ | ~/.openclaw/skills/
Cline, Dexto, Kimi Code CLI, Loaf, Pi, Sarvam Code, Warp, Zed | cline,dexto,kimi-code-cli,loaf,pi,sarvam-code,warp,zed | .agents/skills/ | ~/.agents/skills/
CodeArts Agent | codearts-agent | .codeartsdoer/skills/ | ~/.codeartsdoer/skills/
CodeBuddy | codebuddy | .codebuddy/skills/ | ~/.codebuddy/skills/
Codemaker | codemaker | .codemaker/skills/ | ~/.codemaker/skills/
Code Studio | codestudio | .codestudio/skills/ | ~/.codestudio/skills/
Codex | codex | .agents/skills/ | ~/.codex/skills/
Command Code | command-code | .commandcode/skills/ | ~/.commandcode/skills/
Continue | continue | .continue/skills/ | ~/.continue/skills/
Cortex Code | cortex | .cortex/skills/ | ~/.snowflake/cortex/skills/
Crush | crush | .crush/skills/ | ~/.config/crush/skills/
Cursor | cursor | .agents/skills/ | ~/.cursor/skills/
Deep Agents | deepagents | .agents/skills/ | ~/.deepagents/agent/skills/
Devin for Terminal | devin | .devin/skills/ | ~/.config/devin/skills/
Droid | droid | .agents/skills/ | ~/.factory/skills/
Eve | eve | agent/skills/ | -
Firebender | firebender | .agents/skills/ | ~/.firebender/skills/
ForgeCode | forgecode | .forge/skills/ | ~/.forge/skills/
fx | fx | .fx/skills/ | ~/.fx/skills/
Gemini CLI | gemini-cli | .agents/skills/ | ~/.gemini/skills/
GitHub Copilot | github-copilot | .agents/skills/ | ~/.copilot/skills/
Goose | goose | .goose/skills/ | ~/.config/goose/skills/
Grok Build | grok | .grok/skills/ | ~/.grok/skills/
Hermes Agent | hermes-agent | .hermes/skills/ | ~/.hermes/skills/
inference.sh | inference-sh | .inferencesh/skills/ | ~/.inferencesh/skills/
Jazz | jazz | .jazz/skills/ | ~/.jazz/skills/
Junie | junie | .junie/skills/ | ~/.junie/skills/
iFlow CLI | iflow-cli | .iflow/skills/ | ~/.iflow/skills/
Kilo Code | kilo | .agents/skills/ | ~/.kilo/skills/
Kimchi | kimchi | .kimchi/skills/ | ~/.config/kimchi/harness/skills/
Kiro CLI | kiro-cli | .kiro/skills/ | ~/.kiro/skills/
Kode | kode | .kode/skills/ | ~/.kode/skills/
Lingma | lingma | .lingma/skills/ | ~/.lingma/skills/
MCPJam | mcpjam | .mcpjam/skills/ | ~/.mcpjam/skills/
MiniMax Code | minimax-code | .minimax/skills/ | ~/.minimax/skills/
Mistral Vibe | mistral-vibe | .vibe/skills/ | ~/.vibe/skills/
Moxby | moxby | .moxby/skills/ | ~/.moxby/skills/
Mux | mux | .mux/skills/ | ~/.mux/skills/
OpenCode | opencode | .agents/skills/ | ~/.config/opencode/skills/
OpenHands | openhands | .openhands/skills/ | ~/.openhands/skills/
Ona | ona | .ona/skills/ | ~/.ona/skills/
Posit Assistant | posit-assistant | .posit/assistant/skills/ | ~/.posit/assistant/skills/
Qoder | qoder | .qoder/skills/ | ~/.qoder/skills/
Qoder CN | qoder-cn | .qoder/skills/ | ~/.qoder-cn/skills/
Qwen Code | qwen-code | .qwen/skills/ | ~/.qwen/skills/
Reasonix | reasonix | .reasonix/skills/ | ~/.reasonix/skills/
Rovo Dev | rovodev | .rovodev/skills/ | ~/.rovodev/skills/
Roo Code | roo | .roo/skills/ | ~/.roo/skills/
Tabnine CLI | tabnine-cli | .tabnine/agent/skills/ | ~/.tabnine/agent/skills/
Terramind | terramind | .terramind/skills/ | ~/.terramind/skills/
Tinycloud | tinycloud | .tinycloud/skills/ | ~/.tinycloud/skills/
Trae | trae | .trae/skills/ | ~/.trae/skills/
Trae CN | trae-cn | .trae/skills/ | ~/.trae-cn/skills/
Windsurf | windsurf | .windsurf/skills/ | ~/.codeium/windsurf/skills/
ZCode | zcode | .zcode/skills/ | ~/.zcode/skills/
Zencoder, Zenflow | zencoder,zenflow | .zencoder/skills/ | ~/.zencoder/skills/
Neovate | neovate | .neovate/skills/ | ~/.neovate/skills/
Pochi | pochi | .pochi/skills/ | ~/.pochi/skills/
PromptScript | promptscript | .agents/skills/ | -
AdaL | adal | .adal/skills/ | ~/.adal/skills/
"""

# Where a tool's global folder would give a false positive: look for something more specific.
DETECT_OVERRIDE = {
    "gemini-cli": (".gemini/settings.json",),
    "antigravity": (".gemini/antigravity", ".antigravity-ide"),
    "antigravity-cli": (".gemini/antigravity-cli",),
}
# Short names people type.
ALIASES = {"claude": "claude-code", "gemini": "gemini-cli", "copilot": "github-copilot",
           "hermes": "hermes-agent", "agents": "cline", "shared": "cline", "factory": "droid",
           "vibe": "mistral-vibe", "kiro": "kiro-cli", "qwen": "qwen-code"}


@dataclass(frozen=True)
class Agent:
    name: str
    ids: tuple[str, ...]
    project: str  # relative to a project root, e.g. ".claude/skills"
    glob: str | None  # relative to home, e.g. ".claude/skills"; None if project-only
    detect: tuple[str, ...]

    @property
    def id(self) -> str:
        return self.ids[0]

    @property
    def short(self) -> str:
        return self.name if len(self.name) <= 34 else self.name[:33] + "…"


def parse_table(text: str) -> tuple[Agent, ...]:
    out = []
    for line in text.strip().splitlines():
        name, ids, proj, glob = (c.strip() for c in line.split("|"))
        idt = tuple(i for i in ids.split(",") if i)
        g = None if glob == "-" else glob.removeprefix("~/").rstrip("/")
        det = DETECT_OVERRIDE.get(idt[0]) or ((str(Path(g).parent),) if g else ())
        out.append(Agent(name, idt, proj.rstrip("/"), g, det))
    return tuple(out)


AGENTS = parse_table(AGENT_TABLE)
BY_ID = {i: a for a in AGENTS for i in a.ids} | {k: next(a for a in AGENTS if v in a.ids)
                                                 for k, v in ALIASES.items()}


def home() -> Path:
    return Path(os.environ.get("HOME") or os.path.expanduser("~"))


def detected(a: Agent) -> bool:
    return any((home() / d).exists() for d in a.detect)


def skills_dir(a: Agent, project: bool) -> Path | None:
    if project:
        return Path.cwd() / a.project
    return home() / a.glob if a.glob else None


# ---- the store -----------------------------------------------------------------------


def skill_source(store: Path) -> Path:
    return store / "skills" / NAME


def find_store(update: bool = False) -> Path:
    """The repo root: this checkout, or a downloaded copy."""
    here = Path(__file__).resolve().parent if "__file__" in globals() else None
    if here and skill_source(here).exists():
        if update and (here / ".git").exists():
            os.system(f"git -C '{here}' pull --ff-only")
        return here
    store = Path(os.environ.get("XDG_DATA_HOME") or home() / ".local" / "share") / "jev-questions-skill"
    if skill_source(store).exists() and not update:
        return store
    print(f"downloading {TARBALL}")
    with urllib.request.urlopen(TARBALL, timeout=60) as resp:
        data = resp.read()
    tmp = store.with_name(store.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        top = tar.getmembers()[0].name.split("/")[0]
        for m in tar.getmembers():
            if m.name.split("/", 1)[0] != top or ".." in m.name:
                continue
            m.name = m.name.split("/", 1)[1] if "/" in m.name else ""
            if m.name and (m.isfile() or m.isdir()):  # never links or devices from a tarball
                tar.extract(m, tmp)
    shutil.rmtree(store, ignore_errors=True)
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp.rename(store)
    return store


# ---- install / uninstall -------------------------------------------------------------


def is_ours(path: Path, store: Path) -> bool:
    if path.is_symlink():
        try:
            return path.resolve() == skill_source(store).resolve()
        except OSError:
            return False
    return (path / MARKER).exists()


def install_dir(parent: Path, store: Path, copy: bool, force: bool, dry: bool) -> str:
    dest = parent / NAME
    if dest.exists() or dest.is_symlink():
        if is_ours(dest, store):
            return "already installed"
        if not force:
            return f"skipped: something else is at {dest} (use --force to move it aside)"
        if dry:
            return f"would move {dest} aside and install"
        bak = dest.with_name(dest.name + ".bak")
        if bak.is_symlink() or bak.is_file():
            bak.unlink()
        elif bak.is_dir():
            shutil.rmtree(bak)
        dest.rename(bak)
    if dry:
        return f"would {'copy to' if copy else 'link'} {dest}"
    parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copytree(skill_source(store), dest, ignore=shutil.ignore_patterns("__pycache__"))
        (dest / MARKER).write_text("installed by jev-questions install.py\n")
        return f"copied to {dest}"
    dest.symlink_to(skill_source(store), target_is_directory=True)
    return f"linked {dest} -> {skill_source(store)}"


def uninstall_dir(parent: Path, store: Path, dry: bool) -> str:
    dest = parent / NAME
    if not (dest.exists() or dest.is_symlink()):
        return "not installed"
    if not is_ours(dest, store):
        return f"left alone: {dest} was not installed by this script"
    if dry:
        return f"would remove {dest}"
    if dest.is_symlink():
        dest.unlink()
    else:
        shutil.rmtree(dest)
    return f"removed {dest}"


# ---- choosing ------------------------------------------------------------------------


def ordered() -> list[Agent]:
    """Agents found on this machine first, then the rest in the published order."""
    return sorted(AGENTS, key=lambda a: not detected(a))


def status(a: Agent, store: Path, project: bool = False) -> str:
    d = skills_dir(a, project)
    if d is None:
        return ""
    t = d / NAME
    if t.exists() or t.is_symlink():
        return "installed" if is_ours(t, store) else "occupied"
    return ""


def show(store: Path) -> None:
    print(f"{'#':>2}  {'found':5} {'agent':35} {'global folder':38} project folder")
    for i, a in enumerate(ordered(), 1):
        g = f"~/{a.glob}" if a.glob else "(project only)"
        s = status(a, store)
        print(f"{i:2}  {'yes' if detected(a) else '-':5} {a.short:35} {g:38} {a.project}"
              f"{'   <- ' + s if s else ''}")


def choose(store: Path, verb: str, tty=None) -> list[Agent]:
    """A numbered checklist. Agents found on this machine start ticked. `tty` is where
    answers are read from: /dev/tty when the script itself arrives on stdin (curl | python3)."""
    if tty is None:
        try:
            tty = open("/dev/tty") if not sys.stdin.isatty() else sys.stdin
        except OSError:
            raise SystemExit("no terminal to ask on: pass --agents a,b, --yes or --all "
                             "(see --list for the ids)")
    rows = ordered()
    ticked = {a.id for a in rows if detected(a)} if verb == "install" else {
        a.id for a in rows if status(a, store) == "installed"}
    while True:
        print(f"\n{verb.capitalize()} jev-questions for which agents?  ({len(rows)} known)\n")
        for i, a in enumerate(rows, 1):
            box = "[x]" if a.id in ticked else "[ ]"
            g = f"~/{a.glob}" if a.glob else "(project only)"
            s = status(a, store)
            print(f" {i:2}. {box} {a.short:35} {g:38}{' found' if detected(a) else ''}"
                  f"{'  <- ' + s if s else ''}")
        print("\n numbers to toggle (1 3 5-7) | a all | d found | n none | "
              "Enter to continue | q quit")
        print("> ", end="", flush=True)
        line = tty.readline()
        if not line:
            raise SystemExit("\ncancelled")
        line = line.strip().lower()
        if line in ("q", "quit"):
            raise SystemExit("cancelled")
        if line == "":
            return [a for a in rows if a.id in ticked]
        if line == "a":
            ticked = {a.id for a in rows}
        elif line == "n":
            ticked = set()
        elif line == "d":
            ticked = {a.id for a in rows if detected(a)}
        else:
            for tok in line.replace(",", " ").split():
                lo, _, hi = tok.partition("-")
                try:
                    nums = range(int(lo), int(hi or lo) + 1)
                except ValueError:
                    print(f"  ? {tok}")
                    continue
                for n in nums:
                    if 1 <= n <= len(rows):
                        ticked ^= {rows[n - 1].id}


def ask_scope(tty=None) -> bool:
    """True for project scope."""
    if tty is None:
        try:
            tty = open("/dev/tty") if not sys.stdin.isatty() else sys.stdin
        except OSError:
            return False
    print("\nInstall for [g]lobal use (all your projects) or this [p]roject only? [g] ", end="",
          flush=True)
    return tty.readline().strip().lower().startswith("p")


def main(argv: list[str] | None = None, tty=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show known agents and exit")
    ap.add_argument("--agents", help="comma-separated ids, e.g. claude,codex,hermes")
    ap.add_argument("--all", action="store_true", help="every known agent, found or not")
    ap.add_argument("--yes", "-y", action="store_true", help="every agent found, no prompt")
    ap.add_argument("--project", action="store_true", help="this project's folders, not global")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--copy", action="store_true", help="copy instead of symlink")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--update", action="store_true", help="re-fetch the skill first")
    ap.add_argument("--path", action="append", default=[], help="also install into DIR")
    a = ap.parse_args(argv)

    store = find_store(a.update)
    if a.list:
        show(store)
        return 0

    verb = "uninstall" if a.uninstall else "install"
    interactive = not (a.agents or a.all or a.yes or a.path)
    if a.agents:
        ids = [x.strip() for x in a.agents.split(",") if x.strip()]
        bad = [i for i in ids if i not in BY_ID]
        if bad:
            raise SystemExit(f"unknown agent(s): {', '.join(bad)}; try --list")
        picked = [BY_ID[i] for i in ids]
    elif a.all:
        picked = list(AGENTS)
    elif a.yes:
        picked = [x for x in AGENTS if detected(x)]
        if not picked:
            print("no known agent found on this machine; see --list, or use --agents / --all")
    elif a.path:
        picked = []
    else:
        picked = choose(store, verb, tty)

    project = a.project or (interactive and bool(picked) and not a.uninstall
                            and ask_scope(tty))
    # one target per folder: tools that share one are installed (and reported) once
    targets: dict[Path, list[str]] = {}
    for ag in picked:
        d = skills_dir(ag, project)
        if d is None:
            print(f"  {ag.short:35} has no global folder; use --project")
            continue
        targets.setdefault(d, []).append(ag.short)
    for p in a.path:
        targets.setdefault(Path(p).expanduser().resolve(), []).append("--path")
    if not targets:
        print("nothing selected")
        return 0

    copy = a.copy or project  # a symlink into your home cannot be committed with a project
    print(f"\n{'dry run: ' if a.dry_run else ''}{verb} ({'project' if project else 'global'}) "
          f"from {store}\n")
    for d, names in targets.items():
        res = (uninstall_dir(d, store, a.dry_run) if a.uninstall
               else install_dir(d, store, copy, a.force, a.dry_run))
        label = names[0] if len(names) == 1 else f"{names[0]} +{len(names) - 1}"
        print(f"  {label:35} {res}")
    if not a.uninstall and not a.dry_run:
        print("\nRestart the agent (or start a new session) so it picks the skill up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
