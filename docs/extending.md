# Extending Prismatic Web Plugin (PWP) for New Client Frameworks

The Prismatic Web Plugin is designed to be modular. You can extend it to support new client frameworks, input document structures (e.g., e-commerce, games, web apps), or different agent workflows.

---

## Architecture of Extension

Extending PWP to support a new framework or project type involves three steps corresponding to the three pipeline stages:

```
[Raw Inputs] ──> 1. Ingest (Define Doc Patterns) ──> 2. Synthesize (Update LLM Prompt) ──> 3. Distill (Add Task Mappings) ──> [Linear Tasks]
```

---

## Step 1: Extending Ingestion

To add support for new document types, you need to modify how documents are matched and how fields are extracted.

### A. Defining New Canonical Documents
If you have a new framework that uses, for example, 6 documents instead of the default 5, define them in `src/prismatic_web_plugin/ingest.py`:

```python
# Add your new document types to FRAMEWORK_DOCS
FRAMEWORK_DOCS = [
    ...
    ("seo_keyword_strategy", "SEO Keyword Strategy"),
    ("ecommerce_shipping_rules", "E-commerce & Shipping Setup"),
]
```

### B. Updating the Output Schema
Add any new fields you want to extract to `CLIENT_PROFILE_SCHEMA`:

```python
CLIENT_PROFILE_SCHEMA = {
    ...
    "ecommerce": {
        "payment_gateway": "Stripe",
        "shipping_carriers": [],
    }
}
```

### C. Adapting Generic Ingestion
If you are building a non-website project (e.g., a Telegram bot or a homelab system), extend the document classifier `detect_doc_type` in `src/prismatic_web_plugin/ingest_generic.py` to support new classifications:

```python
def detect_doc_type(path: Path) -> str:
    name = path.name.lower()
    if "api" in name or "webhook" in name:
        return "integration"
    if "database" in name or "schema" in name:
        return "database"
    ...
```

---

## Step 2: Extending Synthesis

The synthesis step uses **AGY Pro** to construct the build plan. To update the synthesis behavior:

1. Locate `src/prismatic_web_plugin/synthesize.py`.
2. Update the system prompt to guide the LLM on how to treat the new schema properties.
3. For example, if you added `ecommerce` configuration to the schema, append instructions to the prompt:
   ```python
   "Analyze the client's `ecommerce` profile keys. "
   "Detail Stripe integration hooks, shipping tables, and inventory rules in §5 Technical Requirements."
   ```

---

## Step 3: Extending Distillation

The distill step parses the synthesized build plan and files tasks on Linear.

### A. Adjusting Section Parsing
Distillation works by searching for markdown headings (e.g. `## Section Title`) in `website_build_plan.md`. If your new framework synthesis introduces new section headings, update the parser in `src/prismatic_web_plugin/distill.py` to recognize them.

### B. Adding Custom Agent Mapping
To route tasks to new specialized agent swarms (e.g. `agent:game-dev` or `agent:seo-specialist`), map the task types to Linear label IDs.
1. Retrieve the label ID from Linear:
   ```bash
   pwb list-labels
   ```
2. Add the label mapping to the distill script:
   ```python
   SPECIALIST_LABEL_ID = "your-guid-here"
   
   if "seo" in issue_title.lower():
       labels.append(SPECIALIST_LABEL_ID)
   ```
This ensures the issue is filed with the correct tags so the right dispatcher schedules it.
