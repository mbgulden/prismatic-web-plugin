#!/usr/bin/env python3
"""
pwp_synthesize.py — Step 2 of the Prismatic Web Plugin system.

Takes the structured client JSON (from Step 1) and produces a comprehensive
website_build_plan.md — the actionable spec that drives the agent swarm build.

Uses AGY pro (Gemini 3.1 Pro High) for high-quality synthesis.

Usage:
    python3 pwp_synthesize.py <path-to-client_profile.json>

Output:
    <input-dir>/website_build_plan.md — the build plan
"""
import os, sys, json, re, subprocess, time
from pathlib import Path
from datetime import datetime, timezone

SYNTHESIS_PROMPT_TEMPLATE = """You are a senior web architect producing a comprehensive build plan for a client website.

Read the structured client profile below and produce a `website_build_plan.md` — the actionable spec
that will drive the entire agent swarm build (content generation, design, build, deploy, automation).

# Client Profile

```json
{client_profile}
```

# Your task

Produce a comprehensive markdown build plan with the following sections. Be CONCRETE — no generic
"create a homepage" placeholders. Use actual slugs, actual color hex codes, actual page content.
A human web architect should be able to take your plan and build the site without further questions.

## Required sections

### 1. Site Architecture
- Full page list (slug, page type, primary purpose)
- Navigation structure (primary + secondary + footer)
- URL patterns (e.g., /, /about/, /classes/<slug>/)
- Redirect rules (if any)

### 2. Per-Page Content Briefs
For EACH page in the architecture:
- Page slug
- Page type (Home / About / Classes index / Class detail / Gallery / Contact / Lead Magnet / Confirmation / etc.)
- Hero section: headline, subheadline, CTA, image description
- Body sections: what content goes here, in what order
- Schema.org markup (LocalBusiness, Course, FAQPage, Event, etc.)
- Acceptance criteria for "this page is done well"

### 3. Design System Spec
- Color palette: 6-8 hex codes with usage (primary, secondary, accent, neutral, etc.)
- Typography: heading font, body font, font sizes for h1-h6
- Spacing system: base unit (e.g., 8px grid)
- Component library: button styles, card styles, form styles
- Brand mood: 5 adjectives (e.g., "empowering, safe, premium, community, professional")
- Reference sites: which competitor sites to study (from the input) + what to take from each

### 4. Asset Plan
- Logo: existing or to design
- Hero images: count, source (Unsplash collection / AGY image gen / client-provided)
- Class photos: count, source
- Instructor portraits: count, source
- Icons: which SVG icons needed
- Total asset count + estimated budget (in time or $)

### 5. Technical Requirements
- Stack: (e.g., Astro + Cloudflare Pages + D1 + Portable Text)
- Local SEO: target areas, schema markup, Google Business Profile integration
- Forms: lead magnet capture (where emails go), contact form
- Analytics: what to track
- Performance: target metrics (LCP, CLS, TTI)
- Accessibility: target level (WCAG AA minimum)

### 6. Automation Workflows
For EACH email sequence in the client profile:
- Trigger event (post-purchase, 3-days-before, post-class)
- Email 1 subject + body outline
- Email 2 subject + body outline
- Email 3 subject + body outline
- Lead magnet delivery (PDF generation, email service, automation tool)

### 7. Build Sequence
- Recommended order (foundation → content → design → polish)
- Which tasks can run in parallel
- Critical path (what blocks everything else)
- Acceptance criteria for each phase

### 8. Acceptance Criteria — "Well Thought Out"
Per Michael's direction: "everything we build going forward goes forth with speed and efficiency" + "high quality and well thought out".
- Specific quality bars for each page (e.g., "homepage must score 95+ on Lighthouse")
- Specific design checks (e.g., "every page must have a real hero image, not placeholder")
- Specific content checks (e.g., "every class page must have what_you_learn, prereqs, gear, price, CTA")
- Specific review gates (e.g., "AGY pro must review code before deploy")

## Quality bar

- >= 2000 words
- Concrete specifics, no generic placeholders
- Every section filled in based on the client profile
- Every page has an acceptance criteria

Output ONLY the markdown build plan, no preamble, no commentary."""

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s).strip("-")
    return s or "client"

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 pwp_synthesize.py <path-to-client_profile.json>", file=sys.stderr)
        sys.exit(1)

    profile_path = Path(sys.argv[1]).resolve()
    if not profile_path.is_file():
        print(f"Error: {profile_path} is not a file", file=sys.stderr)
        sys.exit(2)

    print(f"Synthesizing build plan from: {profile_path}")

    # Read the client profile
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    # Build the prompt
    prompt = SYNTHESIS_PROMPT_TEMPLATE.replace("{client_profile}", json.dumps(profile, indent=2))

    # Call AGY pro (use the actual model name in AGY's valid list)
    print("Synthesizing with AGY pro (Gemini 3.1 Pro High)...")
    result = subprocess.run(
        [
            "/home/ubuntu/.local/bin/agy",
            "--model", "Gemini 3.1 Pro (High)",
            "--prompt", prompt,
            "--print-timeout", "5m0s",
            "--dangerously-skip-permissions",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        print(f"AGY error: {result.stderr}", file=sys.stderr)
        sys.exit(3)

    output = result.stdout.strip()
    if not output:
        print("AGY returned empty output", file=sys.stderr)
        sys.exit(4)

    # Strip any leading/trailing markdown code fences (in case AGY adds them)
    output = re.sub(r"^```markdown\s*\n", "", output, flags=re.IGNORECASE)
    output = re.sub(r"^```\s*\n", "", output)
    output = re.sub(r"\n```\s*$", "", output)

    # Write the build plan
    client_name = profile.get("client_profile", {}).get("name", "")
    if not client_name:
        client_name = profile_path.parent.name
    slug = slugify(client_name)

    # Output to a sibling of the profile JSON: <input-dir>/<slug>/website_build_plan.md
    out_dir = profile_path.parent  # assume the JSON is in the client output dir
    build_plan_path = out_dir / "website_build_plan.md"
    build_plan_path.write_text(output, encoding="utf-8")

    word_count = len(output.split())
    print(f"\nWrote: {build_plan_path}")
    print(f"Word count: {word_count} (target: >= 2000)")
    if word_count < 2000:
        print("WARNING: build plan is short — may need higher quality model or larger context")
        sys.exit(5)

    print("\n✓ Synthesis complete")

if __name__ == "__main__":
    main()