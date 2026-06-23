---
type: Standard
title: Prismatic Web Plugin — Process Documentation (the durable system)
description: The complete process doc for the PWP. How a client's 5 Website Dev Framework docs become a deployed website via the agent swarm. The full pipeline + every step + every script + every Linear workflow. This is the canonical reference for the PWP system.
resource: https://github.com/mbgulden/prismatic-web-plugin
tags: [process, pwp, prismatic-web-plugin, pipeline, ingest, synthesize, distill, build, deploy, agent-swarm, documentation, system]
timestamp: 2026-06-23T16:30:00Z
git_repo: mbgulden/prismatic-web-plugin
git_path: docs/PROCESS.md
last_verified: 2026-06-23
verified_by: fred
status: current
---

# Prismatic Web Plugin — Process Documentation

> **The durable, generalized PWP that turns any client's Website Content Gathering Framework into a deployed website via the Prismatic Engine agent swarm.**
> Repo: https://github.com/mbgulden/prismatic-web-plugin
> CLI: `pwb` (Prismatic Web Builder)

## TL;DR

```
Client's 5 Website Dev docs (Drive / OKF)
                ↓
       ┌────────┴────────┐
       │ pwb run         │
       │ (the builder)   │
       └────────┬────────┘
                ↓
       Step 1: INGEST   → client_profile.json + content_brief.json
                ↓
       Step 2: SYNTHESIZE → website_build_plan.md (3,000+ words, AGY pro)
                ↓
       Step 3: DISTILL   → Linear epic + 10-20 child issues
                ↓
       AGENT SWARM      → AGY/Kai/Ned execute the work
                ↓
       REVIEW + MERGE   → AGY pro reviews, Fred verifies
                ↓
       DEPLOY           → Cloudflare Pages
                ↓
       OKF HANDOFF      → doc + URL + summary for the next client
```

## What's in the package

| File | Purpose |
|---|---|
| `src/prismatic_web_plugin/ingest.py` | Step 1: parse 5 docs → JSON profile |
| `src/prismatic_web_plugin/synthesize.py` | Step 2: profile → build plan via AGY pro |
| `src/prismatic_web_plugin/distill.py` | Step 3: build plan → Linear epic + children |
| `src/prismatic_web_plugin/builder.py` | The `pwb` CLI (run / watch / status) |
| `tests/test_smoke.py` | Smoke tests for all 3 library functions |
| `PRISMATIC_ENGINE.yaml` | Lane governance for the repo |
| `scripts/prismatic-pre-push-hook.py` | The lane enforcement hook |
| `pyproject.toml` | Python package metadata |

## The pipeline (3 steps, ~90 seconds end-to-end)

### Step 1: INGEST (`pwb run --client <slug>`)

**Input:** A directory containing the 5 Website Dev Framework docs:
- `content_gathering_guide` (or "Doc 1 - Content Gathering Guide")
- `partner_interview` (or "Doc 2 - Partner Interview")
- `brand_design_interview` (or "Doc 3 - Brand & Design Interview")
- `conversion_launch_kit` (or "Doc 4 - Conversion & Launch Kit")
- `post_purchase_automation` (or "Doc 5 - Post-Purchase Automation")

**Output:** `<client-slug>/client_profile.json` + `content_brief.json` + `ingest_report.md`

**Library API:**
```python
from prismatic_web_plugin.ingest import run_ingest
result = run_ingest(docs_dir, output_dir=None, dry_run=False)
# Returns: { status, client_profile, content_brief, paths, missing_fields, docs_found }
```

**Time:** ~15 seconds (the AGY call is the bottleneck)

**Failure modes:**
- `status: "error"` — no docs found, AGY failed, or invalid docs dir
- `status: "partial"` — extracted but some required fields are empty

### Step 2: SYNTHESIZE

**Input:** `client_profile.json` (from Step 1)

**Output:** `website_build_plan.md` (3,000+ words, comprehensive)
- §1 Site Architecture (page list, nav, SEO, redirects)
- §2 Per-Page Content Briefs (every page in detail)
- §3 Design System Specifications (colors, type, spacing, components, mood)
- §4 Asset Plan (logo, hero images, instructor portraits, icons)
- §5 Technical Requirements (platform, hosting, analytics)
- §6 Automation Workflows (email sequences, post-purchase flows)
- §7 Success Metrics (KPIs)

**Library API:**
```python
from prismatic_web_plugin.synthesize import run_synthesize
result = run_synthesize(profile_path, output_dir=None, skip_agy=False)
# Returns: { status, build_plan, path, word_count, client_name }
```

**Time:** ~60-90 seconds (AGY pro call)

**Failure modes:**
- `status: "error"` — invalid JSON, AGY call failed, empty output

### Step 3: DISTILL

**Input:** `website_build_plan.md` (from Step 2)

**Output:** A Linear epic with N child issues, where N is roughly:
- 1 per page (5-10 pages typical)
- 1 design system issue
- 1 asset curation issue
- 1 per automation (4 workflows typical)
- 1 CF Pages deploy

**Library API:**
```python
from prismatic_web_plugin.distill import run_distill
result = run_distill(plan_path, dry_run=False)
# Returns: { status, epic_id, child_ids, parsed, issues }
```

**Time:** ~5-10 seconds (Linear API calls)

**Failure modes:**
- `status: "error"` — Linear API failed, plan file missing

## The agent swarm handoff

After Step 3, the system waits for the agent swarm to do its work:

| Agent | Picks up issues labeled | Does what |
|---|---|---|
| `agent:fred` | Design system, asset curation, project coordination | Orchestrates, verifies, finalizes |
| `agent:kai` | Class detail, content-heavy pages | Writes the actual page content |
| `agent:kai-css` | Design system implementation | Implements the CSS design tokens |
| `agent:agy` | Asset generation (hero images, instructor portraits) | Generates imagery |
| `agent:ned` | Cloudflare Pages deploy, DNS, automation workflows | Infrastructure |
| `agent:ned-infra` | Same as ned but for infra-specific tasks | |
| `agent:ned-code` | Code review, code-related infrastructure | |
| `agent:automate-*` | (Future) Automation-specific tasks | Reserved for Phase 4+ |

The dispatchers pick up the children on the next cron tick (every 5-15 min) and start working. Each task produces a `RESULT.md` in its sandbox. The `pwb watch --epic <uuid>` command polls Linear every 60s and posts a progress comment every 10 min.

## The `pwb` CLI

```bash
# Run the full pipeline on a new client
pwb run --client <slug>
pwb run --client <slug> --skip-agy    # use stub for synthesize
pwb run --client <slug> --dry-run     # don't write files or Linear issues

# Watch a running build
pwb watch --epic <uuid> --interval 60 --max-runtime 86400

# Print status
pwb status --epic <uuid>
```

The `pwb` binary is registered via `pyproject.toml` script entry. After `pip install -e .`, it's on PATH.

## Real example: Meridian Women's Defense Academy

The Meridian build is the first end-to-end PWP run:

1. **Input:** 5 Website Dev docs in `growthwebdev-knowledge/okf/projects/website-dev/inputs/`
2. **Ingest:** produced `meridian-womens-defense-academy/client_profile.json` + `ingest_report.md`
3. **Synthesize:** produced `meridian-womens-defense-academy/website_build_plan.md` (3,467 words)
4. **Distill:** created Linear epic **GRO-2142** + 13 children
5. **Agent swarm:** built 5 pages, design system, asset curation, deploy config

As of 2026-06-23: **9/13 children Done**, 4 Automations still pending (Workflows A-D, all `agent:ned`/`agent:ned-infra`).

## How to use PWP for a new client

```bash
# 1. Install the plugin
pip install -e ~/work/prismatic-web-plugin

# 2. Get the client's 5 Website Dev docs into OKF
mkdir -p ~/work/growthwebdev-knowledge/okf/projects/<client-slug>
# (drop the 5 docs into that directory)

# 3. Run the pipeline
pwb run --client <client-slug>

# 4. Watch the build progress
pwb watch --epic <epic-id-from-step-3-output>

# 5. (Optionally) check status
pwb status --epic <epic-id>
```

That's it. The system handles the rest: builds plan, files Linear issues, dispatches to agents, watches progress, posts status updates.

## Why this works

- **The agent swarm already exists** — we just feed it the right Linear issues with the right labels
- **The 5 Website Dev docs are a complete content framework** — they cover everything needed for a website
- **AGY pro is a good enough synthesizer** — it produces a build plan that's actionable enough for the agent swarm
- **The build plan is structured** — pages, design, assets, automations, deploy — and the distill step maps each to a Linear issue
- **Lane governance protects the build** — agents can't push to wrong paths; only Fred merges to deploy-fresh

## What can go wrong

- **Missing framework docs** — Step 1 returns `error` if it can't find 5 docs
- **AGY hallucinates** — Step 2's build plan is good but not perfect; the swarm can refine it
- **Linear API rate limits** — Step 3 uses 2/3M complexity, 1/2500 requests; we're nowhere near the limit
- **Agents get stuck** — the `pwb watch` posts progress every 10 min; check sandbox `RESULT.md` if a task is overdue
- **Cloudflare Pages deploy fails** — Ned's lane handles this; check `webhooks.growthwebdev.com` for HMAC errors

## Related

- [PWP project hub](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/projects/prismatic-web-plugin/index.md)
- [PWP final links](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/hubs/pwp-final-links-2026-06-23.md)
- [AOT architecture template](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/standards/active-oahu-tours-architecture-template.md)
- [Agent dispatch architecture](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/standards/agent-dispatch-architecture.md)
- [UI/UX plan](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/standards/ui-ux-plan.md)
- [Process overhaul lessons](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/standards/prismatic-engine-process-overhaul.md)
- Linear: GRO-2137 (PWP-SYSTEM), GRO-2142 (Meridian epic), GRO-2226-2230 (PWP follow-ups)

## Change log

- 2026-06-23 16:30 UTC: Initial process doc. The PWP v0.1.0 is the durable artifact; this doc is the human/agent reference.
