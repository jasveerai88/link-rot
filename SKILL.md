---
name: link-rot
description: Audit a creator's video-description catalogue (JSON list / {"videos": [...]} / CSV export) for link rot — STRUCTURALLY and OFFLINE. Extracts every URL from every description plus each video's links list, and classifies each: malformed (missing/double scheme, space in URL, unbalanced markdown brackets, unsupported scheme, no host), placeholder (example.* hosts, your-link-here paths, bit.ly/xxx, fragment-only), dead-domain (host of a shut-down service — goo.gl, vine.co, periscope.tv, pscp.tv, mixer.com, plus.google.com, blip.tv, stumbleupon.com, bit.do, tr.im), insecure-http, tracking-clutter (utm_* plus ref/tag/aff_id/gclid/fbclid/msclkid/igshid/si params, named in the reason), conflicting-duplicate (same anchor text, different URLs — the stale-link signal), duplicate (same URL in several videos — informational only, never sets exit 1). `audit` gives per-video findings, catalogue findings and the two honest buckets in unique links — cannot_work_as_written vs worth_checking_live vs clean; `links` gives the flat inventory. THE TOOL NEVER FETCHES ANYTHING — there is no network code in it; a finding never means a link was loaded and failed, and a clean audit means every link is well-formed as written, NEVER that it loads. Exit 0 clean, 1 = actionable findings, 2 = clean error ({"error": ...} under --json, argparse included), never a traceback.
---

# link-rot — agent skill

## Purpose

Back-catalogue descriptions carry the affiliate and sponsor
links a channel still earns from — and they rot quietly:
shorteners shut down (goo.gl links stopped resolving in
2025), URLs get pasted double-schemed, placeholders never get
filled in, and the anchor "my training plan" points at v1 in
one video and v2 in another. Paid SaaS (BrokenTube, VIDIK)
and a TubeBuddy Legend feature sell this audit. This tool
does the audit half locally, on the catalogue export the
creator already has, and produces exact per-video findings
plus two honest counts. Applying fixes stays in YouTube
Studio, where the descriptions live.

**The honesty core of this tool:** it never fetches a link.
There is no network code in the source (a test pins that).
So it can say "this link cannot work as written" or "this
link is worth checking live" — never "this link is dead" and
never "this link works". Keep those wordings separate in
anything you report from it.

## When to use / not use

Use when:
- A creator has a description export (yt-dlp JSON, Studio
  CSV, or any JSON/CSV of id/title/description/links) and
  needs to know which links cannot work and which to check.
- A pipeline needs a rot gate before an affiliate push: run
  `audit` on the channel's own catalogue first; exit 1 lists
  exactly which videos to touch.
- You need the flat inventory of every unique link a channel
  publishes (`links`), with occurrences and classes.

Do NOT use when:
- You need liveness. This tool cannot tell you a link 404s.
  For the worth-checking bucket, verify in a browser; never
  upgrade a structural finding into a liveness claim.
- The catalogue is not yet exported. The tool reads files;
  it does not talk to YouTube (no API, no scraping, no
  network at all).
- You want descriptions edited. Audit only, by design — the
  output is the worklist, Studio is where edits happen.

## Commands

```bash
# Full audit: per-video findings + catalogue findings + buckets
python3 src/link_rot.py audit CATALOGUE.json [--json]
python3 src/link_rot.py audit CATALOGUE.csv [--json]

# Flat inventory: unique links, occurrences, videos, classes
python3 src/link_rot.py links CATALOGUE.json [--json]
```

Input (by file extension, `.json` or `.csv`):
- JSON: a list of videos, or `{"videos": [...]}`. Each video
  is an object: `id` (optional string), `title` (optional
  string), `description` (string), `links` (optional list of
  URL strings or `{"url", "text"|"anchor"|"label"}` objects).
  A video needs `description` or `links` (both are combined,
  links-list entries after the description's own links). A
  video's ref is its `id`, else `title`, else its position.
- CSV: header row, one video per row; columns matched
  case-insensitively among `id`, `title`, `description`,
  `links`; a links cell splits on spaces, semicolons, pipes.
  `description` or `links` must be a column; ragged rows are
  an error naming the row.

Extraction, in order: markdown links and images (anchor =
the bracket text / alt text; a quoted title after the URL is
allowed; `<url>` targets are allowed), then broken markdown
(a `](` that never closes — one malformed finding, its
would-be target consumed so its pieces are not re-read as
links), then bare tokens. A bare token counts as a link when
it carries a scheme, starts `www.`, is a dotted host with a
path, or is a host the classification tables know. Prose
that is not a link — email addresses, version numbers, bare
file names — is left alone.

## Classification (exact)

Per link, from its own shape (a link can carry several):
- `malformed` (severity `cannot-work`): any whitespace in the
  URL; no scheme; a second scheme after the first
  (`https://https://…`); a scheme outside http/https/mailto/
  tel; http(s) with no host or unparseable; a mailto: with no
  `@`; a tel: with no digits; an empty markdown target; an
  unclosed markdown link.
- `placeholder` (`cannot-work`): host in {example.com,
  example.org, example.net, yourdomain.com, your-domain.com,
  your-site.com, yoursite.com, yourwebsite.com}; a path
  segment in {xxx, xxxx, your-link, your-link-here, yourlink,
  insert-link, insert-link-here, placeholder} or containing
  `your-link-here` / `insert-link`; a fragment-only URL
  (`#...`).
- `dead-domain` (`cannot-work`): host in the shutdown table
  (goo.gl, bit.do, tr.im, vine.co, periscope.tv, pscp.tv,
  mixer.com, plus.google.com, blip.tv, stumbleupon.com). The
  reason names the service and its shutdown. It is a
  *pattern* — phrase it as expired-domain risk, never as a
  fetch result.
- `insecure-http` (`check`): scheme is http.
- `tracking-clutter` (`check`): query carries any `utm_*`
  key or one of ref, ref_src, tag, aff, aff_id, affiliate_id,
  gclid, fbclid, msclkid, igshid, si. The reason lists the
  parameter names found, sorted.

Across the catalogue:
- `conflicting-duplicate` (`check`): one normalised anchor
  (casefolded, whitespace-collapsed) with 2+ distinct
  normalised target URLs. Only real anchors participate —
  markdown/link-list text that is not the URL itself. Both
  (all) target URLs carry the class in the `links` inventory.
- `duplicate` (`info`): one normalised URL in 2+ videos.
  Normalisation: scheme/host lowercased, one trailing path
  slash removed, fragment dropped, query kept verbatim.

Buckets count UNIQUE (normalised) links: a link with any
cannot-work class is in `cannot_work_as_written`; else a
link with any check class is in `worth_checking_live`; else
`clean_links` (plain duplicates land here — the class is a
note, not a defect). The three sum to `unique_links`.

## Output JSON schema (`--json`)

Common: `tool` (`"link-rot"`), `version`, `command`,
`catalogue_file` (file name), `scope` (the structural-only
statement), `summary` — `{videos, link_occurrences,
unique_links, findings_by_class, cannot_work_as_written,
worth_checking_live, clean_links}`. `findings_by_class`
counts FINDINGS (a conflict counts once; a link with two
classes counts in both), only non-zero classes, in class
order.

`audit` adds `videos` — each `{ref, title, link_count,
findings}` where a finding is `{class, severity, url,
reason, anchor?}` — and `catalogue_findings`, each either
`{class: "conflicting-duplicate", severity, anchor,
targets: [{url, video, normalized}], reason}` or
`{class: "duplicate", severity: "info", url, occurrences,
videos, reason}`.

`links` adds `links` — each `{url (first-seen form),
normalized, domain, occurrences, videos (refs, first-seen
order), classes (sorted)}`, sorted by occurrences desc then
URL.

On error, stdout is a single object: `{"error": "<message>"}`
with exit code 2 — including argparse usage errors in
`--json` mode. Never plain text, never a traceback.

## Exit codes

- `0` — clean: no cannot-work and no live-check findings.
  Plain duplicates may still be listed; they are notes.
- `1` — findings that need action: anything in the
  cannot-work or live-check buckets. The findings ARE the
  deliverable — quote them, don't summarise them away.
- `2` — ERROR: catalogue missing, unreadable, not valid
  JSON/CSV, wrong shape (entry not an object, a field of the
  wrong type, a video with neither description nor links, a
  CSV missing its link columns or with a ragged row), an
  empty catalogue, an unknown file extension, an invalid
  flag. No audit facts may be quoted from a failed run.

## Limits & honesty rules the agent must respect

- **Structural, never live.** Never report a finding as
  "this link is dead/broken online" — say "cannot work as
  written" for the cannot-work bucket and "worth checking
  live" for the check bucket, exactly as the tool does.
  Never report a clean audit as "all links work" — it means
  "all links are well-formed as written".
- **Dead-domain is a pattern, not a probe.** The host's
  service shut down; the tool did not visit the link. Keep
  the word "risk" attached.
- **Duplicates are not rot.** A plain duplicate is
  informational and does not set exit 1. Do not present the
  duplicate count as a problem count; the conflicting
  anchor is the rot signal in that family.
- **Buckets are unique links; class counts are findings.**
  Do not mix the two in one sentence without saying which
  you are quoting.
- **Exit 2 means no audit happened.** Do not reconstruct
  findings by reading the catalogue yourself and presenting
  them as the tool's — fix the input and re-run.
- Local only: the tool reads only the catalogue file named
  on the command line and sends nothing anywhere.
