# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** link-rot's promise is "clone
  and run". Pull requests that add a third-party dependency
  will not be merged.
- **No network code. Ever.** The tool's whole trust
  proposition is that it reads text and fetches nothing — no
  "just HEAD-check this one link" feature, no telemetry, no
  update check. The test suite greps the source for network
  APIs and fails on purpose if one appears. Wording that
  upgrades a structural finding into a liveness claim ("this
  link is dead") will not be merged; the honest phrasings
  are "cannot work as written" and "worth a live check".
- **Dead-domain additions need a shutdown source.** A host
  joins the table only with a citable shutdown (the service
  closed, its links stopped resolving) — not because a domain
  looks old or a shortener is unfashionable. Live shorteners
  (bit.ly, tinyurl, t.co) stay off the list.
- **Duplicates stay informational.** A repeated URL across
  videos is normal catalogue behaviour; promoting it to an
  action finding (or to exit 1) changes a stated product
  choice. The conflicting anchor is the rot signal.
- **Buckets and findings are different counts.** Buckets
  count unique normalised links; class counts count
  findings. Output and docs must say which is being quoted.
- **Extraction stays conservative.** New link-shaped prose
  patterns need a test showing the prose that must NOT be
  caught (email addresses, version numbers, file names are
  the standing examples) as well as the link that must.
- **Both directions tested.** A behaviour change needs a
  test where good input succeeds and bad input fails
  cleanly — not just one side. The sample catalogue's counts
  are hand-derived in the test file's header; if you change
  the sample, re-derive them by hand, never copy the tool's
  own output into the expectations.

## Getting started

```bash
git clone https://github.com/jasveerai88/link-rot
cd link-rot
python3 -m unittest discover -s tests -v
python3 src/link_rot.py audit examples/sample-catalogue.json
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if
   the CLI output changes.
