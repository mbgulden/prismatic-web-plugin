#!/usr/bin/env python3
"""
pwp_ingest.py — Step 1 of the Prismatic Web Plugin system.

Reads any client's 5 Website Dev docs (the content-gathering framework)
and produces structured JSON output:
  - client_profile.json: business name, mission, USP, location, contact
  - content_brief.json: classes, testimonials, lead magnet, automation
  - ingest_report.md: what was parsed, what was missing/invalid

Uses AGY (Gemini 3.5 Flash High) to extract structured data from the docs.
The 5 docs are NOT uniform templates — they're conversational guides, so
the parser uses LLM-based extraction.

Usage:
    python3 pwp_ingest.py <path-to-5-docs-dir>

Output:
    <docs-dir>/output/<client-slug>/{client_profile.json,content_brief.json,ingest_report.md}
"""
import os, sys, json, re, subprocess, time
from pathlib import Path
from datetime import datetime, timezone

# The 5 framework docs, in canonical order
FRAMEWORK_DOCS = [
    ("01_business_core", "Doc 1: Business Core & Mission + Classes Directory"),
    ("02_partner_story", "Doc 2: Partner Interview & Story Extraction"),
    ("03_brand_design", "Doc 3: Brand Design Interview & Inspiration Directory"),
    ("04_launch_kit", "Doc 4: Conversion & Technical Launch Kit"),
    ("05_post_purchase", "Doc 5: Post-Purchase Automation Flow"),
]

# Output schema (the structured client profile)
CLIENT_PROFILE_SCHEMA = {
    "client_profile": {
        "name": "",
        "tagline": "",
        "mission": "",
        "usp": "",
        "core_values": [],
        "location": {"city": "", "state": "", "service_areas": []},
        "contact": {"phone": "", "email": "", "address": ""},
        "instructors": [],
    },
    "content": {
        "classes": [],  # list of {slug, title, summary, what_you_learn, prerequisites, gear, duration, price, call_to_action}
        "testimonials": [],  # list of {author, quote, date}
        "affiliations": [],  # list of org names
        "lead_magnet": {"title": "", "topics": []},  # title + list of topics
    },
    "design": {
        "color_palette": [],
        "typography": "",
        "mood": "",
        "reference_sites": [],
    },
    "technical": {
        "target_areas": [],
        "domain": "",
        "google_business": "",
        "has_logo": False,
    },
    "automation": {
        "email_sequences": [],
    },
}

def slugify(s: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s).strip("-")
    return s or "client"

def read_doc(path: Path) -> str:
    """Read a doc and return its body (skip frontmatter)."""
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            content = content[end + 3:].strip()
    return content

def find_5_docs(docs_dir: Path) -> dict:
    """Find the 5 framework docs in the input directory. Returns dict keyed by canonical name."""
    found = {}
    # Search for files matching the 5 patterns
    patterns = [
        ("01_business_core", ["Doc_1", "Document_1", "01_Business_Core", "company_profile", "class_"]),
        ("02_partner_story", ["Doc_2", "Document_2", "02_Partner_Interview", "partner_story", "partner_interview"]),
        ("03_brand_design", ["Doc_3", "Document_3", "03_Brand_Design", "brand_design"]),
        ("04_launch_kit", ["Doc_4", "Document_4", "04_Conversion", "04_Launch_Kit", "conversion"]),
        ("05_post_purchase", ["Doc_5", "Document_5", "05_Post_Purchase", "post_purchase"]),
    ]
    for canonical_name, aliases in patterns:
        # Try exact patterns first
        for f in docs_dir.iterdir():
            if not f.is_file() or not f.suffix.lower() in [".md", ".txt"]:
                continue
            fname = f.name
            for alias in aliases:
                if alias.lower() in fname.lower():
                    found[canonical_name] = f
                    break
            if canonical_name in found:
                break
    return found

def extract_with_agy(docs: dict) -> dict:
    """Use AGY (Gemini 3.5 Flash High) to extract structured data from the 5 docs."""

    # Build the prompt
    prompt_parts = [
        "You are a structured-data extraction assistant.",
        "Read the 5 website content gathering docs below and extract a comprehensive client profile as JSON.",
        "Output ONLY valid JSON — no commentary, no markdown, no explanation.",
        "",
        "Use this exact schema (fill in what you find, leave empty if not present):",
        json.dumps(CLIENT_PROFILE_SCHEMA, indent=2),
        "",
        "IMPORTANT notes about the schema:",
        "- `content.classes` is a LIST OF OBJECTS, not strings. Each class needs:",
        '  {"slug": "kebab-case-name", "title": "Class Title", "summary": "1-paragraph", "what_you_learn": ["skill 1", "skill 2"], "prerequisites": "...", "gear": "...", "duration": "4 hours", "price": "$125", "call_to_action": "Reserve Your Spot"}',
        "- `content.testimonials` is a LIST OF OBJECTS:",
        '  {"author": "Name", "quote": "the review text", "date": "YYYY-MM-DD"}',
        "- `content.lead_magnet.topics` is a LIST OF STRINGS (the topics covered)",
        "- `automation.email_sequences` is a LIST OF OBJECTS:",
        '  {"name": "Email 1: Confirmation", "trigger": "post-purchase", "subject": "...", "body": "..."}',
        "- If a field's not in the docs, use empty string, empty list, or empty object — NEVER null",
        "",
        "DOCS:",
        "",
    ]

    for canonical_name, description in FRAMEWORK_DOCS:
        if canonical_name in docs:
            content = read_doc(docs[canonical_name])
            prompt_parts.append(f"=== {description} ===")
            prompt_parts.append(content[:8000])  # truncate to fit context
            prompt_parts.append("")

    prompt_parts.append("")
    prompt_parts.append("Output the JSON now (only the JSON, nothing else):")

    prompt = "\n".join(prompt_parts)

    # Call AGY
    result = subprocess.run(
        [
            "/home/ubuntu/.local/bin/agy",
            "--model", "Gemini 3.5 Flash (High)",
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
        return {}

    # Parse the output (look for JSON in the response)
    output = result.stdout.strip()
    # Try to find JSON in the output
    json_match = re.search(r"\{[\s\S]*\}", output)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}", file=sys.stderr)
            print(f"Output was: {output[:500]}", file=sys.stderr)
            return {}
    print(f"No JSON found in AGY output: {output[:500]}", file=sys.stderr)
    return {}

def write_ingest_report(report_path: Path, docs: dict, extracted: dict, missing: list):
    """Write the ingest_report.md summarizing what was found and what's missing."""
    lines = [
        f"# Ingest Report — {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Docs found",
        "",
    ]
    for canonical_name, description in FRAMEWORK_DOCS:
        if canonical_name in docs:
            lines.append(f"- ✓ {description}: `{docs[canonical_name].name}`")
        else:
            lines.append(f"- ✗ {description}: **NOT FOUND**")

    lines.extend([
        "",
        "## Extracted data",
        "",
    ])
    if extracted:
        profile = extracted.get("client_profile", {})
        lines.append(f"- **Business name:** {profile.get('name', 'MISSING')}")
        lines.append(f"- **Tagline:** {profile.get('tagline', 'MISSING')}")
        lines.append(f"- **Mission:** {profile.get('mission', 'MISSING')[:200]}{'...' if len(profile.get('mission', '')) > 200 else ''}")
        lines.append(f"- **USP:** {profile.get('usp', 'MISSING')[:200]}{'...' if len(profile.get('usp', '')) > 200 else ''}")
        lines.append(f"- **Core values:** {', '.join(profile.get('core_values', [])) or 'MISSING'}")
        loc = profile.get("location", {})
        lines.append(f"- **Location:** {loc.get('city', '?')}, {loc.get('state', '?')}")
        lines.append(f"- **Service areas:** {', '.join(loc.get('service_areas', [])) or 'MISSING'}")
        content = extracted.get("content", {})
        lines.append(f"- **Classes:** {len(content.get('classes', []))} found")
        lines.append(f"- **Testimonials:** {len(content.get('testimonials', []))} found")
        lines.append(f"- **Affiliations:** {', '.join(content.get('affiliations', [])) or 'MISSING'}")
        lm = content.get("lead_magnet", {})
        lines.append(f"- **Lead magnet:** {lm.get('title', 'MISSING')}")
        lines.append(f"- **Email sequences:** {len(extracted.get('automation', {}).get('email_sequences', []))} found")
        design = extracted.get("design", {})
        lines.append(f"- **Mood:** {design.get('mood', 'MISSING')}")
        lines.append(f"- **Reference sites:** {len(design.get('reference_sites', []))} found")
    else:
        lines.append("- **EXTRACTION FAILED** — see errors above")

    if missing:
        lines.extend([
            "",
            "## Missing / incomplete data",
            "",
        ])
        for m in missing:
            lines.append(f"- {m}")

    report_path.write_text("\n".join(lines), encoding="utf-8")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 pwp_ingest.py <path-to-5-docs-dir>", file=sys.stderr)
        sys.exit(1)

    docs_dir = Path(sys.argv[1]).resolve()
    if not docs_dir.is_dir():
        print(f"Error: {docs_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Ingesting from: {docs_dir}")

    # Find the 5 docs
    docs = find_5_docs(docs_dir)
    if not docs:
        print(f"Error: no docs found matching the 5 framework patterns", file=sys.stderr)
        sys.exit(2)

    print(f"Found {len(docs)}/5 docs:")
    for canonical_name, description in FRAMEWORK_DOCS:
        status = "✓" if canonical_name in docs else "✗"
        print(f"  {status} {description}")

    # Extract structured data
    print("\nExtracting structured data with AGY...")
    extracted = extract_with_agy(docs)
    if not extracted:
        print("Error: extraction failed", file=sys.stderr)
        sys.exit(3)

    # Determine client slug from name
    client_name = extracted.get("client_profile", {}).get("name", "")
    if not client_name:
        client_name = docs_dir.name
    slug = slugify(client_name)

    # Output directory
    out_dir = docs_dir / "output" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write outputs
    profile_path = out_dir / "client_profile.json"
    brief_path = out_dir / "content_brief.json"
    report_path = out_dir / "ingest_report.md"

    # Merge into the schema (preserve defaults, override with extracted)
    final = {**CLIENT_PROFILE_SCHEMA, **extracted}

    profile_path.write_text(json.dumps(final, indent=2), encoding="utf-8")
    brief_path.write_text(json.dumps(final.get("content", {}), indent=2), encoding="utf-8")

    # Check for missing required fields
    missing = []
    required = [
        ("client_profile.name", final.get("client_profile", {}).get("name")),
        ("client_profile.mission", final.get("client_profile", {}).get("mission")),
        ("content.classes", final.get("content", {}).get("classes")),
        ("automation.email_sequences", final.get("automation", {}).get("email_sequences")),
    ]
    for path, val in required:
        if not val or (isinstance(val, list) and len(val) == 0):
            missing.append(f"`{path}` is empty — follow up with client")

    write_ingest_report(report_path, docs, final, missing)

    print(f"\nWrote:")
    print(f"  {profile_path}")
    print(f"  {brief_path}")
    print(f"  {report_path}")
    if missing:
        print(f"\nMissing required fields:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(4)  # partial success

    print("\n✓ Ingest complete (all required fields present)")

if __name__ == "__main__":
    main()