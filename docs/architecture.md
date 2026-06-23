# Prismatic Web Plugin — Pipeline Architecture

The Prismatic Web Plugin (PWP) is a durable, generalized content-to-code pipeline that automates the creation and deployment of client websites. It acts as the orchestration framework that bridges client inputs to an autonomous agent swarm.

## High-Level Architecture

The pipeline consists of three core steps executed by the Prismatic Web Builder CLI (`pwb`), followed by an asynchronous handoff to the agent swarm for execution, review, and deployment.

```mermaid
graph TD
    subgraph Client Input
        Docs[5 Website Dev Docs]
    end

    subgraph PWP CLI (pwb run)
        S1[Step 1: Ingestion<br/>ingest.py] -->|client_profile.json| S2[Step 2: Synthesis<br/>synthesize.py]
        S2 -->|website_build_plan.md| S3[Step 3: Distillation<br/>distill.py]
    end

    subgraph Linear Integration
        S3 -->|Create Epic + Issues| LE[Linear Epic & Child Tasks]
    end

    subgraph Agent Swarm (Asynchronous Handoff)
        LE -->|agent:fred| A_Fred[Fred: Design, Assets, Coordination]
        LE -->|agent:kai| A_Kai[Kai: Content-heavy Pages]
        LE -->|agent:kai-css| A_KaiCSS[Kai-CSS: Design Tokens / CSS]
        LE -->|agent:agy| A_AGY[AGY: Asset Generation]
        LE -->|agent:ned| A_Ned[Ned: Deploy, DNS, Automations]
    end

    subgraph Review & Build
        A_Fred --> RL[Review Loop: AGY Pro + Fred]
        A_Kai --> RL
        A_KaiCSS --> RL
        A_AGY --> RL
        A_Ned --> RL
        RL -->|Approved| Deploy[Deploy: Cloudflare Pages]
    end

    Docs --> S1
```

---

## The Three Pipeline Steps

### 1. Ingestion (`ingest.py` / `ingest_generic.py`)
- **Input:** A source directory containing the client's **5 Website Dev Framework Documents** (typically sourced from Google Drive or OKF):
  1. *Doc 1: Content Gathering Guide*
  2. *Doc 2: Partner Interview*
  3. *Doc 3: Brand & Design Interview*
  4. *Doc 4: Conversion & Launch Kit*
  5. *Doc 5: Post-Purchase Automation*
- **Mechanism:** Parses the raw document structures (markdown/text), extracts relevant fields, and standardizes them.
- **Output:** Writes `<client-slug>/client_profile.json` and `content_brief.json` (along with an `ingest_report.md` specifying any missing parameters).

### 2. Synthesis (`synthesize.py` / `synthesize_generic.py`)
- **Input:** `client_profile.json` and `content_brief.json` (from Step 1).
- **Mechanism:** Sends the structured client data to **AGY Pro** (using the high-performance LLM configuration) with a detailed system prompt defining website best practices, design constraints, and structure.
- **Output:** Synthesizes `website_build_plan.md`, a detailed document (typically 3,000+ words) covering:
  - **Site Architecture:** Sitemap, navigation hierarchy, canonical redirects, SEO metadata.
  - **Per-Page Content Briefs:** Explicit outlines, copy guidelines, and components for every page.
  - **Design System Specifications:** Color palettes (HSL/Hex), typography, spacing, UI component styles, and responsiveness rules.
  - **Asset Plan:** Logo design directives, hero image generation instructions, iconographies, and portrait briefs.
  - **Technical Requirements:** Hosting, integrations (analytics, maps, forms), and script definitions.
  - **Automation Workflows:** Auto-response emails, post-purchase hooks, and CRM integrations.

### 3. Distillation (`distill.py` / `distill_generic.py`)
- **Input:** `website_build_plan.md` (from Step 2).
- **Mechanism:** Parses the structure of the build plan and interacts with the Linear GraphQL API to:
  1. Create a parent **Linear Epic** for the client website build.
  2. Parse the plan into individual, discrete task descriptions.
  3. Create **10-20 child issues** linked to the parent Epic, assigning them specific agent labels (`agent:kai`, `agent:kai-css`, `agent:agy`, `agent:ned`, etc.).
- **Output:** The Linear Epic ID and a list of created issue IDs.

---

## Swarm Handoff & Role Allocations

Once issues are filed on Linear, the orchestration engine schedules agent execution based on issue labels:

| Label | Role | Responsibilities |
|---|---|---|
| `agent:fred` | Swarm Governor | Coordinates the build, checks asset styling cohesion, manages git staging, and gives final sign-off. |
| `agent:kai` | Content Writer | Creates semantic HTML pages, populates them with client copy, and implements metadata. |
| `agent:kai-css` | Frontend Builder | Authors `index.css`, defines global design tokens, implements responsive layouts, and builds custom components. |
| `agent:agy` | Asset Designer | Generates assets (e.g., SVG icons, hero images using `generate_image`, logos) and populates the assets manifest. |
| `agent:ned` | Deployer & Infra | Configures Cloudflare Pages, manages DNS, binds custom headers/WAF rules, and builds post-purchase automation scripts. |

---

## Review, Build, and Deploy Workflow

1. **Local Sandboxed Build:** Agents work concurrently in isolated git worktree sandboxes (determined by their profile prefix, e.g., `content/`, `design/`, `execution/`).
2. **Result Verification:** When a task is complete, the agent writes a `RESULT.md` containing verification details.
3. **Review Loop:** Completed code is pushed to a PR. `agent:agy-pro` reviews the code quality, and `agent:fred` performs the final governance gates.
4. **Deploy:** Once the PR is merged by Fred to the release branch, the Cloudflare Pages deploy hook is triggered, publishing the site live.
