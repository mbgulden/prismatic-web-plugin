# prismatic-web-plugin

> The durable, generalized PWP that turns any client's Website Content Gathering Framework into a deployed website via the Prismatic Engine agent swarm.

## What this is

The Prismatic Web Plugin (PWP) is the **system** that:

1. **Ingests** any client's completed Website Content Gathering Framework (the 5 Drive docs)
2. **Synthesizes** an actionable website build plan
3. **Distills** the build plan into Linear tasks with proper agent routing
4. **Dispatches** the agent swarm (AGY/Ned/Kai/Jules) to execute the build
5. **Reviews** via the existing review loop
6. **Deploys** to Cloudflare Pages
7. **Documents** the build in OKF for future client onboarding

## Quick start

```bash
# Install (from source)
pip install -e .

# Run the full pipeline on a new client
pwp run --client meridian-womens-defense

# Watch a running build
pwp watch --epic <epic-uuid>

# Print status
pwp status --epic <epic-uuid>
```

## Pipeline stages

| Step | Script | Output | Status |
|------|--------|--------|--------|
| 1. Ingest | `pwp_ingest.py` | `client_profile.json` + `content_brief.json` | Done |
| 2. Synthesize | `pwp_synthesize.py` | `website_build_plan.md` | Done |
| 3. Distill | `pwp_distill.py` | Linear epic + 10-20 child issues | Done |
| 4. Dispatch | (existing AGY/Ned/Kai dispatchers) | Worker tasks in flight | Live |
| 5. Build | (agent swarm) | Pages + assets + Result.md | Live |
| 6. Review | (AGY pro + Fred) | Sign-off on each task | Live |
| 7. Deploy | (Ned) | Cloudflare Pages site | Live |
| 8. Document | (this orchestrator) | OKF handoff package | Todo |

## Status

- **Steps 1-3**: Done (proven on Meridian Women's Defense Academy + 4 other projects)
- **Demo build (Meridian)**: In progress (6/15 pages done, agent swarm executing)
- **Orchestrator (this repo)**: Todo (this build)
- **Plugin skeleton + GRO-1497 hooks**: Todo (Phase 3 of master synthesis)

## Repo structure

```
prismatic-web-plugin/
├── src/
│   └── prismatic_web_plugin/
│       ├── __init__.py
│       ├── orchestrator.py    # The system (this build)
│       ├── ingest.py          # Step 1
│       ├── synthesize.py      # Step 2
│       ├── distill.py         # Step 3
│       ├── ingest_generic.py  # Generic ingest (any project type)
│       ├── synthesize_generic.py
│       └── distill_generic.py
├── tests/                     # Test suite (todo)
├── docs/                      # Architecture + usage docs
├── okf/                       # OKF metadata (frontmatter, standards)
├── examples/                  # Example client runs
├── bin/                       # CLI scripts
├── pyproject.toml             # Python package metadata
└── README.md                  # This file
```

## Related

- [PWP project hub](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/projects/prismatic-web-plugin/index.md)
- [Master synthesis](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/projects/prismatic-source-plans-master-synthesis-2026-06-23.md)
- [AOT architecture template](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/standards/active-oahu-tours-architecture-template.md)
- [Agent dispatch architecture](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/standards/agent-dispatch-architecture.md)
- [UI/UX plan](https://files.growthwebdev.com/raw/growthwebdev-knowledge/okf/standards/ui-ux-plan.md)
- Linear: GRO-2137 (PWP-SYSTEM), GRO-2132 (MVP), GRO-2185 (PWP-UI), GRO-2142 (Meridian epic)

## License

MIT
