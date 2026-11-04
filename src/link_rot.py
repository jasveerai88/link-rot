#!/usr/bin/env python3
"""link-rot — audit a creator's video-description catalogue for
link rot, structurally, offline. It reads a catalogue of video
descriptions (the export a creator already has: JSON or CSV),
extracts every URL in every description, and classifies each
one by what is wrong with it AS WRITTEN:

  cannot work as written
    malformed             missing scheme, double scheme, a space
                          in the URL, unbalanced markdown
                          brackets, an unsupported scheme, no
                          host — the link is broken on its face
    placeholder           example.com and friends, your-link-
                          here paths, a bare "#" — the link was
                          never filled in
    dead-domain           the host belongs to a service that
                          has shut down (goo.gl, Vine, Periscope
                          and kin) — an expired-domain risk: it
                          cannot be trusted to resolve
  worth a live check
    conflicting-duplicate the same anchor text points at two
                          or more different URLs across the
                          catalogue — one of them is stale
    insecure-http         scheme is http, not https
    tracking-clutter      utm_* and affiliate-tag parameters —
                          clutter, not rot; the link may still
                          work, but it is carrying junk
  informational
    duplicate             the same URL in several videos —
                          fine on its own; only a problem if
                          the target ever changes

Two paid SaaS tools (BrokenTube, VIDIK) and a TubeBuddy Legend
feature sell this job, on the claim that the average channel
has ~23% of its affiliate links broken. This is the audit half
of that job, locally and free: the find and the classify. It
produces the counts and the per-video findings; fixing the
descriptions stays with the creator, in YouTube Studio, where
the descriptions live.

The honesty core: THIS TOOL NEVER FETCHES ANYTHING. There is
no network code in it at all. A finding never means "this link
was loaded and failed" — it means "as written, this link
cannot work" or "this link is worth checking live". A clean
audit means every link is well-formed as written, never that
every link loads. Liveness is a network question this tool
deliberately never asks.

Catalogue input — JSON or CSV (chosen by file extension):

  JSON: a list of videos, or {"videos": [...]} (yt-dlp /
  Studio dumps are this shape). Each video is an object:
    id           optional string
    title        optional string
    description  the description text (string)
    links        optional list: URL strings, or objects
                 {"url": ..., "text"/"anchor"/"label": ...}
  A video needs "description" or "links" (or both; links-list
  entries are audited after the description's own links).
  A video is referred to by its id, else its title, else its
  position ("videos[2]").

  CSV: a header row, then one video per row. Columns are
  matched case-insensitively: id, title, description, links
  (a links cell holds one or more URLs separated by spaces,
  semicolons or pipes). "description" or "links" must be one
  of the columns.

Commands:
  audit CATALOGUE [--json]
            per-video findings, catalogue-wide findings
            (conflicting anchors, plain duplicates), counts
            by class, and the two honest buckets: how many
            unique links cannot work as written, and how many
            are worth a live check.
  links CATALOGUE [--json]
            the flat inventory: every unique link, how many
            times it appears, in which videos, and which
            classes it carries.

Exit codes: 0 = clean (plain duplicates may still be listed —
they are informational) · 1 = findings that need action
(anything in the cannot-work or live-check buckets) · 2 =
ERROR — clean message, never a traceback; with --json the
error is {"error": ...}. Every command takes --json: one JSON
object with the same facts and exit codes as the text view.
"""
import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

__version__ = "0.1.0"
TOOL = "link-rot"

SCOPE_NOTE = ("structural audit only — no link was fetched; a "
              "clean result means every link is well-formed as "
              "written, never that it loads")

# ---------------------------------------------------------------------------
# classification tables
# ---------------------------------------------------------------------------

# Hosts belonging to services that have shut down. A link to
# one of these is an expired-domain risk: it cannot be trusted
# to resolve, and the audit says why, per host. This is a
# pattern list, not a liveness result — the tool never fetches.
DEAD_DOMAINS = {
    "goo.gl": "Google URL Shortener — Google shut it down and "
              "its links stopped resolving in August 2025",
    "bit.do": "bit.do shortener — the service was discontinued",
    "tr.im": "tr.im shortener — the service shut down",
    "vine.co": "Vine — shut down in 2017",
    "periscope.tv": "Periscope — shut down in 2021",
    "pscp.tv": "Periscope — shut down in 2021",
    "mixer.com": "Mixer — shut down in 2020",
    "plus.google.com": "Google+ — shut down in 2019",
    "blip.tv": "Blip — shut down in 2015",
    "stumbleupon.com": "StumbleUpon — shut down in 2018",
}

# Hosts that exist to be placeholders in documentation and
# templates. A description still pointing at one was never
# filled in.
PLACEHOLDER_HOSTS = {
    "example.com", "example.org", "example.net",
    "yourdomain.com", "your-domain.com", "your-site.com",
    "yoursite.com", "yourwebsite.com",
}

# Path segments / shortener codes that mark a link as a
# template placeholder rather than a real target.
PLACEHOLDER_TOKENS = {
    "xxx", "xxxx", "your-link", "your-link-here", "yourlink",
    "insert-link", "insert-link-here", "placeholder",
}

# Query parameters that are tracking or affiliate-tag clutter:
# they do not break a link, but the link is carrying junk —
# and an affiliate "tag" is worth eyeballing, because the
# wrong tag pays the wrong account.
TRACKING_PARAMS = {
    "ref", "ref_src", "tag", "aff", "aff_id", "affiliate_id",
    "gclid", "fbclid", "msclkid", "igshid", "si",
}

SEVERITY = {
    "malformed": "cannot-work",
    "placeholder": "cannot-work",
    "dead-domain": "cannot-work",
    "conflicting-duplicate": "check",
    "insecure-http": "check",
    "tracking-clutter": "check",
    "duplicate": "info",
}

CLASS_ORDER = [
    "malformed", "placeholder", "dead-domain",
    "conflicting-duplicate", "insecure-http", "tracking-clutter",
    "duplicate",
]

_KNOWN_LINK_HOSTS = set(DEAD_DOMAINS) | PLACEHOLDER_HOSTS


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# ---------------------------------------------------------------------------
# catalogue loading
# ---------------------------------------------------------------------------

def _video_ref(entry, index, origin):
    vid = entry.get("id")
    if isinstance(vid, str) and vid.strip():
        return vid.strip()
    title = entry.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return f"{origin}[{index}]"


def _clean_video(entry, index, origin):
    """One raw catalogue entry -> a video dict with a ref, a
    title and a list of (url, anchor) pairs from its links
    list. Hard problems raise ToolError naming the entry."""
    label = f"{origin}[{index}]"
    if not isinstance(entry, dict):
        raise ToolError(f"{label}: each video must be an object "
                        f"(got {entry!r})")
    for field in ("id", "title"):
        value = entry.get(field)
        if value is not None and not isinstance(value, str):
            raise ToolError(f"{label}: field {field!r} must be a "
                            f"string (got {value!r})")
    description = entry.get("description")
    if description is not None and not isinstance(description, str):
        raise ToolError(f"{label}: field 'description' must be a "
                        f"string (got {description!r})")
    links_raw = entry.get("links")
    links = []
    if links_raw is not None:
        if not isinstance(links_raw, list):
            raise ToolError(f"{label}: field 'links' must be a "
                            f"list (got {links_raw!r})")
        for j, item in enumerate(links_raw):
            if isinstance(item, str):
                links.append((item, None))
            elif isinstance(item, dict):
                url = item.get("url")
                if not isinstance(url, str) or not url.strip():
                    raise ToolError(
                        f"{label}: links[{j}] needs a non-empty "
                        f"'url' string (got {item!r})")
                anchor = None
                for key in ("text", "anchor", "label"):
                    if isinstance(item.get(key), str) \
                            and item[key].strip():
                        anchor = item[key]
                        break
                links.append((url, anchor))
            else:
                raise ToolError(
                    f"{label}: links[{j}] must be a URL string "
                    f"or an object with a 'url' (got {item!r})")
    if description is None and not links:
        raise ToolError(f"{label}: a video needs a 'description' "
                        f"or a 'links' list — it has neither")
    return {
        "ref": _video_ref(entry, index, origin),
        "title": entry.get("title") or "",
        "description": description or "",
        "links": links,
    }


def _load_json(raw, name):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"catalogue file {name!r} is not valid "
                        f"JSON: {exc}")
    if isinstance(data, dict):
        if "videos" not in data:
            raise ToolError(
                f"catalogue file {name!r}: a JSON object must "
                f"carry its videos under a 'videos' key")
        data = data["videos"]
    if not isinstance(data, list):
        raise ToolError(
            f"catalogue file {name!r}: top level must be a list "
            f"of videos or an object with a 'videos' list (got "
            f"{type(data).__name__})")
    return [_clean_video(e, i, "videos") for i, e in enumerate(data)]


def _load_csv(raw, name):
    try:
        rows = list(csv.reader(io.StringIO(raw), strict=True))
    except csv.Error as exc:
        raise ToolError(f"catalogue file {name!r} is not valid "
                        f"CSV: {exc}")
    if not rows:
        raise ToolError(f"catalogue file {name!r}: the CSV has "
                        f"no header row")
    header = [h.strip().lower() for h in rows[0]]
    if "description" not in header and "links" not in header:
        raise ToolError(
            f"catalogue file {name!r}: the CSV needs a "
            f"'description' or 'links' column (header is: "
            f"{', '.join(rows[0])})")
    videos = []
    for i, row in enumerate(rows[1:]):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) != len(header):
            raise ToolError(
                f"catalogue file {name!r}: row {i + 2} has "
                f"{len(row)} field(s), the header has "
                f"{len(header)}")
        entry = dict(zip(header, row))
        if isinstance(entry.get("links"), str):
            cell = entry["links"]
            entry["links"] = [t for t in
                               re.split(r"[\s;|]+", cell.strip())
                               if t]
        videos.append(_clean_video(entry, i, "row"))
    return videos


def load_catalogue(path):
    """Read a catalogue file (JSON or CSV by extension) ->
    a list of video dicts. Raises ToolError on any problem."""
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    if suffix not in (".json", ".csv"):
        raise ToolError(
            f"catalogue file {name!r}: link-rot reads .json or "
            f".csv catalogues (got extension {suffix!r})")
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ToolError(f"cannot read catalogue file "
                        f"{path!r}: {exc}")
    except UnicodeDecodeError as exc:
        raise ToolError(f"catalogue file {name!r} is not valid "
                        f"UTF-8 text: {exc}")
    if suffix == ".json":
        videos = _load_json(raw, name)
    else:
        videos = _load_csv(raw, name)
    if not videos:
        raise ToolError(f"catalogue file {name!r} contains no "
                        f"videos — nothing to audit")
    return videos


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)]*)\)")
_TOKEN_RE = re.compile(r"[^\s<>\"'\[\]{}|]+")
_DOMAIN_TOKEN_RE = re.compile(
    r"^(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    r"(?::[0-9]+)?(?:/[^\s]*)?$")
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")


def _md_target(raw_target):
    """The inside of a markdown link's (...) -> (url, problem).
    Handles the <url> form and an optional quoted title; a
    target with a space anywhere else is a malformed link."""
    target = raw_target.strip()
    if not target:
        return "", "the markdown link target is empty"
    if target.startswith("<"):
        end = target.find(">")
        if end > 0:
            return target[1:end], None
    if any(ch.isspace() for ch in target):
        first, _, rest = target.partition(" ")
        rest = rest.strip()
        if rest.startswith(('"', "'")) and rest.endswith(rest[0]) \
                and len(rest) >= 2:
            return first, None
        return target, "the URL contains a space"
    return target, None


def _looks_like_link(token):
    """Is this bare token in prose a link (vs a word, a version
    number, an email address, a file name)? Conservative: it
    needs a scheme, a www. prefix, a path after a dotted host,
    or a host this tool knows about."""
    if _SCHEME_RE.match(token):
        return True
    if token.startswith("//"):
        return True
    if not _DOMAIN_TOKEN_RE.match(token):
        return False
    host = token.split("/", 1)[0].split(":", 1)[0].lower()
    if token.lower().startswith("www."):
        return True
    if "/" in token:
        return True
    return host in _KNOWN_LINK_HOSTS


def _trim_token(token):
    """Strip prose punctuation glued to a bare URL token."""
    while token.startswith("("):
        token = token[1:]
    while token and token[-1] in ".,;:!?":
        token = token[:-1]
    while token.endswith(")") and token.count("(") < token.count(")"):
        token = token[:-1]
    while token.endswith("]") and token.count("[") < token.count("]"):
        token = token[:-1]
    return token


def extract_occurrences(video):
    """One video -> a list of occurrence dicts in the order the
    links appear: {url, anchor, position, forced} where forced
    is a (class, reason) the extraction itself already knows
    (a space in the target, unbalanced brackets) or None."""
    text = video["description"]
    occurrences = []

    def _md_sub(match):
        anchor = match.group(2).strip() or None
        url, problem = _md_target(match.group(3))
        forced = ("malformed", problem) if problem else None
        occurrences.append({
            "url": url, "anchor": anchor,
            "position": match.start(), "forced": forced})
        return ""

    work = _MD_LINK_RE.sub(_md_sub, text)

    # Leftovers: a "](" the well-formed pass could not close.
    # Each one's would-be target runs to the next "](", the end
    # of the line, or the end of the text — and is consumed, so
    # the bare-token scan never re-reads its pieces as links.
    def _leftover_scan(s):
        out = []
        i = 0
        while True:
            j = s.find("](", i)
            if j < 0:
                out.append(s[i:])
                return "".join(out)
            out.append(s[i:j])
            start = j + 2
            end = len(s)
            for marker in ("](", "\n"):
                nxt = s.find(marker, start)
                if nxt >= 0:
                    end = min(end, nxt)
            raw = s[start:end].strip()
            if not raw:
                url, problem = "(no target)", (
                    "unbalanced brackets: a markdown link opens "
                    "with '](' but never closes and names no "
                    "target")
            elif any(ch.isspace() for ch in raw):
                url = raw.split(None, 1)[0]
                problem = ("unbalanced brackets: a markdown "
                           "link opens with '](' but never "
                           "closes, and the would-be target "
                           "contains a space")
            else:
                url = raw
                problem = ("unbalanced brackets: a markdown "
                           "link opens with '](' but never "
                           "closes")
            occurrences.append({
                "url": url, "anchor": None, "position": j,
                "forced": ("malformed", problem)})
            i = end

    work = _leftover_scan(work)

    for match in _TOKEN_RE.finditer(work):
        token = _trim_token(match.group(0))
        if token and _looks_like_link(token):
            occurrences.append({
                "url": token, "anchor": None,
                "position": match.start(), "forced": None})

    base = len(text) + 1
    for j, (url, anchor) in enumerate(video["links"]):
        occurrences.append({
            "url": url, "anchor": anchor,
            "position": base + j, "forced": None})

    occurrences.sort(key=lambda o: o["position"])
    return occurrences


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def normalize_url(url):
    """Canonical form for duplicate comparison: scheme and host
    lowercased, one trailing path slash removed, fragment
    dropped. Anything unparsable normalises to its lowercased
    raw form, so identical breakage still groups together."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return url.lower()
    scheme = (parts.scheme or "").lower()
    if not scheme or not host:
        return url.lower()
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    out = f"{scheme}://{host}"
    try:
        if parts.port:
            out += f":{parts.port}"
    except ValueError:
        pass
    out += path
    if parts.query:
        out += f"?{parts.query}"
    return out


def classify(url):
    """One URL -> a list of (class, reason) findings from its
    own shape alone (catalogue-wide classes are computed
    later). An empty list means the link is well-formed as
    written — never that it loads."""
    findings = []
    if any(ch.isspace() for ch in url):
        findings.append(("malformed",
                         "the URL contains a space"))
        return findings
    if url.startswith("#"):
        findings.append(("placeholder",
                         "a fragment-only link ('#...') — it "
                         "points at a spot on a page, not at a "
                         "page; in a description it goes nowhere"))
        return findings
    m = _SCHEME_RE.match(url)
    if not m:
        findings.append(("malformed",
                         "missing scheme — a description reader "
                         "cannot follow it as written; it needs "
                         "https:// in front"))
        return findings
    scheme = m.group(1).lower()
    rest = url[m.end():]
    after = rest[2:] if rest.startswith("//") else rest
    if _SCHEME_RE.match(after) and "://" in after:
        findings.append(("malformed",
                         "double scheme — the URL carries two "
                         "schemes (a paste of a full URL into a "
                         "field that added its own)"))
        return findings
    if scheme in ("mailto", "tel"):
        if scheme == "mailto" and "@" not in rest:
            findings.append(("malformed",
                             "a mailto: link with no address"))
        if scheme == "tel" and not any(c.isdigit() for c in rest):
            findings.append(("malformed",
                             "a tel: link with no digits"))
        return findings
    if scheme not in ("http", "https"):
        findings.append(("malformed",
                         f"unsupported scheme {scheme!r} — a "
                         f"video description can only carry "
                         f"http(s) links a viewer can follow"))
        return findings
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        findings.append(("malformed",
                         "the URL cannot be parsed as written"))
        return findings
    if not host:
        findings.append(("malformed",
                         "the URL has no host"))
        return findings
    if scheme == "http":
        findings.append(("insecure-http",
                         "scheme is http, not https — most "
                         "browsers warn or upgrade, and some "
                         "embeds refuse it"))
    if host in DEAD_DOMAINS:
        findings.append(("dead-domain",
                         f"host {host} belongs to a service "
                         f"that has shut down ({DEAD_DOMAINS[host]})"
                         f" — an expired-domain risk pattern; "
                         f"replace it with a live target"))
    segments = [s for s in parts.path.split("/") if s]
    joined = "/".join(segments).lower()
    if host in PLACEHOLDER_HOSTS:
        findings.append(("placeholder",
                         f"host {host} is a documentation "
                         f"placeholder — the real link was never "
                         f"filled in"))
    elif any(s.lower() in PLACEHOLDER_TOKENS for s in segments) \
            or "your-link-here" in joined \
            or "insert-link" in joined:
        findings.append(("placeholder",
                         "the path carries a template placeholder "
                         "— the real link was never filled in"))
    if parts.query:
        keys = []
        for key, _ in parse_qsl(parts.query, keep_blank_values=True):
            lk = key.lower()
            if (lk.startswith("utm_") or lk in TRACKING_PARAMS) \
                    and lk not in keys:
                keys.append(lk)
        if keys:
            findings.append(("tracking-clutter",
                             "carries tracking parameter(s): "
                             + ", ".join(sorted(keys))
                             + " — clutter, not rot, but worth "
                               "stripping; an affiliate 'tag' "
                               "pays whoever it names"))
    return findings


def _anchor_key(anchor):
    return re.sub(r"\s+", " ", anchor.strip()).casefold()


def analyse(videos):
    """The whole catalogue -> a report dict: per-video
    occurrences with findings, catalogue-level findings
    (conflicting anchors, plain duplicates) and the summary
    counts. Pure function of the input."""
    per_video = []
    by_normalized = {}
    anchors = {}
    for video in videos:
        occs = []
        for occ in extract_occurrences(video):
            findings = []
            if occ["forced"]:
                findings.append(occ["forced"])
            else:
                findings.extend(classify(occ["url"]))
            entry = {
                "url": occ["url"], "anchor": occ["anchor"],
                "normalized": normalize_url(occ["url"]),
                "findings": findings,
                "video": video["ref"],
            }
            occs.append(entry)
            by_normalized.setdefault(entry["normalized"],
                                     []).append(entry)
            if occ["anchor"] and occ["anchor"] != occ["url"]:
                anchors.setdefault(_anchor_key(occ["anchor"]),
                                   []).append(entry)
        per_video.append({
            "ref": video["ref"], "title": video["title"],
            "occurrences": occs,
        })

    catalogue_findings = []
    conflict_urls = set()
    for key in sorted(anchors):
        entries = anchors[key]
        targets = {e["normalized"] for e in entries}
        if len(targets) >= 2:
            conflict_urls |= targets
            catalogue_findings.append({
                "class": "conflicting-duplicate",
                "anchor": entries[0]["anchor"],
                "targets": [
                    {"url": e["url"], "video": e["video"],
                     "normalized": e["normalized"]}
                    for e in entries],
            })
    duplicate_urls = set()
    for norm in sorted(by_normalized):
        entries = by_normalized[norm]
        videos_seen = {e["video"] for e in entries}
        if len(videos_seen) >= 2:
            duplicate_urls.add(norm)
            catalogue_findings.append({
                "class": "duplicate",
                "url": entries[0]["url"], "normalized": norm,
                "occurrences": len(entries),
                "videos": sorted(videos_seen),
            })

    classes_by_url = {}
    findings_by_class = {}
    total_occurrences = 0
    for video in per_video:
        for entry in video["occurrences"]:
            total_occurrences += 1
            classes = classes_by_url.setdefault(
                entry["normalized"], set())
            for cls, _reason in entry["findings"]:
                classes.add(cls)
                findings_by_class[cls] = \
                    findings_by_class.get(cls, 0) + 1
    for finding in catalogue_findings:
        cls = finding["class"]
        findings_by_class[cls] = findings_by_class.get(cls, 0) + 1
        if cls == "conflicting-duplicate":
            for target in finding["targets"]:
                classes_by_url.setdefault(
                    target["normalized"], set()).add(cls)
        elif cls == "duplicate":
            classes_by_url.setdefault(
                finding["normalized"], set()).add(cls)

    cannot, check, clean = set(), set(), set()
    for norm, classes in classes_by_url.items():
        sevs = {SEVERITY[c] for c in classes}
        if "cannot-work" in sevs:
            cannot.add(norm)
        elif "check" in sevs:
            check.add(norm)
        else:
            clean.add(norm)

    summary = {
        "videos": len(per_video),
        "link_occurrences": total_occurrences,
        "unique_links": len(classes_by_url),
        "findings_by_class": {
            c: findings_by_class[c] for c in CLASS_ORDER
            if findings_by_class.get(c)},
        "cannot_work_as_written": len(cannot),
        "worth_checking_live": len(check),
        "clean_links": len(clean),
    }
    actionable = bool(cannot or check)
    return {
        "videos": per_video,
        "catalogue_findings": catalogue_findings,
        "classes_by_url": {k: sorted(v) for k, v in
                           classes_by_url.items()},
        "summary": summary,
        "exit_code": 1 if actionable else 0,
    }


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------

def _finding_json(cls, reason, url, anchor):
    out = {"class": cls, "severity": SEVERITY[cls], "url": url,
           "reason": reason}
    if anchor:
        out["anchor"] = anchor
    return out


def _report_json(report, catalogue_name, command):
    videos = []
    for video in report["videos"]:
        videos.append({
            "ref": video["ref"], "title": video["title"],
            "link_count": len(video["occurrences"]),
            "findings": [
                _finding_json(cls, reason, e["url"], e["anchor"])
                for e in video["occurrences"]
                for cls, reason in e["findings"]],
        })
    catalogue = []
    for finding in report["catalogue_findings"]:
        if finding["class"] == "conflicting-duplicate":
            catalogue.append({
                "class": "conflicting-duplicate",
                "severity": "check",
                "anchor": finding["anchor"],
                "targets": finding["targets"],
                "reason": "the same anchor text points at "
                          "different URLs across the catalogue — "
                          "one of them is stale",
            })
        else:
            catalogue.append({
                "class": "duplicate", "severity": "info",
                "url": finding["url"],
                "occurrences": finding["occurrences"],
                "videos": finding["videos"],
                "reason": "the same link appears in several "
                          "videos — fine on its own; only a "
                          "problem if the target changes",
            })
    return {
        "tool": TOOL, "version": __version__, "command": command,
        "catalogue_file": catalogue_name,
        "scope": SCOPE_NOTE,
        "videos": videos,
        "catalogue_findings": catalogue,
        "summary": report["summary"],
    }


def cmd_audit(a):
    videos = load_catalogue(a.catalogue)
    report = analyse(videos)
    name = Path(a.catalogue).name
    summary = report["summary"]
    if a.json:
        print(json.dumps(_report_json(report, name, "audit")))
        return report["exit_code"]
    print(f"{TOOL} v{__version__} — audit · catalogue {name}")
    print(f"{summary['videos']} video(s) · "
          f"{summary['link_occurrences']} link occurrence(s) · "
          f"{summary['unique_links']} unique link(s)")
    print("Structural audit only: this tool reads text and never "
          "fetches a link.")
    print("A finding means the link cannot work as written, or "
          "is worth a live")
    print("check — never that it was loaded and failed.")
    print()
    counts = summary["findings_by_class"]
    if counts:
        print("Findings by class (findings, not links):")
        for cls in CLASS_ORDER:
            if cls in counts:
                suffix = " (informational)" if cls == "duplicate" \
                    else ""
                print(f"  {cls}: {counts[cls]}{suffix}")
    else:
        print("Findings: none")
    print()
    print(f"Cannot work as written: "
          f"{summary['cannot_work_as_written']} unique link(s)")
    print(f"Worth a live check: "
          f"{summary['worth_checking_live']} unique link(s)")
    print(f"Clean: {summary['clean_links']} unique link(s)")
    print()
    print("Per video:")
    for video in report["videos"]:
        heading = f"  [{video['ref']}]"
        if video["title"] and video["title"] != video["ref"]:
            heading += f" {video['title']}"
        print(heading)
        findings = [(e, cls, reason)
                    for e in video["occurrences"]
                    for cls, reason in e["findings"]]
        if not findings:
            print(f"    {len(video['occurrences'])} link(s) · "
                  f"no findings")
        for entry, cls, reason in findings:
            print(f"    ! {cls} — {entry['url']} — {reason}")
    if report["catalogue_findings"]:
        print()
        print("Across the catalogue:")
        for finding in report["catalogue_findings"]:
            if finding["class"] == "conflicting-duplicate":
                print(f"  ! conflicting-duplicate — anchor "
                      f"{finding['anchor']!r} points at "
                      f"{len({t['normalized'] for t in finding['targets']})}"
                      f" different URLs:")
                for target in finding["targets"]:
                    print(f"      {target['url']} — in "
                          f"[{target['video']}]")
            else:
                refs = ", ".join(f"[{v}]"
                                 for v in finding["videos"])
                print(f"  · duplicate — {finding['url']} appears "
                      f"in {len(finding['videos'])} video(s): "
                      f"{refs} — fine on its own; only a problem "
                      f"if the target changes")
    return report["exit_code"]


def cmd_links(a):
    videos = load_catalogue(a.catalogue)
    report = analyse(videos)
    name = Path(a.catalogue).name
    summary = report["summary"]
    grouped = {}
    for video in report["videos"]:
        for entry in video["occurrences"]:
            slot = grouped.setdefault(entry["normalized"], {
                "url": entry["url"], "occurrences": 0,
                "videos": []})
            slot["occurrences"] += 1
            if video["ref"] not in slot["videos"]:
                slot["videos"].append(video["ref"])
    rows = []
    for norm, slot in grouped.items():
        try:
            host = (urlsplit(slot["url"]).hostname or "").lower()
        except ValueError:
            host = ""
        rows.append({
            "url": slot["url"], "normalized": norm,
            "domain": host or None,
            "occurrences": slot["occurrences"],
            "videos": slot["videos"],
            "classes": report["classes_by_url"].get(norm, []),
        })
    rows.sort(key=lambda r: (-r["occurrences"], r["url"]))
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "links", "catalogue_file": name,
            "scope": SCOPE_NOTE, "links": rows,
            "summary": summary,
        }))
        return report["exit_code"]
    print(f"{TOOL} v{__version__} — links · catalogue {name}")
    print(f"{summary['unique_links']} unique link(s) · "
          f"{summary['link_occurrences']} occurrence(s)")
    print()
    for row in rows:
        refs = ", ".join(f"[{v}]" for v in row["videos"])
        line = f"  {row['occurrences']}× {row['url']} — in {refs}"
        if row["classes"]:
            line += " · " + ", ".join(row["classes"])
        print(line)
    return report["exit_code"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json
    mode ({"error": ...} on stdout, same exit code 2) — an agent
    driving this tool with --json never gets plain text or a
    traceback. The flag lives on the class so subparsers share
    it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _json_arg(p):
    p.add_argument("--json", action="store_true",
                   help="one JSON object instead of text output")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="Audit a video-description catalogue for "
                    "link rot — structurally, offline, never "
                    "fetching a single link (stdlib only, "
                    "local only).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_audit = sub.add_parser(
        "audit", help="per-video findings, catalogue-wide "
                      "findings and the cannot-work / "
                      "worth-checking counts")
    p_audit.add_argument("catalogue",
                         help="catalogue file (.json or .csv)")
    _json_arg(p_audit)
    p_audit.set_defaults(func=cmd_audit)

    p_links = sub.add_parser(
        "links", help="the flat inventory: every unique link, "
                      "its occurrences, its videos, its classes")
    p_links.add_argument("catalogue",
                         help="catalogue file (.json or .csv)")
    _json_arg(p_links)
    p_links.set_defaults(func=cmd_links)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))
    except BrokenPipeError:
        return 2


if __name__ == "__main__":
    sys.exit(main())
