#!/usr/bin/env python3
"""
pwp_distill.py — Step 3 of the Prismatic Web Plugin system.

Takes a website_build_plan.md (from Step 2) and creates a Linear epic +
10-20 child issues with proper agent:* labels and OKF context.

Usage:
    python3 pwp_distill.py <path-to-website_build_plan.md>
    python3 pwp_distill.py <path-to-website_build_plan.md> --dry-run

Options:
    --dry-run  Print the issues that would be created without actually creating them.
"""
import os, sys, json, re, subprocess, argparse
from pathlib import Path
from datetime import datetime, timezone

# Linear API key from env
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
if not LINEAR_API_KEY:
    env_path = "/home/ubuntu/.hermes/profiles/orchestrator/.env"
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                if k.strip() == "LINEAR_API_KEY":
                    LINEAR_API_KEY = v.strip().strip('"').strip("'")
                    break
if not LINEAR_API_KEY:
    print("Error: LINEAR_API_KEY not set", file=sys.stderr)
    sys.exit(1)

TEAM_ID = "b6fb2651-5a1f-4714-9bcd-9eb6e759ffef"
PRISMATIC_PROJECT = "2eb2913f-740c-4142-b844-59feec230a9d"
TODO_STATE = "3d29ebe3-00cf-428b-b52a-bfecb5ae4410"

# Linear label UUIDs (hardcoded for speed — these are stable)
LABELS = {
    "agent:fred": "a43efb77-534a-4e39-8ff3-76f0e42019d1",
    "agent:agy": "1b69d9c0-20a8-45b3-a594-771b8cba75a7",
    "agent:agy-pro": None,  # need to look up
    "agent:ned": "6e0400c9-fc04-4868-86e3-f3156821f413",
    "agent:ned-infra": None,
    "agent:kai": "c4d929be-8d15-4482-b6d7-a5ed85aa2e73",
    "agent:kai-css": None,
    "agent:kai-content": None,
    "agent:kai-js": None,
    "pipeline:simple": None,
    "type:docs": None,
}

def gql(query, variables=None):
    import urllib.request
    payload = {"query": query, "variables": variables or {}}
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=json.dumps(payload).encode(),
        headers={"Authorization": LINEAR_API_KEY, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def lookup_labels():
    """Look up label UUIDs from Linear API."""
    r = gql(
        """query {
          issueLabels(first: 100) { nodes { id name } }
        }"""
    )
    for node in r["data"]["issueLabels"]["nodes"]:
        for key in LABELS:
            if key.startswith("agent:") or key.startswith("pipeline:") or key.startswith("type:"):
                if node["name"] == key:
                    LABELS[key] = node["id"]

def parse_build_plan(plan_text: str) -> dict:
    """Parse the build plan markdown and extract structured data."""
    parsed = {
        "client_name": "",
        "pages": [],         # list of {slug, title, type}
        "design_spec": {},   # colors, typography, etc
        "tech_stack": {},    # stack, seo, perf, a11y
        "automations": [],   # list of {name, trigger, description}
        "phases": [],        # list of {phase, name, days, tasks}
        "acceptance": [],    # list of quality bars
    }

    # Extract client name from the title
    m = re.search(r"^#\s+(.+?):", plan_text, re.MULTILINE)
    if m:
        parsed["client_name"] = m.group(1).strip()

    # Extract pages from "Full Page List" section
    pages_match = re.search(r"## 1\.1 Full Page List\s*\n(.*?)(?=\n## 1\.2|\Z)", plan_text, re.DOTALL)
    if pages_match:
        page_text = pages_match.group(1)
        # Find all page lines: * `slug` (Title): description
        for m in re.finditer(r"\*\s+\*\*[`']([^`']+)[`']\s+\(([^)]+)\)\*\*:?\s*(.*?)(?=\n\*|\n\n|\Z)", page_text, re.DOTALL):
            slug = m.group(1).strip()
            title = m.group(2).strip()
            desc = m.group(3).strip()[:200]
            parsed["pages"].append({"slug": slug, "title": title, "description": desc})

    # Extract pages from Per-Page Content Briefs section
    briefs_match = re.search(r"## 2\. Per-Page Content Briefs\s*\n(.*?)(?=\n## 3\.|\Z)", plan_text, re.DOTALL)
    if briefs_match:
        # Each page brief starts with ### 2.X Title (slug)
        for m in re.finditer(r"###\s+2\.\d+\s+(.+?)\s+\(([^)]+)\)", briefs_match.group(1)):
            slug = m.group(2).strip()
            title = m.group(1).strip()
            # Avoid duplicates
            if not any(p["slug"] == slug for p in parsed["pages"]):
                parsed["pages"].append({"slug": slug, "title": title, "description": ""})

    # Extract build phases from "Build Sequence" section
    phases_match = re.search(r"## 7\. Build Sequence\s*\n(.*?)(?=\n## 8\.|\Z)", plan_text, re.DOTALL)
    if phases_match:
        for m in re.finditer(r"###\s+Phase\s+(\d+):\s+(.+?)\s+\(([^)]+)\)", phases_match.group(1)):
            parsed["phases"].append({
                "phase": int(m.group(1)),
                "name": m.group(2).strip(),
                "duration": m.group(3).strip(),
            })

    # Extract automation workflows
    auto_match = re.search(r"## 6\. Automation Workflows\s*\n(.*?)(?=\n## 7\.|\Z)", plan_text, re.DOTALL)
    if auto_match:
        for m in re.finditer(r"###\s+6\.\d+\s+(.+)", auto_match.group(1)):
            parsed["automations"].append({"name": m.group(1).strip()})

    return parsed

def issue_for_page(client_name: str, page: dict, build_plan_path: str) -> dict:
    """Build a Linear issue for a page."""
    slug = page["slug"].strip("/")
    title = page["title"].strip()
    return {
        "title": f"[{client_name}] Build page: {title} ({slug})",
        "description": (
            f"**Page:** `{slug}`\n"
            f"**Title:** {title}\n"
            f"**Description:** {page.get('description', 'See build plan')}\n\n"
            f"**From build plan:** `{build_plan_path}`\n\n"
            f"## Acceptance criteria\n"
            f"- Page renders with the hero (headline, subheadline, CTA, image)\n"
            f"- Page is mobile-responsive (test on 3 breakpoints)\n"
            f"- Schema.org markup present (per build plan)\n"
            f"- Internal links work, no broken links\n"
            f"- Lighthouse score >= 95\n\n"
            f"## Verification\n"
            f"```bash\n"
            f"curl -s http://localhost:4321{page['slug']} | head -50\n"
            f"```\n"
        ),
        "labels": ["agent:agy"],
        "priority": 2,
    }

def issue_for_design(client_name: str, plan_path: str) -> dict:
    return {
        "title": f"[{client_name}] Design system implementation (colors, type, components)",
        "description": (
            f"Implement the design tokens from the build plan.\n\n"
            f"**From build plan:** `{plan_path}` §3 Design System Spec\n\n"
            f"## Tasks\n"
            f"- [ ] Set up color palette as CSS variables (per build plan §3.1)\n"
            f"- [ ] Import typography (heading + body fonts)\n"
            f"- [ ] Build spacing scale (per build plan §3.3)\n"
            f"- [ ] Implement component library: buttons, cards, forms (per build plan §3.4)\n"
            f"- [ ] Reference sites mood board (per build plan §3.6)\n\n"
            f"## Acceptance criteria\n"
            f"- All colors used match the build plan hex codes\n"
            f"- Typography consistent across pages\n"
            f"- Components match the spec\n"
        ),
        "labels": ["agent:kai-css"],
        "priority": 1,
    }

def issue_for_assets(client_name: str, plan_path: str) -> dict:
    return {
        "title": f"[{client_name}] Asset curation — hero images, class photos, instructor portraits, icons",
        "description": (
            f"Cure/source all assets per the build plan asset inventory.\n\n"
            f"**From build plan:** `{plan_path}` §4 Asset Plan\n\n"
            f"## Tasks\n"
            f"- [ ] Logo (use existing or design)\n"
            f"- [ ] Hero images for Home, About, Classes\n"
            f"- [ ] Class photos (per build plan)\n"
            f"- [ ] Instructor portraits\n"
            f"- [ ] SVG icons\n\n"
            f"## Sources\n"
            f"- Unsplash (royalty-free): for hero images\n"
            f"- AGY SDK image gen (Gemini Omni): for branded/custom assets\n"
            f"- Client-provided: for logo and any real photos\n\n"
            f"## Acceptance criteria\n"
            f"- Every page has at least one real image (no placeholders)\n"
            f"- All assets have proper attribution\n"
        ),
        "labels": ["agent:agy"],
        "priority": 2,
    }

def issue_for_automation(client_name: str, plan_path: str, automation: dict) -> dict:
    return {
        "title": f"[{client_name}] Automation: {automation['name']}",
        "description": (
            f"Implement the automation workflow per the build plan.\n\n"
            f"**From build plan:** `{plan_path}` §6 Automation Workflows\n\n"
            f"## Workflow\n"
            f"{automation['name']}\n\n"
            f"## Tasks\n"
            f"- [ ] Set up email service integration (ConvertKit / MailerLite / Brevo)\n"
            f"- [ ] Implement trigger event (per build plan)\n"
            f"- [ ] Build email templates (per build plan)\n"
            f"- [ ] Test end-to-end\n\n"
            f"## Acceptance criteria\n"
            f"- Trigger fires on the right event\n"
            f"- All 3 emails in the sequence deliver correctly\n"
            f"- Subject lines + body match the build plan\n"
        ),
        "labels": ["agent:ned"],
        "priority": 3,
    }

def issue_for_deploy(client_name: str, plan_path: str) -> dict:
    return {
        "title": f"[{client_name}] Cloudflare Pages deploy + DNS + monitoring",
        "description": (
            f"Deploy the site to Cloudflare Pages, set up DNS, configure monitoring.\n\n"
            f"**From build plan:** `{plan_path}` §5 Technical Requirements\n\n"
            f"## Tasks\n"
            f"- [ ] Create Cloudflare Pages project\n"
            f"- [ ] Connect to GitHub repo\n"
            f"- [ ] Set up custom domain (per build plan §5 / §1.3)\n"
            f"- [ ] Configure 301 redirects (HTTP→HTTPS, www→non-www, etc.)\n"
            f"- [ ] Set up analytics (per build plan §5.3)\n"
            f"- [ ] Set up uptime monitoring\n\n"
            f"## Acceptance criteria\n"
            f"- Site is live at the custom domain\n"
            f"- All redirects work\n"
            f"- Analytics tracking all pages\n"
            f"- Monitoring alerts on downtime\n"
        ),
        "labels": ["agent:ned-infra"],
        "priority": 1,
    }

def create_issue(title: str, description: str, labels: list, priority: int, parent_id: str = None) -> str:
    """Create a Linear issue. Returns issue identifier (e.g., GRO-1234)."""
    label_ids = [LABELS[l] for l in labels if LABELS.get(l)]
    if not label_ids:
        label_ids = [LABELS["agent:fred"]]
    input_data = {
        "teamId": TEAM_ID,
        "title": title,
        "description": description,
        "priority": priority,
        "stateId": TODO_STATE,
        "projectId": PRISMATIC_PROJECT,
        "labelIds": label_ids,
    }
    if parent_id:
        input_data["parentId"] = parent_id
    r = gql(
        """mutation($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success issue { identifier }
          }
        }""",
        {"input": input_data}
    )
    if r.get("data", {}).get("issueCreate", {}).get("success"):
        return r["data"]["issueCreate"]["issue"]["identifier"]
    print(f"  ✗ Failed to create issue: {title[:60]}", file=sys.stderr)
    print(f"    {json.dumps(r, indent=2)[:300]}", file=sys.stderr)
    return None

def main():
    parser = argparse.ArgumentParser(description="Distill a build plan into Linear issues")
    parser.add_argument("plan_path", help="Path to website_build_plan.md")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually create issues")
    args = parser.parse_args()

    plan_path = Path(args.plan_path).resolve()
    if not plan_path.is_file():
        print(f"Error: {plan_path} is not a file", file=sys.stderr)
        sys.exit(1)

    print(f"Distilling build plan: {plan_path}")

    # Look up labels
    lookup_labels()

    # Parse the build plan
    plan_text = plan_path.read_text(encoding="utf-8")
    parsed = parse_build_plan(plan_text)
    print(f"  Client: {parsed['client_name']}")
    print(f"  Pages: {len(parsed['pages'])}")
    print(f"  Phases: {len(parsed['phases'])}")
    print(f"  Automations: {len(parsed['automations'])}")

    if not parsed["pages"]:
        print("Warning: no pages parsed. Check the build plan format.", file=sys.stderr)

    if args.dry_run:
        print("\n=== DRY RUN — would create the following issues ===\n")
        for page in parsed["pages"]:
            print(f"  • {issue_for_page(parsed['client_name'], page, str(plan_path))['title']}")
        print(f"  • {issue_for_design(parsed['client_name'], str(plan_path))['title']}")
        print(f"  • {issue_for_assets(parsed['client_name'], str(plan_path))['title']}")
        for auto in parsed["automations"]:
            print(f"  • {issue_for_automation(parsed['client_name'], str(plan_path), auto)['title']}")
        print(f"  • {issue_for_deploy(parsed['client_name'], str(plan_path))['title']}")
        return

    # Create the parent epic first
    epic_title = f"[{parsed['client_name']}] Website build epic (from build plan)"
    epic_description = (
        f"**Source:** `{plan_path}`\n\n"
        f"**Client:** {parsed['client_name']}\n"
        f"**Pages:** {len(parsed['pages'])}\n"
        f"**Phases:** {len(parsed['phases'])}\n"
        f"**Automations:** {len(parsed['automations'])}\n\n"
        f"Generated from the Prismatic Web Plugin build plan. All child issues are derived from the plan's site architecture, design system, and automation workflows."
    )
    print(f"\nCreating epic: {epic_title}")
    epic_id_str = create_issue(epic_title, epic_description, ["agent:fred"], 1)
    print(f"  ✓ {epic_id_str}")

    # Get the epic UUID for parenting (use number filter, not identifier)
    r = gql(f"""query {{ issues(filter: {{ number: {{ eq: {int(epic_id_str.split('-')[1])} }} }}) {{ nodes {{ id }} }} }}""")
    epic_uuid = r["data"]["issues"]["nodes"][0]["id"]

    import time
    created = [epic_id_str]

    # Per-page issues
    print(f"\nCreating {len(parsed['pages'])} page issues...")
    for page in parsed["pages"]:
        issue = issue_for_page(parsed["client_name"], page, str(plan_path))
        ident = create_issue(issue["title"], issue["description"], issue["labels"], issue["priority"], parent_id=epic_uuid)
        if ident:
            created.append(ident)
            print(f"  ✓ {ident}  {issue['title'][:60]}")
        time.sleep(0.3)

    # Design system
    issue = issue_for_design(parsed["client_name"], str(plan_path))
    ident = create_issue(issue["title"], issue["description"], issue["labels"], issue["priority"], parent_id=epic_uuid)
    if ident:
        created.append(ident)
        print(f"\n✓ {ident}  {issue['title'][:60]}")
    time.sleep(0.3)

    # Assets
    issue = issue_for_assets(parsed["client_name"], str(plan_path))
    ident = create_issue(issue["title"], issue["description"], issue["labels"], issue["priority"], parent_id=epic_uuid)
    if ident:
        created.append(ident)
        print(f"✓ {ident}  {issue['title'][:60]}")
    time.sleep(0.3)

    # Automations
    for auto in parsed["automations"]:
        issue = issue_for_automation(parsed["client_name"], str(plan_path), auto)
        ident = create_issue(issue["title"], issue["description"], issue["labels"], issue["priority"], parent_id=epic_uuid)
        if ident:
            created.append(ident)
            print(f"✓ {ident}  {issue['title'][:60]}")
        time.sleep(0.3)

    # Deploy
    issue = issue_for_deploy(parsed["client_name"], str(plan_path))
    ident = create_issue(issue["title"], issue["description"], issue["labels"], issue["priority"], parent_id=epic_uuid)
    if ident:
        created.append(ident)
        print(f"✓ {ident}  {issue['title'][:60]}")

    print(f"\n=== Created {len(created)} Linear issues ===")
    print(f"Epic: {epic_id_str}")
    print(f"Children: {len(created) - 1}")

if __name__ == "__main__":
    main()