# PWP Astro + EmDash Website System

## Decision

All new PWP-managed client websites should be generated as **Astro + EmDash** projects unless a client requirement explicitly calls for another stack.

- **Astro** owns the frontend, routes, components, performance, and deploy target.
- **EmDash** owns editable client content, admin UI, media, menus, site settings, taxonomies, preview/revisions, and agent-friendly structured content.
- **Cloudflare Pages/Workers** remain the default hosting/runtime layer.

## Emergency pages are disposable

Emergency stabilization pages — for example, the temporary Valkyrie Arms Training coming-soon Worker — are **not standards**.

They exist to restore trust quickly when a domain is broken or blank. Once client-approved direction arrives, PWP must treat that new direction as source of truth and set aside emergency styles, layout, imagery, and copy as if the placeholder never existed.

Generated scaffolds must carry this flag when applicable:

```json
{
  "placeholderOnly": true,
  "pwpPolicy": {
    "emergencyPlaceholdersDoNotSetStandards": true,
    "clientApprovedDirectionSupersedesPlaceholder": true,
    "editableStack": "Astro + EmDash"
  }
}
```

## First implementation slice

The initial kernel lives in:

```text
src/prismatic_web_plugin/astro_emdash.py
```

It provides:

- `build_site_model(profile, placeholder_only=...)`
- `render_starter_files(model)`
- `scaffold_astro_emdash_site(profile_path, output_dir, ...)`
- CLI entry via module invocation:

```bash
PYTHONPATH=src python -m prismatic_web_plugin.astro_emdash client_profile.json --out ./site --placeholder-only
```

The scaffold emits:

```text
package.json
astro.config.mjs
src/data/site.json
src/layouts/BaseLayout.astro
src/pages/index.astro
emdash.seed.json
README.md
```

## Verified package contract

As of 2026-06-26:

- NPM package: `emdash`
- Latest verified version: `0.23.0`
- Cloudflare adapter package: `@emdash-cms/cloudflare`
- Astro integration import:

```ts
import emdash from 'emdash/astro';
import { d1, kvCache, r2 } from '@emdash-cms/cloudflare';
```

The generated scaffold pins both `emdash` and `@emdash-cms/cloudflare` to `0.23.0` instead of `latest` so breaking upstream changes are deliberate upgrades. The generated `wrangler.jsonc` includes D1, R2, KV, and `nodejs_compat` placeholders because EmDash on Cloudflare is runtime-backed, not a purely static Astro export.

## Content model v0

The first v0 content model is intentionally small:

```text
siteSettings:
  businessName
  domain
  phone
  address
  tagline
  theme
  pwpPolicy

homePage:
  eyebrow
  headline
  body
  primaryCtaLabel
  primaryCtaHref
  secondaryCtaLabel
  secondaryCtaHref
```

Later PWP phases should expand this into:

```text
programs/classes
instructors/team
FAQs
testimonials
lead magnets
contact forms
menus
blog/articles
media library
```

## Required next step

This kernel currently creates a standards-compliant scaffold. The next durable integration should wire it into the full PWB pipeline:

```text
ingest → synthesize → distill → scaffold Astro+EmDash site → staging deploy → approval → production deploy
```

Do not bypass staging/approval for client-approved work. Emergency stabilization can deploy directly only when the domain is broken and the page is explicitly marked `placeholderOnly`.
