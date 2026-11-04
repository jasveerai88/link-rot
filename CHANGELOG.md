# Changelog

## v0.1.0 — 2026-11-04

First release.

- **Audit a whole description catalogue for link rot —
  structurally, offline.** Input is the export a creator
  already has: JSON (a list of videos, or `{"videos": [...]}`
  — the yt-dlp / Studio shape) or CSV (header row, one video
  per row; `id` / `title` / `description` / `links` columns).
  Every URL in every description, plus each video's `links`
  list, is extracted and classified. There is **no network
  code in the tool** — it never fetches a link and never
  claims one is dead.
- **`audit CATALOGUE`** — per-video findings with exact
  reasons, catalogue-wide findings, counts by class, and the
  two honest buckets in unique links: *cannot work as
  written* vs *worth a live check* vs clean. Exit 0 = clean,
  1 = actionable findings, 2 = error.
- **`links CATALOGUE`** — the flat inventory: every unique
  link with its occurrence count, the videos it appears in,
  and the classes it carries.
- **The classes** — `malformed` (missing scheme, double
  scheme, a space in the URL, unbalanced markdown brackets,
  unsupported scheme, no host), `placeholder` (example.*
  hosts, `your-link-here` paths, `bit.ly/xxx`, fragment-only
  links), `dead-domain` (hosts of shut-down services: goo.gl,
  Vine, Periscope, Mixer, Google+, Blip, StumbleUpon, bit.do,
  tr.im — an expired-domain risk pattern, never a probe
  result), `insecure-http`, `tracking-clutter` (`utm_*` plus
  affiliate-tag parameters, each named in the reason), and
  across the catalogue: `conflicting-duplicate` (one anchor
  text, several target URLs — the stale-link signal) and
  `duplicate` (one URL in several videos — informational
  only; it never sets exit 1).
- **Extraction with judgement** — markdown links and images,
  quoted titles and `<url>` targets, broken markdown consumed
  as one finding instead of spraying phantom links, bare
  URLs trimmed of prose punctuation — and prose that is not
  a link (email addresses, version numbers, file names) is
  left alone. Unicode domains and very long URLs are reported
  as-is.
- **Honesty rules, enforced in wording everywhere** — a
  finding means "cannot work as written" or "worth checking
  live", never "was loaded and failed"; a clean audit means
  "well-formed as written", never "loads". Buckets count
  unique links; class counts count findings; the two are
  never silently mixed.
- **`--json` on every command** — one JSON object with the
  same facts and exit codes as the text view; errors are
  `{"error": ...}` objects, argparse usage errors included.
- **`SKILL.md`** at the repo root for AI coding agents:
  commands, the JSON schemas, exit codes, and the honesty
  rules (structural never live; duplicates are not rot;
  buckets vs findings).
- Bundled sample catalogue (`examples/sample-catalogue.json`):
  six fictional videos, 14 link occurrences over 13 unique
  links, exactly one planted finding per class — the counts
  are hand-checkable (buckets 3 / 4 / 6).
- 60 stdlib-unittest tests: the sample's hand-counted
  numbers, every class in both directions, the extraction
  edges, the prose-that-is-not-a-link cases, the CSV path
  and its malformed forms, every input error exiting 2
  cleanly, and a guard test that fails if network code ever
  enters the source.
- Pure Python standard library; local only; MIT licence.
