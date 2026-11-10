"""Run the test-suite and write docs/TEST_REPORT.md (counts, coverage, acceptance results)."""
import ast
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JUNIT, COV = ROOT / "metrics" / "junit.xml", ROOT / "metrics" / "coverage.json"
TEST_FILES = ["tests/test_pipeline.py", "tests/test_backend.py", "tests/test_acceptance.py", "tests/test_ui.py"]


def docstrings() -> dict:
    """Map test function name -> first docstring line (the test's description)."""
    out = {}
    for f in TEST_FILES:
        for node in ast.walk(ast.parse((ROOT / f).read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                out[node.name] = (ast.get_docstring(node) or "").splitlines()[0] if ast.get_docstring(node) else ""
    return out


def main() -> int:
    """Run pytest, then render the Markdown report. Returns pytest's exit code."""
    (ROOT / "metrics").mkdir(exist_ok=True)
    proc = subprocess.run([sys.executable, "-m", "pytest", f"--junitxml={JUNIT}", "--cov",
                           f"--cov-report=json:{COV}", "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True)
    suite = ET.parse(JUNIT).getroot()
    suite = suite if suite.tag == "testsuite" else suite[0]
    docs, rows = docstrings(), []
    for tc in suite.iter("testcase"):
        base = re.sub(r"\[.*\]$", "", tc.get("name"))
        status = "FAIL" if tc.find("failure") is not None or tc.find("error") is not None else (
            "SKIP" if tc.find("skipped") is not None else "PASS")
        m = re.match(r"test_(tc|ac)(\d+)", base)
        rows.append((f"{m.group(1).upper()}-{int(m.group(2)):02d}" if m else "-", tc.get("name"),
                     docs.get(base, ""), status, float(tc.get("time"))))
    total = len(rows)
    passed = sum(r[3] == "PASS" for r in rows)
    failed = sum(r[3] == "FAIL" for r in rows)
    skipped = total - passed - failed
    cov = json.loads(COV.read_text())["totals"]["percent_covered"]
    tm = json.loads((ROOT / "metrics/train_metrics.json").read_text())
    lat = json.loads((ROOT / "metrics/latency.json").read_text())
    min_recall = min(v for k, v in tm.items() if k.startswith("recall_"))
    ac = [("AC-1", "Held-out macro-F1 >= 0.80", f"{tm['macro_f1']:.4f}", tm["macro_f1"] >= 0.80),
          ("AC-2", "Every class recall >= 0.70", f"min = {min_recall:.4f}", min_recall >= 0.70),
          ("AC-3", "p95 /predict latency < 300 ms", f"{lat['p95_ms']} ms (p50 {lat['p50_ms']} ms, n={lat['requests']})",
           lat["p95_ms"] < 300),
          ("AC-4", "Serving features == training features", "see test AC-04",
           all(r[3] == "PASS" for r in rows if r[0] == "AC-04")),
          ("AC-5", "No 5xx on malformed input", "see test AC-05", all(r[3] == "PASS" for r in rows if r[0] == "AC-05")),
          ("AC-6", "Line coverage of all project code >= 70%", f"{cov:.1f}%", cov >= 70)]
    lines = [
        "# AirSense - Test Report", "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by `make_test_report.py`_", "",
        "## 1. Summary", "", "| Metric | Value |", "|---|---|",
        f"| Total test cases | **{total}** |", f"| Passed | **{passed}** |", f"| Failed | **{failed}** |",
        f"| Skipped | {skipped} |", f"| Line coverage | {cov:.1f}% |",
        f"| Duration | {float(suite.get('time')):.1f} s |", "",
        "## 2. Acceptance criteria", "", "| ID | Criterion | Measured | Result |", "|---|---|---|---|",
        *[f"| {a} | {c} | {m} | {'MET' if ok else '**NOT MET**'} |" for a, c, m, ok in ac], "",
        f"**Overall: {'ACCEPTED - all criteria met' if all(a[3] for a in ac) and failed == 0 else 'NOT ACCEPTED'}**", "",
        "## 3. Test case results", "", "| ID | Test | Description | Result | Time (s) |", "|---|---|---|---|---|",
        *[f"| {i} | `{n}` | {d} | {s} | {t:.2f} |" for i, n, d, s, t in rows], ""]
    (ROOT / "docs" / "TEST_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{total} tests: {passed} passed, {failed} failed, {skipped} skipped; coverage {cov:.1f}%")
    if failed:
        print(proc.stdout[-3000:])
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
