"""typeset_paper.py — post-processor: studies/<id>/paper.md (+ figures) -> paper.tex + paper.pdf.

Deterministic Python, ZERO model calls. Takes a study's markdown write-up and
the matplotlib .png figures sitting beside it, emits paper.tex in the same
directory, and (best-effort) compiles it to paper.pdf with whatever LaTeX
engine the machine has. It never touches how papers are WRITTEN — it consumes
stages/study_paper.py's output after the fact and stages/study_paper.py does
not know it exists.

Why generate .tex directly instead of shelling out to pandoc:
  1. pandoc is not installed on the target machine (and neither is a TeX
     engine — the compile step must already survive an absent binary), and a
     required external binary contradicts the project's stdlib-first
     discipline. Direct generation needs nothing beyond Python to produce the
     .tex, so the conversion itself is unit-testable offline and only the
     final compile depends on a toolchain.
  2. The markdown surface is small and known: study_paper.py's prompt yields
     ATX headings, pipe tables, ![caption](fig.png) images, emphasis/code
     spans, lists — a bounded dialect a few hundred lines convert faithfully.
     Write-ups deliberately vary in SECTION structure (paper / design doc /
     direct answer), so nothing here assumes named sections; it converts
     whatever blocks appear, in order.
  3. Determinism: pandoc's output varies by version; this converter's output
     is a pure function of the input, so the .tex is reproducible evidence in
     the same sense as the rest of the study record.

Toolchain handling: the engine is discovered at run time (tectonic, latexmk,
pdflatex, xelatex, lualatex — on PATH plus /Library/TeX/texbin, the standard
MacTeX location). No engine found is an HONEST, bounded error message in the
result dict (and a clean non-zero CLI exit), never a traceback; paper.tex is
still written so the user can compile elsewhere. A failed compile returns a
bounded log tail, never the full log.

Figure placement: figures float [htbp] at the point the markdown embeds them,
width-capped to the line, with the markdown alt-text as the caption (a leading
"Figure N." / "Figure N:" prefix is stripped because LaTeX numbers captions
itself). A referenced figure missing on disk becomes a framed placeholder box
(recorded in the result under missing_figures) rather than a compile failure.

CLI:  python -m tools.typeset_paper <study-dir-or-paper.md> [--tex-only]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# character-level escaping
# ---------------------------------------------------------------------------

# LaTeX special characters, text mode.
_SPECIALS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}

# Unicode the papers actually use (surveyed from real studies/*/paper.md),
# plus obvious neighbours. Value is (text_mode, math_mode); math_mode is used
# inside $...$ spans the author wrote, where a bare macro is wanted.
_UNICODE = {
    "\u2014": ("---", "-"),               # em dash
    "\u2013": ("--", "-"),                # en dash
    "\u2026": (r"\dots{}", r"\dots"),
    "\u00a0": ("~", " "),                 # no-break space
    "\u2018": ("`", "`"),
    "\u2019": ("'", "'"),
    "\u201c": ("``", "``"),
    "\u201d": ("''", "''"),
    "\u2264": (r"$\leq$", r"\leq "),
    "\u2265": (r"$\geq$", r"\geq "),
    "\u00d7": (r"$\times$", r"\times "),
    "\u2248": (r"$\approx$", r"\approx "),
    "\u2192": (r"$\rightarrow$", r"\rightarrow "),
    "\u2190": (r"$\leftarrow$", r"\leftarrow "),
    "\u00b7": (r"$\cdot$", r"\cdot "),
    "\u00b1": (r"$\pm$", r"\pm "),
    "\u2260": (r"$\neq$", r"\neq "),
    "\u221e": (r"$\infty$", r"\infty "),
    "\u00b0": (r"$^{\circ}$", r"^{\circ}"),
    "\u00b9": (r"\textsuperscript{1}", r"^{1}"),
    "\u00b2": (r"\textsuperscript{2}", r"^{2}"),
    "\u00b3": (r"\textsuperscript{3}", r"^{3}"),
    "\u00b5": (r"$\mu$", r"\mu "),        # micro sign
    # Greek (lowercase + the capitals that show up in physics prose)
    "\u03b1": (r"$\alpha$", r"\alpha "),
    "\u03b2": (r"$\beta$", r"\beta "),
    "\u03b3": (r"$\gamma$", r"\gamma "),
    "\u03b4": (r"$\delta$", r"\delta "),
    "\u03b5": (r"$\varepsilon$", r"\varepsilon "),
    "\u03b6": (r"$\zeta$", r"\zeta "),
    "\u03b7": (r"$\eta$", r"\eta "),
    "\u03b8": (r"$\theta$", r"\theta "),
    "\u03ba": (r"$\kappa$", r"\kappa "),
    "\u03bb": (r"$\lambda$", r"\lambda "),
    "\u03bc": (r"$\mu$", r"\mu "),
    "\u03bd": (r"$\nu$", r"\nu "),
    "\u03c0": (r"$\pi$", r"\pi "),
    "\u03c1": (r"$\rho$", r"\rho "),
    "\u03c3": (r"$\sigma$", r"\sigma "),
    "\u03c4": (r"$\tau$", r"\tau "),
    "\u03c6": (r"$\phi$", r"\phi "),
    "\u03c7": (r"$\chi$", r"\chi "),
    "\u03c8": (r"$\psi$", r"\psi "),
    "\u03c9": (r"$\omega$", r"\omega "),
    "\u0394": (r"$\Delta$", r"\Delta "),
    "\u03a9": (r"$\Omega$", r"\Omega "),
    "\u03a3": (r"$\Sigma$", r"\Sigma "),
}


def escape_latex(text: str, *, math: bool = False) -> str:
    """Escape one run of plain text for LaTeX in a single character pass.

    math=True is for the inside of an author-written $...$ span: specials are
    left alone (they are meaningful math) and unicode maps to bare macros.
    Unmapped non-ASCII passes through — modern engines read UTF-8 input and
    letters like e-acute survive; anything an engine cannot set surfaces in
    the bounded compile-error tail, never silently.
    """
    out = []
    for ch in text:
        if not math and ch in _SPECIALS:
            out.append(_SPECIALS[ch])
        elif ch in _UNICODE:
            out.append(_UNICODE[ch][1 if math else 0])
        else:
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# inline markdown -> LaTeX
# ---------------------------------------------------------------------------

_INLINE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<math>\$[^$]+\$)"
    r"|(?P<bold>\*\*.+?\*\*)"
    r"|(?P<ital>\*[^\s*][^*]*?\*)"
)


def inline_to_latex(text: str) -> str:
    """Convert one line's inline markdown: `code`, $math$, **bold**, *italic*."""
    out = []
    pos = 0
    for m in _INLINE.finditer(text):
        out.append(escape_latex(text[pos:m.start()]))
        tok = m.group(0)
        if m.lastgroup == "code":
            out.append(r"\texttt{" + escape_latex(tok[1:-1]) + "}")
        elif m.lastgroup == "math":
            out.append("$" + escape_latex(tok[1:-1], math=True) + "$")
        elif m.lastgroup == "bold":
            out.append(r"\textbf{" + inline_to_latex(tok[2:-2]) + "}")
        else:
            out.append(r"\emph{" + inline_to_latex(tok[1:-1]) + "}")
        pos = m.end()
    out.append(escape_latex(text[pos:]))
    return "".join(out)


# ---------------------------------------------------------------------------
# block-level conversion
# ---------------------------------------------------------------------------

_IMAGE_LINE = re.compile(r"^!\[(?P<caption>.*)\]\((?P<path>[^)]+)\)\s*$")
_CAPTION_PREFIX = re.compile(r"^\s*Figure\s+\d+\s*[.:]\s*", re.IGNORECASE)
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_ORDERED_ITEM = re.compile(r"^\d+[.)]\s+")
_HRULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")

_HEADINGS = {2: "section", 3: "subsection", 4: "subsubsection", 5: "paragraph"}

_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{microtype}
\usepackage[hidelinks]{hyperref}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.5\baselineskip}
\begin{document}
"""


def _split_row(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table_to_latex(lines: list) -> str:
    """Pipe table -> non-floating booktabs tabularx (stays where the text put it).

    The column whose content runs longest becomes the wrapping X column; the
    rest stay left-aligned, so long quantity descriptions wrap while values
    (even 16-significant-digit ones) stay on one line.
    """
    header = _split_row(lines[0])
    body = [_split_row(ln) for ln in lines[2:]]
    ncols = len(header)
    rows = [(r + [""] * ncols)[:ncols] for r in body]

    widths = [max([len(header[i])] + [len(r[i]) for r in rows]) for i in range(ncols)]
    x_col = widths.index(max(widths))
    colspec = "".join("X" if i == x_col else "l" for i in range(ncols))

    def _row(cells, bold=False):
        rendered = [inline_to_latex(c) for c in cells]
        if bold:
            rendered = [r"\textbf{" + c + "}" for c in rendered]
        return " & ".join(rendered) + r" \\"

    out = [
        r"\medskip",
        r"\noindent",
        r"{\small",
        r"\begin{tabularx}{\textwidth}{" + colspec + "}",
        r"\toprule",
        _row(header, bold=True),
        r"\midrule",
    ]
    out.extend(_row(r) for r in rows)
    out.extend([r"\bottomrule", r"\end{tabularx}", "}", r"\medskip", ""])
    return "\n".join(out)


def _figure_to_latex(caption: str, path: str, exists: bool) -> str:
    caption_tex = inline_to_latex(_CAPTION_PREFIX.sub("", caption).strip())
    if exists:
        body = r"\includegraphics[width=\linewidth]{" + path + "}"
    else:
        body = (
            r"\fbox{\parbox{0.9\linewidth}{\centering\vspace{2em}"
            r"\texttt{missing figure: " + escape_latex(path) + r"}"
            r"\vspace{2em}}}"
        )
    lines = [r"\begin{figure}[htbp]", r"\centering", body]
    if caption_tex:
        lines.append(r"\caption{" + caption_tex + "}")
    lines.extend([r"\end{figure}", ""])
    return "\n".join(lines)


def markdown_to_latex(md_text: str,
                      figure_exists: Optional[Callable[[str], bool]] = None) -> dict:
    """Convert a whole paper.md to a complete LaTeX document.

    figure_exists decides whether an embedded image file is present (defaults
    to "yes" for every figure, so the pure conversion needs no disk). Returns
    {tex, title, figures, missing_figures}.
    """
    if figure_exists is None:
        figure_exists = lambda name: True  # noqa: E731

    lines = md_text.splitlines()
    body: list = []
    title = None
    figures: list = []
    missing: list = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # fenced code block
        if stripped.startswith("```"):
            block = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1  # closing fence (or EOF)
            body.append("\\begin{verbatim}\n" + "\n".join(block) + "\n\\end{verbatim}\n")
            continue

        # headings
        m = re.match(r"^(#{1,5})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1 and title is None:
                title = text
            else:
                cmd = _HEADINGS.get(max(level, 2), "paragraph")
                body.append("\\" + cmd + "*{" + inline_to_latex(text) + "}\n")
            i += 1
            continue

        # figure on its own line
        m = _IMAGE_LINE.match(stripped)
        if m:
            path = m.group("path").strip()
            exists = bool(figure_exists(path))
            figures.append(path)
            if not exists:
                missing.append(path)
            body.append(_figure_to_latex(m.group("caption"), path, exists))
            i += 1
            continue

        # pipe table (header row + separator row)
        if stripped.startswith("|") and i + 1 < n and _TABLE_SEP.match(lines[i + 1].strip()):
            tbl = [stripped, lines[i + 1].strip()]
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            body.append(_table_to_latex(tbl))
            continue

        # horizontal rule (after the table check: separators live inside tables)
        if _HRULE.match(stripped):
            body.append("\\medskip\\noindent\\hrulefill\\medskip\n")
            i += 1
            continue

        # bullet list
        if stripped.startswith(("- ", "* ")):
            items = []
            while i < n and lines[i].strip().startswith(("- ", "* ")):
                item = lines[i].strip()[2:].strip()
                i += 1
                while i < n and lines[i].strip() and lines[i].startswith((" ", "\t")) \
                        and not lines[i].strip().startswith(("- ", "* ")):
                    item += " " + lines[i].strip()
                    i += 1
                items.append(item)
            body.append("\\begin{itemize}\n"
                        + "\n".join(r"\item " + inline_to_latex(it) for it in items)
                        + "\n\\end{itemize}\n")
            continue

        # ordered list
        if _ORDERED_ITEM.match(stripped):
            items = []
            while i < n and _ORDERED_ITEM.match(lines[i].strip()):
                item = _ORDERED_ITEM.sub("", lines[i].strip())
                i += 1
                while i < n and lines[i].strip() and lines[i].startswith((" ", "\t")) \
                        and not _ORDERED_ITEM.match(lines[i].strip()):
                    item += " " + lines[i].strip()
                    i += 1
                items.append(item)
            body.append("\\begin{enumerate}\n"
                        + "\n".join(r"\item " + inline_to_latex(it) for it in items)
                        + "\n\\end{enumerate}\n")
            continue

        # blockquote
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            body.append("\\begin{quote}\n" + inline_to_latex(" ".join(quote))
                        + "\n\\end{quote}\n")
            continue

        # paragraph: gather until blank line or the start of any block above
        para = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", "|", "- ", "* ", ">", "```"))
                    or _IMAGE_LINE.match(nxt) or _ORDERED_ITEM.match(nxt)
                    or _HRULE.match(nxt)):
                break
            para.append(nxt)
            i += 1
        body.append(inline_to_latex(" ".join(para)) + "\n")

    parts = [_PREAMBLE]
    if title:
        parts.append("\\begin{center}\n{\\LARGE\\bfseries "
                     + inline_to_latex(title) + "\\par}\n\\end{center}\n"
                     "\\vspace{0.5\\baselineskip}\n")
    parts.append("\n".join(body))
    parts.append("\\end{document}\n")
    return {
        "tex": "\n".join(parts),
        "title": title,
        "figures": figures,
        "missing_figures": missing,
    }


# ---------------------------------------------------------------------------
# toolchain discovery + compilation
# ---------------------------------------------------------------------------

_ENGINE_ORDER = ["tectonic", "latexmk", "pdflatex", "xelatex", "lualatex"]
_EXTRA_BIN_DIRS = [Path("/Library/TeX/texbin")]  # standard MacTeX location

NO_ENGINE_MESSAGE = (
    "no LaTeX engine found (looked for "
    + ", ".join(_ENGINE_ORDER)
    + " on PATH and in "
    + ", ".join(str(d) for d in _EXTRA_BIN_DIRS)
    + "). paper.tex was written; to get a PDF install a TeX distribution "
    "(macOS: `brew install --cask basictex` or `brew install tectonic`) "
    "and re-run, or compile paper.tex on another machine."
)


def find_latex_engine() -> Optional[str]:
    """Absolute path of the first available engine, or None."""
    for name in _ENGINE_ORDER:
        path = shutil.which(name)
        if path:
            return path
        for d in _EXTRA_BIN_DIRS:
            cand = d / name
            if cand.is_file():
                return str(cand)
    return None


def _engine_argv(engine: str, tex_name: str) -> list:
    base = Path(engine).name
    if base == "tectonic":
        return [engine, tex_name]
    if base == "latexmk":
        return [engine, "-pdf", "-interaction=nonstopmode", "-halt-on-error", tex_name]
    return [engine, "-interaction=nonstopmode", "-halt-on-error", tex_name]


def _bounded_tail(text: str, max_lines: int = 40, max_chars: int = 3000) -> str:
    tail = "\n".join(text.splitlines()[-max_lines:])
    return tail[-max_chars:]


def compile_tex(tex_path: Path, engine: Optional[str] = None,
                timeout_s: int = 300) -> dict:
    """Compile a .tex file in its own directory (so relative figure paths
    resolve). Returns {pdf_path, engine} or {error} — never raises for a
    missing toolchain or a failed compile."""
    engine = engine or find_latex_engine()
    if engine is None:
        return {"error": NO_ENGINE_MESSAGE}
    argv = _engine_argv(engine, tex_path.name)
    try:
        proc = subprocess.run(
            argv, cwd=str(tex_path.parent), timeout=timeout_s,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"LaTeX compile timed out after {timeout_s}s ({argv[0]})"}
    except OSError as exc:
        return {"error": f"could not run LaTeX engine {argv[0]}: {exc}"}
    pdf = tex_path.with_suffix(".pdf")
    if proc.returncode != 0 or not pdf.is_file():
        return {
            "error": "LaTeX compilation failed (engine "
                     + Path(engine).name
                     + f", exit {proc.returncode}); log tail:\n"
                     + _bounded_tail(proc.stdout + "\n" + proc.stderr)
        }
    return {"pdf_path": str(pdf), "engine": Path(engine).name}


# ---------------------------------------------------------------------------
# top-level entry
# ---------------------------------------------------------------------------

def typeset_paper(target, *, compile_pdf: bool = True,
                  engine: Optional[str] = None) -> dict:
    """studies/<id>/ (or a direct paper.md path) -> paper.tex [+ paper.pdf].

    Always writes paper.tex beside the markdown when conversion succeeds.
    Result: {tex_path, pdf_path|None, engine|None, figures, missing_figures}
    plus an "error" key when the PDF could not be produced (missing toolchain
    or failed compile) — the .tex still stands on its own in that case.
    """
    target = Path(target)
    md_path = target / "paper.md" if target.is_dir() else target
    if not md_path.is_file():
        return {"error": f"no paper found at {md_path}"}

    md_text = md_path.read_text(encoding="utf-8")
    paper_dir = md_path.parent
    conv = markdown_to_latex(
        md_text, figure_exists=lambda name: (paper_dir / name).is_file()
    )
    tex_path = md_path.with_suffix(".tex")
    tex_path.write_text(conv["tex"], encoding="utf-8")

    result = {
        "tex_path": str(tex_path),
        "pdf_path": None,
        "engine": None,
        "figures": conv["figures"],
        "missing_figures": conv["missing_figures"],
    }
    if not compile_pdf:
        return result
    compiled = compile_tex(tex_path, engine=engine)
    if "error" in compiled:
        result["error"] = compiled["error"]
    else:
        result["pdf_path"] = compiled["pdf_path"]
        result["engine"] = compiled["engine"]
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Typeset a study's paper.md into paper.tex + paper.pdf."
    )
    ap.add_argument("target", help="study directory (containing paper.md) or a paper.md path")
    ap.add_argument("--tex-only", action="store_true",
                    help="emit paper.tex without attempting to compile a PDF")
    args = ap.parse_args(argv)
    result = typeset_paper(args.target, compile_pdf=not args.tex_only)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
