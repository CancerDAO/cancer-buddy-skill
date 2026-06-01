# Installation

## Requirements

Requirements depend on which sub-skills you use:

- **Core companion modes** (organize, caregiver, mind, disclosure, vault, education, nutrition, second-opinion) — only **Claude Code** (latest). Get it from https://claude.ai/code. OCR, vision, and reasoning run on Claude's native model capabilities; no tesseract or pdftotext needed.
- **`cancer-buddy-find-care`** — additionally needs **Node.js 22+** and a **Chrome instance launched with remote debugging** (used via the bundled `web-access` skill; see [Web-access prerequisites](#web-access-prerequisites)).
- **Profile schema validator** (`scripts/validate-profile-schema.sh`, optional) — needs **python3** on `PATH`. This is a convenience checker for `profile.json` / `readiness.json`; the companion modes do not require it to run.

There is no single "zero-config, no Python" path: core modes are Claude-Code-only, but find-care pulls in Node/Chrome and the optional validator pulls in python3.

## Install via `skills` CLI

Cancer-buddy follows the [vercel-labs/skills](https://github.com/vercel-labs/skills) paradigm — each sub-skill is an independently installable directory under `skills/`. Claude Code is the supported, tested target (see [Platform support](#platform-support)); other agents get a best-effort copy.

```bash
# Global (all projects)
npx skills add CancerDAO/cancer-buddy-skill -g

# Project-scoped
npx skills add CancerDAO/cancer-buddy-skill

# Install only specific sub-skills
npx skills add CancerDAO/cancer-buddy-skill --skill cancer-buddy cancer-buddy-organize cancer-buddy-find-care
```

> **Note**: `cancer-buddy-find-care` requires the bundled `web-access` skill (also under `skills/`) to perform the parallel multi-subagent web research that powers hospital/doctor/trial discovery. Both are auto-installed when you use `--all` or `add CancerDAO/cancer-buddy-skill` without `--skill`. If you cherry-pick `cancer-buddy-find-care`, also include `web-access`.

### Web-access prerequisites

`cancer-buddy-find-care` (via `web-access`) uses the user's local Chrome with remote debugging for sites that block static scraping (好大夫在线, 微信公众号, ChiCTR, etc.). One-time setup:

1. **Node.js 22+** (for native WebSocket; lower versions need the `ws` module).
2. **Launch Chrome with an open CDP endpoint.** Ticking the box in `chrome://inspect` alone does **not** open a DevTools (CDP) endpoint — `web-access` connects to a real `--remote-debugging-port`. Quit Chrome fully first, then start it with the debug port:

   ```bash
   # macOS
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

   # Windows (PowerShell or cmd)
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

   # Linux
   google-chrome --remote-debugging-port=9222
   ```

   Verify it's live: `curl http://127.0.0.1:9222/json/version` should return JSON.

The bundled `cdp-proxy` auto-discovers Chrome on ports `9222 / 9229 / 9333` and itself listens on `CDP_PROXY_PORT` (default **3456**). If your Chrome uses a different debug port, the proxy still finds it via Chrome's `DevToolsActivePort` file; to override the proxy's own port, set `CDP_PROXY_PORT`.

Without a debug-enabled Chrome, `find-care` falls back to pure WebSearch/WebFetch — works for some queries, less reliable for ranking-heavy ones.

### Platform support

**Claude Code is the supported and tested target.** The repo ships `.claude-plugin` manifests for Claude Code and the CC marketplace, and that is the path we exercise. On Claude Code the CLI auto-detects the agent and installs to `~/.claude/skills/` (global) or `.claude/skills/` (project) — restart Claude Code after install.

Other agents (Codex, OpenCode, Cursor, etc.) get a **best-effort directory copy** via `npx skills add` — the sub-skill directories are agent-agnostic Markdown, but we have **not yet verified** end-to-end behavior on those agents. Treat non-Claude-Code use as experimental; no parity is claimed.

### Update / remove at the bundle level

`add CancerDAO/cancer-buddy-skill` installs a **bundle** — the meta `cancer-buddy` entry plus its 9 companions and the `web-access` dependency, each as its own directory under `skills/`. Updating or removing only the `cancer-buddy` meta-skill leaves the 9 companions and `web-access` behind (orphaned). Operate on the whole bundle instead:

**Update the whole bundle:**
```bash
npx skills update CancerDAO/cancer-buddy-skill
```

**Remove the whole bundle (meta + 9 companions + web-access):**
```bash
npx skills remove CancerDAO/cancer-buddy-skill
```

If you only ever want to touch one sub-skill, name it explicitly — e.g. `npx skills update cancer-buddy-find-care`. But do **not** run `npx skills remove cancer-buddy` expecting it to clean up the bundle: that removes only the meta router and silently orphans the companions.

## Companion skills

Cancer-buddy is companion-scope — it deliberately does NOT do clinical decision-making. Two companion skills cover the clinical/decision tier:

### clinical-trial-matching — opt-in, fetched on demand

Repo: [CancerDAO/clinical-trial-matching-skill](https://github.com/CancerDAO/clinical-trial-matching-skill) (CancerDAO open source). Does criterion-level CoT gating, R1–R5 hard rules, vs-SoC efficacy, decision synthesizer — built on NCBI TrialGPT.

**You don't install it upfront, and the fetch is opt-in.** When `cancer-buddy-find-care` produces a shortlist that contains NCT / ChiCTR trials and the user wants criterion-by-criterion matching, find-care:
1. Checks whether `clinical-trial-matching` is already in `~/.claude/skills/` (or `.claude/skills/`).
2. If missing, **asks for your confirmation before running** `npx skills add CancerDAO/clinical-trial-matching-skill -g --all` (≈3 s).
3. Routes the call only after you approve.

> **Security note:** the on-demand fetch installs code from a remote repo into your **global** skills directory (`-g`). Because this runs third-party code, find-care prompts you first and never installs it silently. Decline the prompt and find-care stays in shortlist-only mode; or pre-install yourself (below) so no on-demand fetch is ever attempted.

If you'd rather pre-install (offline machine, slow network, or to avoid the prompt entirely):

```bash
npx skills add CancerDAO/clinical-trial-matching-skill -g --all
```

### vmtb-skill — full virtual MTB analysis (open-sourcing soon)

`cancer-buddy-find-care` helps you **find hospitals/doctors that do MTB** — it doesn't run the MTB analysis itself. For the deep committee analysis (pathologist + geneticist + recruiter + oncologist + chair + 5-dimension verifier, 15–20 min), the dedicated tool is `vmtb-skill`. **It's not open-sourced yet — public release is in preparation, follow [@CancerDAO](https://github.com/CancerDAO) for the announcement.**

In the meantime, cancer-buddy auto-detects whether `vmtb-skill` is already installed locally:

- **Installed (internal team members)** → router invokes it directly; no extra steps needed.
- **Not installed (public users)** → router replies with the "open-sourcing soon" message and offers `find-care` (find an MTB-capable venue), `organize` (prep records for an in-person MTB), or `second-opinion` (cross-border packet).

Internal team members get the install path through CancerDAO's internal onboarding — not documented here.

### Routing summary

- **Where can my MTB happen?** → `cancer-buddy-find-care` (this repo)
- **Find trial centers / hospitals near me** → `cancer-buddy-find-care` (this repo)
- **Match me to a specific trial criterion-by-criterion** → `clinical-trial-matching` (auto-fetched by find-care)
- **Run a virtual MTB on my case** → `vmtb-skill` if installed (internal); otherwise "open-sourcing soon" + the alternatives above
- **Real clinical MTB decisions** → your treating oncologist + the venue you found above

## Verify

In Claude Code, type:
```
抗癌搭子
```

The meta-skill should respond. If nothing happens:

1. Check the SKILL.md was installed: `ls ~/.claude/skills/cancer-buddy/SKILL.md`
2. Claude Code version — older versions may not auto-discover skills.
3. Try the `skills list` command: `npx skills list` — confirms what's installed.

## Data location

`patients/<patient_code>/` is where all records and reports live. `patient_code` is auto-generated by the organizer on first run (e.g. `PT-17CE02BC33`). Root directory resolves in this order:

1. `$CANCER_BUDDY_PATIENTS_DIR` (if set)
2. `$VMTB_PATIENT_DATA_ROOT` (shared with vmtb-skill)
3. `$HOME/CancerDAO/patients` (default)

Your `patients/` directory is untouched by uninstall — back it up or move it first if you care about it.
