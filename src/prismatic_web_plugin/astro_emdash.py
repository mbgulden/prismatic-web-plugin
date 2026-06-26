"""Astro + EmDash site kernel for the Prismatic Web Plugin.

This module owns the durable website-system scaffold. It deliberately separates
emergency/placeholder pages from client-approved standards so a fast recovery
page (like Valkyrie) never becomes accidental brand direction.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .approval import (
    ApprovalState,
    compute_content_model_version,
    compute_style_guide_version,
)

EMDASH_VERSION = "0.23.0"
ASTRO_VERSION = "^7.0.0"


@dataclass(frozen=True)
class SiteModel:
    """Normalized site model consumed by the Astro/EmDash scaffold."""

    slug: str
    business_name: str
    domain: str | None = None
    phone: str | None = None
    address: str | None = None
    tagline: str | None = None
    hero_headline: str | None = None
    hero_body: str | None = None
    primary_cta_label: str = "Call"
    secondary_cta_label: str = "Send a Message"
    primary_cta_href: str | None = None
    secondary_cta_href: str | None = None
    brand_colors: list[str] = field(default_factory=list)
    placeholder_only: bool = False
    source_note: str = "client-approved"


def slugify(value: str) -> str:
    """Return a URL/package safe slug."""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "client-site"


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def build_site_model(profile: dict[str, Any], *, placeholder_only: bool = False) -> SiteModel:
    """Normalize an arbitrary PWP client profile into the site kernel model.

    The normalizer accepts both the current PWP nested shape
    (``{"client_profile": {...}}``) and a flat profile. Emergency pages should
    call this with ``placeholder_only=True`` so downstream deploy/version UI can
    clearly label the result as disposable.
    """
    nested = profile.get("client_profile")
    client: dict[str, Any] = nested if isinstance(nested, dict) else profile
    brand_value = client.get("brand")
    brand: dict[str, Any] = brand_value if isinstance(brand_value, dict) else {}

    name = _first(client.get("name"), client.get("businessName"), client.get("business_name"), "Client Site")
    slug = slugify(_first(client.get("slug"), name))
    phone = _first(client.get("phone"), client.get("smsPhone"), client.get("sms_phone"))
    phone_digits = re.sub(r"\D+", "", phone or "")
    if len(phone_digits) == 10:
        phone_href = "+1" + phone_digits
    elif phone_digits:
        phone_href = "+" + phone_digits
    else:
        phone_href = None

    colors = brand.get("colors") or client.get("brand_colors") or []
    if isinstance(colors, str):
        colors = [colors]

    return SiteModel(
        slug=slug,
        business_name=str(name),
        domain=_first(client.get("domain"), client.get("siteUrl"), client.get("site_url")),
        phone=phone,
        address=_first(client.get("address"), client.get("location")),
        tagline=_first(client.get("tagline"), brand.get("mood"), "Coming soon"),
        hero_headline=_first(client.get("heroHeadline"), client.get("hero_headline"), name),
        hero_body=_first(
            client.get("heroBody"),
            client.get("hero_body"),
            client.get("description"),
            "If you have questions about our programs, feel free to send us a message. We will get back to you as soon as possible.",
        ),
        primary_cta_label="Call " + phone if phone else "Contact Us",
        secondary_cta_label="Send a Message",
        primary_cta_href=f"tel:{phone_href}" if phone_href else "/contact/",
        secondary_cta_href=f"sms:{phone_href}" if phone_href else "/contact/",
        brand_colors=list(colors),
        placeholder_only=placeholder_only,
        source_note="placeholder/emergency" if placeholder_only else "client-approved",
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def render_starter_files(model: SiteModel) -> dict[str, str]:
    """Render a minimal Astro + EmDash starter file tree.

    The emitted project is intentionally small: Astro owns the frontend, EmDash
    is installed/configured as the editable CMS layer, and seed JSON carries
    the current content. The seed includes ``placeholderOnly`` so editors and
    agents know whether to discard it when client direction arrives.
    """
    primary = model.brand_colors[0] if model.brand_colors else "#111827"
    accent = model.brand_colors[1] if len(model.brand_colors) > 1 else "#c6a86b"

    style_guide_dict = {"primary": primary, "accent": accent, "mode": "dark"}
    content_model_dict = {"schema": "page", "fields": ["headline", "body", "primaryCtaLabel", "primaryCtaHref"]}
    style_guide_version = compute_style_guide_version(style_guide_dict)
    content_model_version = compute_content_model_version(content_model_dict)
    package_name = f"pwp-site-{model.slug}"
    site_json = {
        "schemaVersion": 1,
        "source": model.source_note,
        "placeholderOnly": model.placeholder_only,
        "businessName": model.business_name,
        "domain": model.domain,
        "phone": model.phone,
        "address": model.address,
        "tagline": model.tagline,
        "homePage": {
            "eyebrow": "Coming Soon" if model.placeholder_only else model.tagline,
            "headline": model.hero_headline,
            "body": model.hero_body,
            "primaryCtaLabel": model.primary_cta_label,
            "primaryCtaHref": model.primary_cta_href,
            "secondaryCtaLabel": model.secondary_cta_label,
            "secondaryCtaHref": model.secondary_cta_href,
        },
        "theme": {
            "primary": primary,
            "accent": accent,
            "mode": "dark",
        },
        "pwpPolicy": {
            "emergencyPlaceholdersDoNotSetStandards": True,
            "clientApprovedDirectionSupersedesPlaceholder": True,
            "editableStack": "Astro + EmDash",
        },
        "pwpApproval": {
            "version": 1,
            "styleGuideVersion": style_guide_version,
            "contentModelVersion": content_model_version,
            "approvalState": ApprovalState.PENDING.value,
            "requiresApprovalForProduction": True,
            "stagingPreviewUrl": "",
            "rollbackCommand": (
                "PYTHONPATH=src python3 -m prismatic_web_plugin.approval "
                f"rollback ./workspace --style-guide-version {style_guide_version} "
                f"--content-model-version {content_model_version}"
            ),
        },
    }

    return {
        "package.json": _json_dumps(
            {
                "name": package_name,
                "version": "0.1.0",
                "private": True,
                "type": "module",
                "scripts": {
                    "dev": "astro dev",
                    "build": "astro build",
                    "preview": "astro preview",
                    "emdash": "emdash",
                },
                "dependencies": {
                    "@astrojs/cloudflare": "latest",
                    "@emdash-cms/cloudflare": EMDASH_VERSION,
                    "astro": ASTRO_VERSION,
                    "emdash": EMDASH_VERSION,
                },
                "devDependencies": {"wrangler": "latest"},
            }
        ),
        "astro.config.mjs": """import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';
import emdash from 'emdash/astro';
import { d1, kvCache, r2 } from '@emdash-cms/cloudflare';

export default defineConfig({
  output: 'server',
  adapter: cloudflare(),
  integrations: [
    emdash({
      database: d1({ binding: 'DB' }),
      storage: r2({ binding: 'MEDIA' }),
      objectCache: kvCache({ binding: 'CACHE' }),
    }),
  ],
});
""",
        "wrangler.jsonc": _json_dumps(
            {
                "$schema": "node_modules/wrangler/config-schema.json",
                "name": package_name,
                "compatibility_date": "2026-06-26",
                "compatibility_flags": ["nodejs_compat"],
                "d1_databases": [
                    {
                        "binding": "DB",
                        "database_name": f"{model.slug}-emdash",
                        "database_id": "REPLACE_WITH_D1_DATABASE_ID",
                    }
                ],
                "r2_buckets": [
                    {
                        "binding": "MEDIA",
                        "bucket_name": f"{model.slug}-media",
                    }
                ],
                "kv_namespaces": [
                    {
                        "binding": "CACHE",
                        "id": "REPLACE_WITH_KV_NAMESPACE_ID",
                    }
                ],
            }
        ),
        "src/data/site.json": _json_dumps(site_json),
        "pwp-approval.json": _json_dumps(
            {
                "version": 1,
                "client_slug": model.slug,
                "business_name": model.business_name,
                "style_guide_version": style_guide_version,
                "content_model_version": content_model_version,
                "approval_state": ApprovalState.PENDING.value,
                "requires_approval_for_production": True,
                "staging_preview_url": "",
                "deploy_history": "history/deploy_history.json",
                "evidence_dir": "evidence/",
                "rollback_command": (
                    "PYTHONPATH=src python3 -m prismatic_web_plugin.approval rollback "
                    "./workspace "
                    f"--style-guide-version {style_guide_version} "
                    f"--content-model-version {content_model_version}"
                ),
                "linear_issue": "",
                "okf_paths": [
                    "okf/projects/prismatic-web-plugin/decisions/2026-06-26-astro-emdash-pwp-standard.md"
                ],
            }
        ),
        "src/layouts/BaseLayout.astro": """---
const { title, description } = Astro.props;
---
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <meta name="description" content={description} />
  </head>
  <body>
    <slot />
  </body>
</html>
""",
        "src/pages/index.astro": """---
import BaseLayout from '../layouts/BaseLayout.astro';
import site from '../data/site.json';
const home = site.homePage;
---
<BaseLayout title={`${site.businessName} | ${home.eyebrow}`} description={home.body}>
  <main class="page-shell" data-placeholder-only={site.placeholderOnly ? 'true' : 'false'}>
    {site.placeholderOnly && (
      <aside class="notice">Temporary stabilization page. Client-approved direction supersedes this content.</aside>
    )}
    <section class="hero">
      <p class="eyebrow">{home.eyebrow}</p>
      <h1>{home.headline}</h1>
      <p class="lead">{home.body}</p>
      <div class="actions">
        <a class="button primary" href={home.primaryCtaHref}>{home.primaryCtaLabel}</a>
        <a class="button secondary" href={home.secondaryCtaHref}>{home.secondaryCtaLabel}</a>
      </div>
      <dl class="details">
        {site.phone && <><dt>Phone</dt><dd>{site.phone}</dd></>}
        {site.address && <><dt>Address</dt><dd>{site.address}</dd></>}
      </dl>
    </section>
  </main>
</BaseLayout>
<style define:vars={{ primary: site.theme.primary, accent: site.theme.accent }}>
  :global(body) { margin: 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #0c0d0f; color: #fff7ed; }
  .page-shell { min-height: 100vh; display: grid; place-items: center; padding: 2rem; background: radial-gradient(circle at top left, color-mix(in srgb, var(--accent) 22%, transparent), transparent 36%), #0c0d0f; }
  .notice { width: min(900px, 100%); margin-bottom: 1rem; border: 1px solid color-mix(in srgb, var(--accent) 42%, transparent); color: #f9d68a; border-radius: 999px; padding: .75rem 1rem; text-align: center; font-size: .9rem; }
  .hero { width: min(900px, 100%); border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent); border-radius: 2rem; padding: clamp(2rem, 6vw, 5rem); background: rgba(17,24,39,.74); box-shadow: 0 30px 90px rgba(0,0,0,.35); }
  .eyebrow { color: var(--accent); text-transform: uppercase; letter-spacing: .2em; font-weight: 800; }
  h1 { font-family: Georgia, 'Times New Roman', serif; font-size: clamp(2.8rem, 8vw, 6rem); line-height: .9; margin: 0 0 1.5rem; }
  .lead { max-width: 58ch; color: #d6d3d1; font-size: 1.2rem; line-height: 1.7; }
  .actions { display: flex; flex-wrap: wrap; gap: .85rem; margin: 2rem 0; }
  .button { border-radius: 999px; padding: .9rem 1.25rem; font-weight: 800; text-decoration: none; border: 1px solid color-mix(in srgb, var(--accent) 50%, transparent); }
  .primary { background: var(--accent); color: #111; }
  .secondary { color: #fff7ed; }
  .details { display: grid; gap: .5rem; color: #d6d3d1; }
  dt { color: #fff7ed; text-transform: uppercase; letter-spacing: .12em; font-size: .8rem; font-weight: 800; }
  dd { margin: 0 0 1rem; }
</style>
""",
        "emdash.seed.json": _json_dumps(
            {
                "version": 1,
                "siteSettings": site_json,
                "collections": {
                    "pages": [
                        {
                            "slug": "home",
                            "status": "draft" if model.placeholder_only else "published",
                            "title": model.hero_headline,
                            "portableText": [
                                {"_type": "block", "children": [{"_type": "span", "text": model.hero_body}]}
                            ],
                        }
                    ]
                },
            }
        ),
        "README.md": f"""# {model.business_name}

Generated by the Prismatic Web Plugin Astro + EmDash kernel.

## Stack

- Astro
- EmDash `{EMDASH_VERSION}`
- Cloudflare adapter

## Policy

- `placeholderOnly`: `{str(model.placeholder_only).lower()}`
- Emergency/stabilization pages do **not** establish client brand or UX standards.
- Client-approved direction supersedes this generated placeholder as if the placeholder never existed.

## Commands

```bash
npm install
npm run dev
npm run build
npm run emdash -- --help
```

EmDash admin UI is available at `/_emdash/admin` after the CMS runtime is initialized.
""",
    }


def scaffold_astro_emdash_site(
    profile_path: str | Path,
    output_dir: str | Path,
    *,
    placeholder_only: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create an Astro + EmDash site scaffold from a PWP profile JSON file."""
    profile_path = Path(profile_path)
    output_dir = Path(output_dir)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    model = build_site_model(profile, placeholder_only=placeholder_only)
    files = render_starter_files(model)

    written: list[str] = []
    skipped: list[str] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = output_dir / rel
        if path.exists() and not overwrite:
            skipped.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel)

    return {
        "status": "ok",
        "site_slug": model.slug,
        "output_dir": str(output_dir),
        "placeholder_only": model.placeholder_only,
        "written": written,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a PWP Astro + EmDash site")
    parser.add_argument("profile", help="Path to client_profile.json")
    parser.add_argument("--out", required=True, help="Output directory for generated site")
    parser.add_argument("--placeholder-only", action="store_true", help="Mark generated content as disposable emergency placeholder")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files")
    args = parser.parse_args(argv)

    result = scaffold_astro_emdash_site(
        args.profile,
        args.out,
        placeholder_only=args.placeholder_only,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
