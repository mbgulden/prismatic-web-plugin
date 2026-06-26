# Bootstrapping a New Client Build From Scratch

This guide walks you through bootstrapping a website build for a new client using the Prismatic Web Plugin (PWP).

---

## Prerequisites
Before starting, ensure that:
1. You have the **Linear API Key** loaded in your environment (`LINEAR_API_KEY`).
2. The `prismatic-web-plugin` package is installed in developer mode:
   ```bash
   pip install -e ~/work/prismatic-web-plugin
   ```
3. The local client directory or your OKF project files are accessible.

---

## Step 1: Collect client documents
Obtain the **5 Website Dev Framework Documents** from the client (Google Drive / Doc templates). They must cover:
1. `content_gathering_guide` — Base client information, services, contact details.
2. `partner_interview` — Business backstory, core client narrative.
3. `brand_design_interview` — Design guidelines, preferred fonts, primary/secondary colors.
4. `conversion_launch_kit` — Call to action (CTA), form requirements, pages list.
5. `post_purchase_automation` — Post-purchase workflow definitions and auto-responders.

Save these files as Markdown (`.md`) or text (`.txt`) in a workspace directory matching the client's name slug (e.g. `~/work/growthwebdev-knowledge/okf/projects/my-new-client/`).

---

## Step 2: Prepare inputs directory
Create the directory and place the documents inside:

```bash
# Create directory
mkdir -p ~/work/growthwebdev-knowledge/okf/projects/my-new-client

# Verify documents exist inside the directory
ls ~/work/growthwebdev-knowledge/okf/projects/my-new-client/
```

Verify that the filenames contain patterns matching the canonical names (e.g., contains the words `partner_interview` or `partner-interview` or `Partner Interview`).

---

## Step 3: Run the Ingestion & Synthesis Pipeline
Run the `pwb run` command to process the documents.

```bash
pwb run --client my-new-client
```

### What happens:
1. **Ingest:** PWP reads the folder, matches the 5 docs, runs the extraction, and generates `client_profile.json` and `content_brief.json`.
2. **Synthesize:** PWP invokes **AGY Pro** to write the detailed website blueprint `website_build_plan.md`.
3. **Distill:** PWP reads the build plan, creates a **Linear Epic** (e.g. `GRO-XXXX`), and files all required child tasks, routing them to the correct agent swarms.

Take note of the **Linear Epic UUID** printed in the CLI output.

---

## Step 4: Monitor and Orchestrate the Build
To follow the progress of the agent swarm and post updates back to the client/Linear, run the `watch` tool:

```bash
pwb watch --epic <your-epic-uuid>
```

This command will:
- Poll Linear for task completion.
- Print live terminal updates.
- Comment on the Linear Epic with progress metrics (e.g., "7 of 12 tasks complete").

To get a quick summary of current task state, run:

```bash
pwb status --epic <your-epic-uuid>
```
