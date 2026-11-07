> **Merged into [Faceless QC Lite](https://github.com/jasveerai88/faceless-qc-lite)** — as of v2.0.0 this tool ships inside the Faceless QC Lite pre-upload suite: same checks, byte-identical engine, plus one combined `suite` run across all six checks. This repo stays public for existing links; development continues there. Install the suite: `pipx install faceless-qc-lite`

# link-rot

**Your old videos are still selling. Some of their links
aren't.**

Affiliate and sponsor links in a back catalogue quietly rot:
shorteners shut down, links get pasted in twice-schemed, a
placeholder never gets filled in, the same "my plan" anchor
points at last year's version in one video and this year's in
another. Paid tools sell the fix on a striking claim — the
average channel has ~23% of its affiliate links broken,
silently losing commissions every day (BrokenTube); VIDIK
sells the same job; TubeBuddy locks bulk find/replace behind
its Legend tier.

`link-rot` is the audit half of that job, locally and free.
Feed it the catalogue export you already have (JSON or CSV),
and it extracts every URL in every description, classifies
each one by what is wrong with it **as written**, and hands
you the per-video findings and the two numbers that matter:
how many links **cannot work as written**, and how many are
**worth a live check**.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — and stronger: **there is no network code in
  this tool at all.** It never fetches a link, so it never
  claims one is dead. It classifies *shape*, and says so.
- Script-friendly exit codes: `0` = clean, `1` = findings
  that need action, `2` = error

## What it flags

| Class | Severity | Meaning |
|---|---|---|
| `malformed` | cannot work | missing scheme, double scheme, a space in the URL, unbalanced markdown brackets, an unsupported scheme, no host |
| `placeholder` | cannot work | `example.com` and friends, `your-link-here` paths, `bit.ly/xxx`, a fragment-only `#` — never filled in |
| `dead-domain` | cannot work | the host belongs to a service that has shut down (`goo.gl`, Vine, Periscope, Mixer…) — an expired-domain risk pattern |
| `conflicting-duplicate` | live check | the same anchor text points at different URLs across the catalogue — one of them is stale |
| `insecure-http` | live check | scheme is `http`, not `https` |
| `tracking-clutter` | live check | `utm_*` and affiliate-tag parameters (`tag`, `ref`, `gclid`…) — clutter, not rot, but an affiliate `tag` pays whoever it names |
| `duplicate` | informational | the same URL in several videos — fine on its own; only a problem if the target changes. Listed, but it does **not** set exit 1 |

Two honest buckets, counted in unique links: **cannot work
as written** (malformed + placeholder + dead-domain) and
**worth a live check** (conflicting anchors, http links,
tracked links). Everything else is an ordinary duplicate note
or a clean link. The tool never merges the buckets — a link
that *might* be dead is not reported as a link that *cannot
work*.

## The catalogue

JSON — a list of videos, or `{"videos": [...]}` (the shape
yt-dlp and Studio exports already use):

```json
[
  {"id": "desk-setup-2024", "title": "My Desk Setup Tour",
   "description": "Keyboard I type on: https://keyshop.io/k87-pro"},
  {"id": "camera-gear-2025", "title": "Camera Gear I Actually Use",
   "description": "My main camera body: http://camerastore.ca/a7iv-body",
   "links": [{"url": "https://camerastore.ca/24-70-gm", "text": "The lens"}]}
]
```

Each video needs a `description` and/or a `links` list (URL
strings, or `{"url", "text"}` objects). A video is referred
to by its `id`, else its `title`, else its position.

CSV — a header row, one video per row; columns matched
case-insensitively: `id`, `title`, `description`, `links`
(a links cell holds URLs separated by spaces, semicolons or
pipes). Malformed input of either kind is a clean exit-2
error naming the entry and the field — never a traceback.

## Usage

```bash
# 1. Audit the whole catalogue
python3 src/link_rot.py audit examples/sample-catalogue.json

# 2. The flat inventory: every unique link, its videos, its classes
python3 src/link_rot.py links examples/sample-catalogue.json

# 3. Drive it from a script: exit 1 means findings need action
python3 src/link_rot.py audit catalogue.csv || echo "rot found"
```

Then fix the flagged descriptions where they live (YouTube
Studio), oldest videos first — they have had the longest to
rot, and they are still being watched.

## Use with AI agents

Every command takes `--json`: one JSON object with the same
facts and exit codes as the text view (errors come back as
`{"error": ...}`, argparse usage errors included):

```bash
python3 src/link_rot.py audit examples/sample-catalogue.json --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the full
JSON schemas, the exit codes, and the honesty rules (a
finding is structural, never a liveness result; a clean
audit means well-formed, never "loads").

## Real run (verbatim)

The bundled sample is a six-video fictional catalogue with
exactly one planted finding per class. The audit:

```text
$ python3 src/link_rot.py audit examples/sample-catalogue.json
link-rot v0.1.0 — audit · catalogue sample-catalogue.json
6 video(s) · 14 link occurrence(s) · 13 unique link(s)
Structural audit only: this tool reads text and never fetches a link.
A finding means the link cannot work as written, or is worth a live
check — never that it was loaded and failed.

Findings by class (findings, not links):
  malformed: 1
  placeholder: 1
  dead-domain: 1
  conflicting-duplicate: 1
  insecure-http: 1
  tracking-clutter: 1
  duplicate: 1 (informational)

Cannot work as written: 3 unique link(s)
Worth a live check: 4 unique link(s)
Clean: 6 unique link(s)

Per video:
  [desk-setup-2024] My Desk Setup Tour
    3 link(s) · no findings
  [camera-gear-2025] Camera Gear I Actually Use
    ! insecure-http — http://camerastore.ca/a7iv-body — scheme is http, not https — most browsers warn or upgrade, and some embeds refuse it
  [trail-kit] Trail Running Kit List
    ! tracking-clutter — https://runshop.ca/speedgoat?utm_source=youtube&utm_medium=description&ref=trailcast — carries tracking parameter(s): ref, utm_medium, utm_source — clutter, not rot, but worth stripping; an affiliate 'tag' pays whoever it names
  [favourites-2019] My 2019 Favourites
    ! dead-domain — https://goo.gl/faves2019 — host goo.gl belongs to a service that has shut down (Google URL Shortener — Google shut it down and its links stopped resolving in August 2025) — an expired-domain risk pattern; replace it with a live target
  [sponsor-haul] Sponsored Gear Haul
    ! malformed — https://https://brightgear.co/landing — double scheme — the URL carries two schemes (a paste of a full URL into a field that added its own)
  [training-update] Training Plan — Spring Update
    ! placeholder — https://example.com/affiliate-link — host example.com is a documentation placeholder — the real link was never filled in

Across the catalogue:
  ! conflicting-duplicate — anchor 'My training plan' points at 2 different URLs:
      https://plans.mayachen.ca/plan-v1 — in [sponsor-haul]
      https://plans.mayachen.ca/plan-v2 — in [training-update]
  · duplicate — https://keyshop.io/k87-pro appears in 2 video(s): [desk-setup-2024], [training-update] — fine on its own; only a problem if the target changes
(exit code: 1)
```

The flat inventory of the same catalogue:

```text
$ python3 src/link_rot.py links examples/sample-catalogue.json
link-rot v0.1.0 — links · catalogue sample-catalogue.json
13 unique link(s) · 14 occurrence(s)

  2× https://keyshop.io/k87-pro — in [desk-setup-2024], [training-update] · duplicate
  1× http://camerastore.ca/a7iv-body — in [camera-gear-2025] · insecure-http
  1× https://blog.mayachen.ca/favourites-2019 — in [favourites-2019]
  1× https://camerastore.ca/24-70-gm — in [camera-gear-2025]
  1× https://deskhaus.ca/apex-desk — in [desk-setup-2024]
  1× https://example.com/affiliate-link — in [training-update] · placeholder
  1× https://goo.gl/faves2019 — in [favourites-2019] · dead-domain
  1× https://https://brightgear.co/landing — in [sponsor-haul] · malformed
  1× https://plans.mayachen.ca/plan-v1 — in [sponsor-haul] · conflicting-duplicate
  1× https://plans.mayachen.ca/plan-v2 — in [training-update] · conflicting-duplicate
  1× https://runshop.ca/merino-wool-socks — in [trail-kit]
  1× https://runshop.ca/speedgoat?utm_source=youtube&utm_medium=description&ref=trailcast — in [trail-kit] · tracking-clutter
  1× https://youtu.be/abc123XYZ0 — in [desk-setup-2024]
(exit code: 1)
```

A clean catalogue exits 0, and says so without inventing
findings:

```text
$ python3 src/link_rot.py audit clean.json
link-rot v0.1.0 — audit · catalogue clean.json
1 video(s) · 2 link occurrence(s) · 2 unique link(s)
Structural audit only: this tool reads text and never fetches a link.
A finding means the link cannot work as written, or is worth a live
check — never that it was loaded and failed.

Findings: none

Cannot work as written: 0 unique link(s)
Worth a live check: 0 unique link(s)
Clean: 2 unique link(s)

Per video:
  [launch-video] Launch Day
    2 link(s) · no findings
(exit code: 0)
```

And a broken catalogue file is a clean error, never a
traceback:

```text
$ python3 src/link_rot.py audit bad.json
ERROR: catalogue file 'bad.json' is not valid JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
(exit code: 2)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 60 tests — OK
```

The suite pins the sample's hand-counted numbers (14
occurrences, 13 unique links, one finding per class, buckets
3 / 4 / 6); every class on its own in both directions; the
extraction edges (markdown links and images, quoted titles,
angle-bracket targets, prose punctuation, unbalanced
brackets, a space in a target); the prose that is *not* a
link (an email address, a version number, a file name);
unicode domains and 3,000-character URLs without a crash;
the CSV path including its malformed forms; every input
error exiting 2 cleanly as `{"error": ...}` under `--json`;
and a guard test that fails if network code ever enters the
source.

## Dual use

- **For creators (the Sponsors surface):** the audit half of
  a paid link-rot SaaS, run locally on an export you already
  have — no account, no OAuth into your channel, no per-video
  caps.
- **For its author:** the first real run is on the author's
  own channels — 170+ published video descriptions carrying
  sponsor and affiliate links — before any affiliate push, so
  the catalogue that earns is the catalogue that gets fixed
  first.

## Known limits

- **Structural, never live.** The tool reads text. It cannot
  know that a well-formed link 404s today, and it never
  claims to: `dead-domain` is a *pattern* (a host whose
  service shut down), the live-check bucket is explicitly a
  list of things to check live, and a clean audit means
  "well-formed as written", never "loads". If you need
  liveness, check the flagged links in a browser — there
  will be far fewer of them than the whole catalogue.
- **The dead-domain list is a list.** It covers the big
  shutdowns (Google's shortener, Vine, Periscope, Mixer,
  Google+, Blip, StumbleUpon, two dead shorteners). A domain
  that died quietly last year is not on it — that is what the
  live check is for.
- **Extraction is conservative.** A bare link is recognised
  by its scheme, a `www.` prefix, a dotted host with a path,
  or a host the tool knows. A scheme-less bare domain with no
  path (`shop.ca` alone in prose) is left alone rather than
  guessed at — and an email address is never mistaken for a
  link.
- **Audit only, by design.** The tool does not edit
  descriptions (they live in YouTube Studio, behind your
  login) and does not apply a find-and-replace plan. It tells
  you exactly which videos and which links to touch.
- **One catalogue file.** A folder of per-video `.info.json`
  files (yt-dlp's other common dump shape) needs merging
  into one list first — one line with `jq`:
  `jq -s '[.[] | {id, title, description}]' *.info.json > catalogue.json`.

## Privacy

What it touches: only the catalogue file you point it at.
What it sends: nothing — there is no network code in this
tool. Your descriptions, your affiliate tags and your video
list never leave the machine.

## Support

If this finds rot in a catalogue that earns for you, consider
sponsoring: **https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
