#!/usr/bin/env python3
"""Validate *.review.yaml files against the schema the viewer expects.

Usage: validate.py OUT_DIR   (exit 1 if any file is invalid)
"""
import sys
from collections import Counter
from pathlib import Path

import yaml

SEVERITIES = {"critical", "high", "medium", "low", "nit"}
REQUIRED = ("id", "title", "severity", "category", "location", "summary", "suggested_fix")


def validate_file(path):
    try:
        d = yaml.safe_load(Path(path).read_text())
    except Exception as e:
        return [f"unparseable: {e}"]
    if not isinstance(d, dict):
        return ["top level is not a mapping"]
    errs = [f"missing `{k}`" for k in ("project", "findings") if k not in d]
    findings = d.get("findings") or []
    if not isinstance(findings, list):
        return errs + ["`findings` is not a list"]
    ids = set()
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errs.append(f"finding[{i}] is not a mapping")
            continue
        if not isinstance(f.get("id"), int):
            errs.append(f"finding[{i}] id is not an integer")
            continue
        errs += [f"finding[{i}] missing `{k}`" for k in REQUIRED if not f.get(k)]
        if f.get("severity") not in SEVERITIES:
            errs.append(f"finding[{i}] bad severity {f.get('severity')!r}")
        if f.get("id") in ids:
            errs.append(f"finding[{i}] duplicate id {f.get('id')}")
        ids.add(f.get("id"))
    return errs


if __name__ == "__main__":
    root = Path(sys.argv[1])
    bad, sev, n = 0, Counter(), 0
    for p in sorted(root.rglob("*.review.yaml")):
        n += 1
        errs = validate_file(p)
        if errs:
            bad += 1
            print(f"{p.relative_to(root)}: " + "; ".join(errs))
        else:
            sev.update(f["severity"] for f in yaml.safe_load(p.read_text())["findings"])
    print(f"{n} files, {bad} invalid, findings: {dict(sev)}")
    sys.exit(1 if bad else 0)
