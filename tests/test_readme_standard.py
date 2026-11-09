"""Every published study README meets docs/report-standard.md."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_readmes  # noqa: E402
from report_meta import META  # noqa: E402

SECTIONS = ["**TL;DR**", "## Key numbers", "## Why it matters for a club", "## The question", "## Results",
            "## Validation", "## Limitations", "## Next steps", "## Reproduce", "## Files in this folder"]
FIELDS = ["short", "tldr", "question", "seasons", "tags", "hero", "figs", "key", "why", "validation", "next", "files"]


def test_every_study_has_presentation_metadata():
    for slug, _ in build_readmes.REPORTS:
        assert slug in META, f"{slug}: add an entry to scripts/report_meta.py"
        missing = [k for k in FIELDS if k not in META[slug]]
        assert not missing, f"{slug}: missing {missing}"


def test_every_study_readme_has_all_sections():
    for slug, _ in build_readmes.REPORTS:
        p = ROOT / "reports" / slug / "README.md"
        if not p.exists():
            continue
        text = p.read_text()
        for s in SECTIONS:
            assert s in text, f"{slug}: README missing {s}"


def test_figures_referenced_exist():
    for slug, _ in build_readmes.REPORTS:
        m = META[slug]
        figs = [m["hero"][0]] + [f for v in m["figs"].values() for f, _ in v]
        for f in figs:
            assert (ROOT / "reports" / slug / f).exists(), f"{slug}: {f} not found"
