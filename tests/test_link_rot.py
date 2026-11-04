#!/usr/bin/env python3
"""Tests for link-rot. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

Expectations are worked out from the catalogues below by hand,
not copied from the tool's own output:

- The bundled sample (examples/sample-catalogue.json) carries
  6 fictional videos and 14 link occurrences over 13 unique
  links, with exactly one planted finding per class:
    malformed              the double-scheme sponsor URL
    placeholder            an example.com affiliate link
    dead-domain            a goo.gl link from 2019
    insecure-http          an http:// camera-store link
    tracking-clutter       utm_* + ref on a shoe link
    conflicting-duplicate  the anchor "My training plan"
                           points at plan-v1 in one video and
                           plan-v2 in another
    duplicate              the keyboard link appears in two
                           videos (informational only)
  Buckets, counting UNIQUE links: cannot-work = 3 (malformed,
  placeholder, dead-domain), worth-a-live-check = 4 (the http
  link, the tracked link, and BOTH plan URLs — a conflict
  flags each side), clean = 6. 3 + 4 + 6 = 13. Exit 1.
- A catalogue whose only catalogue-level wrinkle is a plain
  duplicate exits 0: a duplicate is informational, never an
  action finding.
- An email address in prose, a version number ("2.0") and a
  bare file name ("notes.txt") are NOT links; a www. token and
  a domain/path token ARE links missing their scheme.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
TOOL = PACK_ROOT / "src" / "link_rot.py"
SAMPLE = PACK_ROOT / "examples" / "sample-catalogue.json"


def run(args, cwd):
    return subprocess.run([sys.executable, str(TOOL)] + args,
                          capture_output=True, text=True, cwd=cwd)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_json(self, obj, name="catalogue.json"):
        path = self.dir / name
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def write_text(self, text, name):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def audit_json(self, path):
        proc = run(["audit", str(path), "--json"], self.dir)
        return proc, json.loads(proc.stdout)

    def one_video(self, description=None, links=None, **extra):
        video = {"id": "v1", "title": "One Video"}
        if description is not None:
            video["description"] = description
        if links is not None:
            video["links"] = links
        video.update(extra)
        return self.write_json([video])


class SampleAuditTest(TempDirTest):
    def test_sample_summary_counts(self):
        proc, data = self.audit_json(SAMPLE)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(data["tool"], "link-rot")
        self.assertEqual(data["command"], "audit")
        summary = data["summary"]
        self.assertEqual(summary["videos"], 6)
        self.assertEqual(summary["link_occurrences"], 14)
        self.assertEqual(summary["unique_links"], 13)
        self.assertEqual(summary["findings_by_class"], {
            "malformed": 1, "placeholder": 1, "dead-domain": 1,
            "conflicting-duplicate": 1, "insecure-http": 1,
            "tracking-clutter": 1, "duplicate": 1})
        self.assertEqual(summary["cannot_work_as_written"], 3)
        self.assertEqual(summary["worth_checking_live"], 4)
        self.assertEqual(summary["clean_links"], 6)

    def test_sample_per_video_findings(self):
        _proc, data = self.audit_json(SAMPLE)
        by_ref = {v["ref"]: v for v in data["videos"]}
        self.assertEqual(by_ref["desk-setup-2024"]["link_count"], 3)
        self.assertEqual(by_ref["desk-setup-2024"]["findings"], [])
        classes = {ref: [f["class"] for f in v["findings"]]
                   for ref, v in by_ref.items()}
        self.assertEqual(classes["camera-gear-2025"],
                         ["insecure-http"])
        self.assertEqual(classes["trail-kit"], ["tracking-clutter"])
        self.assertEqual(classes["favourites-2019"], ["dead-domain"])
        self.assertEqual(classes["sponsor-haul"], ["malformed"])
        self.assertEqual(classes["training-update"], ["placeholder"])
        for video in data["videos"]:
            for finding in video["findings"]:
                self.assertIn("reason", finding)
                self.assertIn("severity", finding)

    def test_sample_catalogue_findings(self):
        _proc, data = self.audit_json(SAMPLE)
        catalogue = data["catalogue_findings"]
        self.assertEqual(len(catalogue), 2)
        conflict = catalogue[0]
        self.assertEqual(conflict["class"], "conflicting-duplicate")
        self.assertEqual(conflict["anchor"], "My training plan")
        self.assertEqual(
            {t["url"] for t in conflict["targets"]},
            {"https://plans.mayachen.ca/plan-v1",
             "https://plans.mayachen.ca/plan-v2"})
        dup = catalogue[1]
        self.assertEqual(dup["class"], "duplicate")
        self.assertEqual(dup["severity"], "info")
        self.assertEqual(dup["url"], "https://keyshop.io/k87-pro")
        self.assertEqual(dup["videos"],
                         ["desk-setup-2024", "training-update"])

    def test_sample_text_output(self):
        proc = run(["audit", str(SAMPLE)], self.dir)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("6 video(s) · 14 link occurrence(s) · "
                      "13 unique link(s)", proc.stdout)
        self.assertIn("Cannot work as written: 3 unique link(s)",
                      proc.stdout)
        self.assertIn("Worth a live check: 4 unique link(s)",
                      proc.stdout)
        self.assertIn("never fetches a link", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_sample_links_command(self):
        proc = run(["links", str(SAMPLE), "--json"], self.dir)
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertEqual(len(data["links"]), 13)
        by_url = {r["url"]: r for r in data["links"]}
        keyboard = by_url["https://keyshop.io/k87-pro"]
        self.assertEqual(keyboard["occurrences"], 2)
        self.assertEqual(keyboard["classes"], ["duplicate"])
        self.assertEqual(keyboard["domain"], "keyshop.io")
        self.assertEqual(
            by_url["https://plans.mayachen.ca/plan-v1"]["classes"],
            ["conflicting-duplicate"])
        self.assertEqual(
            by_url["https://goo.gl/faves2019"]["classes"],
            ["dead-domain"])
        text = run(["links", str(SAMPLE)], self.dir)
        self.assertIn("2× https://keyshop.io/k87-pro", text.stdout)


class CleanAndInfoTest(TempDirTest):
    def test_clean_catalogue_exits_zero(self):
        path = self.one_video(
            "All good: https://shop.ca/widget and "
            "[guide](https://blog.shop.ca/guide) — mail me at "
            "mailto:maya@example.org or call tel:+1-250-555-0100")
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["summary"]["findings_by_class"], {})
        self.assertEqual(data["summary"]["clean_links"], 4)
        text = run(["audit", str(path)], self.dir)
        self.assertIn("Findings: none", text.stdout)

    def test_duplicate_only_exits_zero(self):
        path = self.write_json([
            {"id": "a", "description": "Gear: https://shop.ca/x"},
            {"id": "b", "description": "Again https://shop.ca/x"},
        ])
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["summary"]["findings_by_class"],
                         {"duplicate": 1})
        self.assertEqual(data["summary"]["clean_links"], 1)

    def test_video_with_no_links(self):
        path = self.one_video("No links in this one, just words.")
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["videos"][0]["link_count"], 0)
        self.assertEqual(data["summary"]["unique_links"], 0)

    def test_prose_that_is_not_links(self):
        path = self.one_video(
            "Email maya@example.org, see notes.txt, version 2.0 "
            "of the plan, e.g. the second draft.")
        _proc, data = self.audit_json(path)
        self.assertEqual(data["summary"]["link_occurrences"], 0)


class MalformedTest(TempDirTest):
    def classes(self, description):
        path = self.one_video(description)
        _proc, data = self.audit_json(path)
        return [f["class"] for v in data["videos"]
                for f in v["findings"]]

    def test_double_scheme(self):
        self.assertEqual(
            self.classes("Grab it: https://https://shop.ca/landing"),
            ["malformed"])

    def test_missing_scheme_www(self):
        self.assertEqual(self.classes("See www.shop.ca/boots"),
                         ["malformed"])

    def test_missing_scheme_domain_path(self):
        self.assertEqual(self.classes("See bit.ly/spring-sale"),
                         ["malformed"])

    def test_space_in_markdown_target(self):
        self.assertEqual(
            self.classes("[gear](https://exa mple.ca/widget)"),
            ["malformed"])

    def test_unbalanced_brackets(self):
        proc_classes = self.classes("[gear](https://shop.ca/widget")
        self.assertEqual(proc_classes, ["malformed"])

    def test_unsupported_scheme(self):
        self.assertEqual(self.classes("Old mirror: ftp://shop.ca/x"),
                         ["malformed"])

    def test_no_host(self):
        self.assertEqual(self.classes("Broken: https:///path-only"),
                         ["malformed"])

    def test_bad_mailto(self):
        self.assertEqual(self.classes("Write to mailto:nobody"),
                         ["malformed"])

    def test_empty_markdown_target(self):
        self.assertEqual(self.classes("[click]()"), ["malformed"])


class ClassTest(TempDirTest):
    def findings(self, description):
        path = self.one_video(description)
        _proc, data = self.audit_json(path)
        return [f for v in data["videos"] for f in v["findings"]]

    def test_insecure_http(self):
        found = self.findings("Body: http://shop.ca/body")
        self.assertEqual([f["class"] for f in found],
                         ["insecure-http"])
        self.assertEqual(found[0]["severity"], "check")

    def test_tracking_params_named(self):
        found = self.findings(
            "Shoes: https://shop.ca/s?utm_campaign=spring&"
            "utm_source=yt&tag=aff-20&size=9")
        self.assertEqual([f["class"] for f in found],
                         ["tracking-clutter"])
        reason = found[0]["reason"]
        for param in ("tag", "utm_campaign", "utm_source"):
            self.assertIn(param, reason)
        self.assertNotIn("size", reason)

    def test_dead_domain(self):
        for url in ("https://goo.gl/abc", "https://vine.co/v/xyz",
                    "https://mixer.com/channel"):
            found = self.findings(f"Old: {url}")
            self.assertEqual([f["class"] for f in found],
                             ["dead-domain"], url)
            self.assertEqual(found[0]["severity"], "cannot-work")

    def test_live_shortener_not_dead(self):
        self.assertEqual(self.findings("New: https://bit.ly/3AbCdEf"),
                         [])

    def test_placeholder_host(self):
        found = self.findings("Deal: https://example.com/affiliate")
        self.assertEqual([f["class"] for f in found], ["placeholder"])

    def test_placeholder_path_token(self):
        found = self.findings("Deal: https://bit.ly/xxx")
        self.assertEqual([f["class"] for f in found], ["placeholder"])

    def test_placeholder_your_link_here(self):
        found = self.findings("Deal: https://shop.ca/your-link-here")
        self.assertEqual([f["class"] for f in found], ["placeholder"])

    def test_fragment_only(self):
        found = self.findings("[jump](#)")
        self.assertEqual([f["class"] for f in found], ["placeholder"])

    def test_http_and_dead_domain_stack(self):
        found = self.findings("Old: http://goo.gl/abc")
        self.assertEqual({f["class"] for f in found},
                         {"insecure-http", "dead-domain"})


class ExtractionTest(TempDirTest):
    def links_of(self, description):
        path = self.one_video(description)
        proc = run(["links", str(path), "--json"], self.dir)
        return json.loads(proc.stdout)["links"]

    def test_markdown_image_extracted(self):
        rows = self.links_of("Thumb: ![setup](https://img.ca/t.jpg)")
        self.assertEqual([r["url"] for r in rows],
                         ["https://img.ca/t.jpg"])

    def test_markdown_title_allowed(self):
        rows = self.links_of(
            '[gear](https://shop.ca/x "My gear page")')
        self.assertEqual([r["url"] for r in rows],
                         ["https://shop.ca/x"])

    def test_angle_bracket_target(self):
        rows = self.links_of("[gear](<https://shop.ca/x>)")
        self.assertEqual([r["url"] for r in rows],
                         ["https://shop.ca/x"])

    def test_bare_url_trailing_punctuation(self):
        rows = self.links_of(
            "See https://shop.ca/x, and (https://shop.ca/y).")
        self.assertEqual({r["url"] for r in rows},
                         {"https://shop.ca/x", "https://shop.ca/y"})

    def test_autolink_in_angles(self):
        rows = self.links_of("Mirror: <https://shop.ca/x>")
        self.assertEqual([r["url"] for r in rows],
                         ["https://shop.ca/x"])

    def test_unicode_domain_no_crash(self):
        proc, data = self.audit_json(
            self.one_video("Katalog: https://bücher.de/katalog"))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["summary"]["unique_links"], 1)

    def test_very_long_url(self):
        url = "https://shop.ca/" + "a" * 3000
        proc, data = self.audit_json(
            self.one_video(f"Long: {url}"))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["summary"]["unique_links"], 1)


class CatalogueLevelTest(TempDirTest):
    def test_conflict_from_links_list(self):
        path = self.write_json([
            {"id": "a", "links": [
                {"url": "https://plans.ca/v1", "text": "The plan"}]},
            {"id": "b", "links": [
                {"url": "https://plans.ca/v2", "label": "The plan"}]},
        ])
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 1)
        conflict = data["catalogue_findings"][0]
        self.assertEqual(conflict["class"], "conflicting-duplicate")
        self.assertEqual(conflict["anchor"], "The plan")

    def test_same_anchor_same_url_is_duplicate_not_conflict(self):
        path = self.write_json([
            {"id": "a", "description":
             "[Plan](https://plans.ca/v1)"},
            {"id": "b", "description":
             "[Plan](https://plans.ca/v1)"},
        ])
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(
            [f["class"] for f in data["catalogue_findings"]],
            ["duplicate"])

    def test_anchor_that_is_the_url_never_conflicts(self):
        path = self.write_json([
            {"id": "a", "description":
             "[https://plans.ca/v1](https://plans.ca/v1)"},
            {"id": "b", "description":
             "[https://plans.ca/v1](https://plans.ca/v2)"},
        ])
        _proc, data = self.audit_json(path)
        self.assertEqual(data["catalogue_findings"], [])

    def test_anchor_case_and_whitespace_normalised(self):
        path = self.write_json([
            {"id": "a", "description":
             "[My  Plan](https://plans.ca/v1)"},
            {"id": "b", "description":
             "[my plan](https://plans.ca/v2)"},
        ])
        _proc, data = self.audit_json(path)
        self.assertEqual(data["catalogue_findings"][0]["class"],
                         "conflicting-duplicate")

    def test_description_and_links_combine(self):
        path = self.one_video(
            "In text: https://shop.ca/a",
            links=["https://shop.ca/b"])
        _proc, data = self.audit_json(path)
        self.assertEqual(data["videos"][0]["link_count"], 2)


class CsvInputTest(TempDirTest):
    def test_csv_audit(self):
        path = self.write_text(
            "id,title,description\n"
            "v1,First,Body: http://shop.ca/body\n"
            "v2,Second,Shoes: https://shop.ca/s?utm_source=yt\n",
            "catalogue.csv")
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(data["summary"]["videos"], 2)
        self.assertEqual(data["summary"]["findings_by_class"],
                         {"insecure-http": 1, "tracking-clutter": 1})

    def test_csv_links_column(self):
        path = self.write_text(
            "title,links\n"
            "First,https://shop.ca/a; https://shop.ca/b\n",
            "catalogue.csv")
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["videos"][0]["link_count"], 2)

    def test_csv_object_json_form(self):
        path = self.write_json({"videos": [
            {"id": "x", "description": "https://shop.ca/a"}]})
        proc, data = self.audit_json(path)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["summary"]["videos"], 1)


class ErrorTest(TempDirTest):
    def expect_error(self, args, needle=None):
        proc = run(args, self.dir)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        if needle:
            self.assertIn(needle, proc.stdout + proc.stderr)
        return proc

    def test_missing_file(self):
        self.expect_error(["audit", "nope.json"],
                          "cannot read catalogue file")

    def test_missing_file_json_mode(self):
        proc = run(["audit", "nope.json", "--json"], self.dir)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", json.loads(proc.stdout))

    def test_malformed_json(self):
        path = self.write_text("{not json", "bad.json")
        self.expect_error(["audit", str(path)], "not valid JSON")

    def test_json_object_without_videos(self):
        path = self.write_json({"items": []})
        self.expect_error(["audit", str(path)], "'videos' key")

    def test_top_level_string(self):
        path = self.write_text('"hello"', "s.json")
        self.expect_error(["audit", str(path)], "top level")

    def test_entry_not_object(self):
        path = self.write_json([42])
        self.expect_error(["audit", str(path)], "must be an object")

    def test_description_wrong_type(self):
        path = self.write_json([{"id": "v", "description": 7}])
        self.expect_error(["audit", str(path)], "'description'")

    def test_neither_description_nor_links(self):
        path = self.write_json([{"id": "v", "title": "Empty"}])
        self.expect_error(["audit", str(path)], "neither")

    def test_links_wrong_type(self):
        path = self.write_json([{"id": "v", "links": "x"}])
        self.expect_error(["audit", str(path)], "'links'")

    def test_links_entry_without_url(self):
        path = self.write_json([{"id": "v", "links": [{"text": "x"}]}])
        self.expect_error(["audit", str(path)], "'url'")

    def test_empty_catalogue(self):
        path = self.write_json([])
        self.expect_error(["audit", str(path)], "no videos")

    def test_unknown_extension(self):
        path = self.write_text("[]", "catalogue.txt")
        self.expect_error(["audit", str(path)], ".json or .csv")

    def test_csv_missing_columns(self):
        path = self.write_text("id,title\nv1,Hi\n", "c.csv")
        self.expect_error(["audit", str(path)], "'description' or "
                                                 "'links' column")

    def test_csv_ragged_row(self):
        path = self.write_text(
            "id,description\nv1,ok,extra\n", "c.csv")
        self.expect_error(["audit", str(path)], "row 2")

    def test_csv_unclosed_quote(self):
        path = self.write_text(
            'id,description\nv1,"never closed\n', "c.csv")
        self.expect_error(["audit", str(path)], "not valid CSV")

    def test_no_arguments(self):
        proc = run([], self.dir)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)

    def test_bad_subcommand_json_mode(self):
        proc = run(["bogus", "--json"], self.dir)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", json.loads(proc.stdout))


class NoNetworkTest(unittest.TestCase):
    def test_source_has_no_network_code(self):
        source = TOOL.read_text(encoding="utf-8")
        for banned in ("urllib.request", "urlopen", "http.client",
                       "import socket", "import requests",
                       "ssl", "ftplib"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
