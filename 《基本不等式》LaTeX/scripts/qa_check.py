# -*- coding: utf-8 -*-
"""Post-compile QA for a Loom Chinese lecture-handout project.

Assumes the project has already been compiled twice with XeLaTeX (so main.log,
main.toc and main.pdf exist). Checks the traps this workflow keeps hitting:

  1. no LaTeX errors            (lines starting with "!" in main.log)
  2. no Overfull \\hbox          (relax with --allow-overfull N)
  3. main.toc exists, non-empty (TOC actually generated)
  4. no undefined references    (LaTeX Warning: Reference ... undefined)
  5. every \\input{sections/..} target file exists
  6. \\end{document} lives only in main.tex, never in a section file
  7. problem numbers (题 N) pair one-to-one with solution numbers (题 N · 解析);
     homework items (练习 N) are counted separately and never required to pair

Exit 0 = all pass, 1 = at least one FAIL. Prints one line per check.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 题 12 / 题12 / 题 12 · 解析 — allow full/half-width spaces after 题.
PROBLEM_RE = re.compile(r"\\begin\{problem\}\{\s*题\s*(\d+)")
SOLUTION_RE = re.compile(r"\\begin\{solution\}\{\s*题\s*(\d+)")
EXERCISE_RE = re.compile(r"\\begin\{problem\}\{\s*练习\s*(\d+)")
INPUT_RE = re.compile(r"\\input\{([^}]+)\}")


def read_text(path: Path) -> str:
    # main.log can carry stray bytes; never let decoding crash the check.
    return path.read_text(encoding="utf-8", errors="replace")


def strip_tex_comments(text: str) -> str:
    """Drop LaTeX comments so commented-out \\input / problem / \\end{document}
    lines are not mistaken for live code. A comment runs from the first
    unescaped % to end of line; \\% is a literal percent, not a comment."""
    out = []
    for line in text.splitlines():
        cut = None
        i = 0
        while i < len(line):
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == "%":
                cut = i
                break
            i += 1
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="QA a compiled Loom handout project.")
    parser.add_argument("--dir", required=True, help="Project directory (contains main.tex).")
    parser.add_argument("--main", default="main", help="Main file stem (default: main).")
    parser.add_argument("--allow-overfull", type=int, default=0,
                        help="Tolerate up to N Overfull \\hbox warnings (default 0).")
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    stem = args.main
    failures: list[str] = []
    notes: list[str] = []

    main_tex = root / f"{stem}.tex"
    log = root / f"{stem}.log"
    toc = root / f"{stem}.toc"

    if not main_tex.exists():
        print(f"FAIL: {main_tex.name} not found in {root}")
        return 1

    # --- log-based checks -------------------------------------------------
    if not log.exists():
        failures.append(f"{log.name} missing — compile the project first (xelatex twice)")
    else:
        log_text = read_text(log)
        errors = [ln for ln in log_text.splitlines() if ln.startswith("!")]
        if errors:
            failures.append(f"{len(errors)} LaTeX error(s), e.g. {errors[0][:80]!r}")
        overfull = len(re.findall(r"Overfull \\hbox", log_text))
        if overfull > args.allow_overfull:
            failures.append(f"{overfull} Overfull \\hbox (allowed {args.allow_overfull})")
        elif overfull:
            notes.append(f"{overfull} Overfull \\hbox (within allowance)")
        undef = len(re.findall(r"Reference .* undefined", log_text))
        if undef:
            failures.append(f"{undef} undefined reference(s) — did you compile twice?")
        fonts = re.findall(r"loom-cn: .*", log_text)
        if fonts:
            notes.append("font tiers -> " + " | ".join(sorted(set(fonts))))

    # --- TOC --------------------------------------------------------------
    if not toc.exists() or not toc.read_bytes().strip():
        failures.append("main.toc missing or empty — add \\tableofcontents and compile twice")

    # --- \input targets exist --------------------------------------------
    main_text = strip_tex_comments(read_text(main_tex))
    for target in INPUT_RE.findall(main_text):
        # \input may omit the .tex extension.
        cand = root / target
        cand_tex = cand if cand.suffix else cand.with_suffix(".tex")
        if not cand_tex.exists():
            failures.append(f"\\input target missing: {target}")

    # --- \end{document} only in main.tex ---------------------------------
    section_files = sorted((root / "sections").glob("*.tex")) if (root / "sections").is_dir() else []
    for sf in section_files:
        if "\\end{document}" in strip_tex_comments(read_text(sf)):
            failures.append(f"stray \\end{{document}} in {sf.name} — it will swallow later input")

    # --- problem/solution number pairing ---------------------------------
    all_tex = [main_tex] + section_files
    prob_nums: set[int] = set()
    sol_nums: set[int] = set()
    exercise_nums: set[int] = set()
    for tf in all_tex:
        text = strip_tex_comments(read_text(tf))
        prob_nums.update(int(n) for n in PROBLEM_RE.findall(text))
        sol_nums.update(int(n) for n in SOLUTION_RE.findall(text))
        exercise_nums.update(int(n) for n in EXERCISE_RE.findall(text))
    # A "题 N" that is really an exercise line would double-count; exercises use
    # 练习 N, so they are already excluded from prob_nums by the regex anchor.
    missing_sol = sorted(prob_nums - sol_nums)
    orphan_sol = sorted(sol_nums - prob_nums)
    if missing_sol:
        failures.append(f"题目缺解析: {missing_sol}")
    if orphan_sol:
        failures.append(f"解析无对应题目: {orphan_sol}")

    # --- report -----------------------------------------------------------
    print(f"题目 {len(prob_nums)} · 解析 {len(sol_nums)} · 课后练习 {len(exercise_nums)}")
    for n in notes:
        print("note: " + n)
    if failures:
        for f in failures:
            print("FAIL: " + f)
        return 1
    print("PASS: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
