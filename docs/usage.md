# Prismatic Web Builder (pwb) CLI Usage Guide

The **Prismatic Web Builder** CLI (`pwb`) is the control interface for managing website builds. It is installed automatically when the package is installed in editable developer mode.

```bash
# Installation (run from the prismatic-web-plugin root directory)
pip install -e .
```

---

## 1. Running the Build Pipeline (`pwb run`)

The `run` command executes the Ingest, Synthesize, and Distill steps end-to-end for a given client slug.

```bash
pwb run --client <client-slug> [options]
```

### Options:
- `--client <slug>` (Required): The unique slug representing the client (e.g. `meridian-womens-defense`). This slug must correspond to the folder name where the client's 5 Website Dev docs are stored.
- `--skip-agy`: Bypasses calling the heavy LLM synthesizer and uses a pre-defined layout stub to generate the build plan. Useful for debugging ingestion or distillation steps.
- `--dry-run`: Performs all parsing and plan generation locally but does **not** create the Linear Epic or any child issues.

### Examples:

**Typical production run:**
```bash
pwb run --client meridian-womens-defense
```

**Testing ingestion and distillation structure without wasting LLM tokens or creating Linear noise:**
```bash
pwb run --client meridian-womens-defense --skip-agy --dry-run
```

---

## 2. Watching Build Progress (`pwb watch`)

The `watch` command monitors a running build by polling Linear at regular intervals, outputting agent activity updates, and publishing periodic progress reports back to the Linear Epic.

```bash
pwb watch --epic <epic-uuid> [options]
```

### Options:
- `--epic <uuid>` (Required): The UUID of the Linear Epic representing the client website build.
- `--interval <seconds>`: Polling frequency for fetching issue states from Linear. Defaults to `60` seconds.
- `--max-runtime <seconds>`: Maximum duration the watch process will run before automatically shutting down. Defaults to `86400` seconds (24 hours).

### Example:
```bash
pwb watch --epic 2eb2913f-740c-4142-b844-59feec230a9d --interval 120
```

---

## 3. Querying Build Status (`pwb status`)

The `status` command provides a snapshot overview of a client build. It displays the current status of each child task, who is assigned, and general completion statistics.

```bash
pwb status --epic <epic-uuid>
```

### Example Output:
```
Epic: Meridian Women's Defense Academy Website Build (GRO-2142)
Status: IN PROGRESS (69% complete - 9 of 13 tasks completed)

Tasks:
  [Done]   GRO-2143: [DESIGN] Implement theme design system (agent:kai-css)
  [Done]   GRO-2144: [CONTENT] Build Home Page (agent:kai)
  [Done]   GRO-2145: [CONTENT] Build About Us Page (agent:kai)
  [Done]   GRO-2146: [CONTENT] Build Classes Detail Page (agent:kai)
  [Done]   GRO-2147: [ASSETS] Generate hero illustrations & graphics (agent:agy)
  [Done]   GRO-2148: [CONTENT] Build Contact Page (agent:kai)
  [Done]   GRO-2149: [CONTENT] Build FAQ Page (agent:kai)
  [Done]   GRO-2150: [INFRA] Deploy to Cloudflare Pages (agent:ned)
  [Done]   GRO-2151: [INFRA] Set up custom domain redirects (agent:ned)
  [Todo]   GRO-2152: [INFRA] Post-purchase email automation (agent:ned-infra)
  [Todo]   GRO-2153: [INFRA] Lead generation form integration (agent:ned-infra)
  [Todo]   GRO-2154: [INFRA] Checkout webhook webhook receiver (agent:ned-infra)
  [Todo]   GRO-2155: [INFRA] CRM sync automation (agent:ned-infra)
```
