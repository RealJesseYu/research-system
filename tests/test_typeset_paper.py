"""Tests for tools/typeset_paper.py — the paper.md -> paper.tex/pdf post-processor.

Pure conversion is tested with no toolchain; the compile path is tested with a
stub "engine" script, and the missing-toolchain path asserts a clear message,
never a traceback.
"""

import os
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import typeset_paper as tp


MINI_PAPER = """# A Small Study — verified twice

## Abstract

We measured a glide ratio of **19.436** (≥ 12, i.e. ≤ the cap) at 3.6× spec,
with margin `e = 0.75` and drag CL²/(π·e·AR), moving 19.436 → 12.0.

## Results

| Quantity with a long descriptive name | Value | Reproduced |
|---|---|---|
| Glide ratio under the *literal* model | 22.16491648940609 | yes |
| Sink rate (m/s) at 50% of limit | 0.5938690036134637 | yes |

![Figure 1. Glide ratio through composition, at 99.8% of the limit.](fig1.png)

![Cost per additional solve.](fig_missing.png)

### Sub-analysis

- first bullet with **bold** and math $x \\leq y^2$
- second bullet

1. step one
2. step two

## Limitations

Everything is simulation — no flight test.
"""


class TestEscaping(unittest.TestCase):
    def test_specials_escaped(self):
        self.assertEqual(tp.escape_latex("a & b % c _ d # e"),
                         r"a \& b \% c \_ d \# e")

    def test_unicode_mapped_text_mode(self):
        self.assertEqual(tp.escape_latex("x ≤ y"), r"x $\leq$ y")
        self.assertEqual(tp.escape_latex("a — b"), "a --- b")
        self.assertEqual(tp.escape_latex("3.6× spec"), r"3.6$\times$ spec")
        self.assertEqual(tp.escape_latex("ψ"), r"$\psi$")

    def test_unicode_mapped_math_mode(self):
        self.assertEqual(tp.escape_latex("x ≤ y", math=True), r"x \leq  y")
        # math mode leaves specials alone
        self.assertEqual(tp.escape_latex("x^2_i", math=True), "x^2_i")


class TestInline(unittest.TestCase):
    def test_bold_italic_code(self):
        self.assertEqual(tp.inline_to_latex("**bold** and *ital* and `c_d`"),
                         r"\textbf{bold} and \emph{ital} and \texttt{c\_d}")

    def test_math_passthrough(self):
        self.assertEqual(tp.inline_to_latex("so $x \\leq y^2$ holds"),
                         "so $x \\leq y^2$ holds")

    def test_unicode_inside_code_span(self):
        self.assertEqual(tp.inline_to_latex("`CL²`"),
                         r"\texttt{CL\textsuperscript{2}}")

    def test_lone_asterisk_untouched(self):
        self.assertEqual(tp.inline_to_latex("12 * 3"), "12 * 3")

    def test_nested_emphasis_in_bold(self):
        self.assertEqual(tp.inline_to_latex("**a `b` c**"),
                         r"\textbf{a \texttt{b} c}")


class TestBlocks(unittest.TestCase):
    def convert(self, md, **kw):
        return tp.markdown_to_latex(md, **kw)

    def test_title_and_sections(self):
        out = self.convert(MINI_PAPER)
        self.assertEqual(out["title"], "A Small Study — verified twice")
        tex = out["tex"]
        self.assertIn(r"{\LARGE\bfseries A Small Study --- verified twice", tex)
        self.assertIn(r"\section*{Abstract}", tex)
        self.assertIn(r"\subsection*{Sub-analysis}", tex)

    def test_document_is_complete_and_ascii_safe(self):
        tex = self.convert(MINI_PAPER)["tex"]
        self.assertTrue(tex.startswith(r"\documentclass"))
        self.assertIn(r"\end{document}", tex)
        # every surveyed symbol must be mapped, not passed raw
        for ch in "≤≥×→≈·²βφψπ—–…":
            self.assertNotIn(ch, tex)

    def test_table_conversion(self):
        tex = self.convert(MINI_PAPER)["tex"]
        self.assertIn(r"\begin{tabularx}{\textwidth}{Xll}", tex)
        self.assertIn(r"\toprule", tex)
        self.assertIn(r"\textbf{Quantity with a long descriptive name}", tex)
        self.assertIn(r"\emph{literal} model & 22.16491648940609 & yes \\", tex)
        self.assertIn(r"50\% of limit", tex)

    def test_x_column_goes_to_longest(self):
        md = "| a | description column |\n|---|---|\n| 1 | a very very long descriptive cell |\n"
        tex = self.convert(md)["tex"]
        self.assertIn(r"\begin{tabularx}{\textwidth}{lX}", tex)

    def test_figures_present_and_missing(self):
        out = self.convert(MINI_PAPER,
                           figure_exists=lambda name: name == "fig1.png")
        tex = out["tex"]
        self.assertIn(r"\includegraphics[width=\linewidth]{fig1.png}", tex)
        # LaTeX numbers captions itself: the "Figure 1." prefix is stripped
        self.assertIn(r"\caption{Glide ratio through composition", tex)
        self.assertNotIn(r"\caption{Figure 1.", tex)
        # missing figure becomes a placeholder, not an \includegraphics
        self.assertIn("missing figure: fig\\_missing.png", tex)
        self.assertNotIn(r"\includegraphics[width=\linewidth]{fig_missing.png}", tex)
        self.assertEqual(out["figures"], ["fig1.png", "fig_missing.png"])
        self.assertEqual(out["missing_figures"], ["fig_missing.png"])

    def test_lists(self):
        tex = self.convert(MINI_PAPER)["tex"]
        self.assertIn(r"\begin{itemize}", tex)
        self.assertIn(r"\item first bullet with \textbf{bold} and math $x \leq y^2$", tex)
        self.assertIn(r"\begin{enumerate}", tex)
        self.assertIn(r"\item step one", tex)

    def test_no_fixed_structure_assumed(self):
        # a direct-answer write-up: no title, no sections, just prose
        out = self.convert("The answer is **42**, verified twice.\n")
        self.assertIsNone(out["title"])
        self.assertIn(r"The answer is \textbf{42}, verified twice.", out["tex"])

    def test_code_fence_verbatim(self):
        tex = self.convert("```\nx = 1 & y\n```\n")["tex"]
        self.assertIn("\\begin{verbatim}\nx = 1 & y\n\\end{verbatim}", tex)


class TestToolchain(unittest.TestCase):
    def _write_paper(self, tmp):
        d = Path(tmp)
        (d / "paper.md").write_text(MINI_PAPER, encoding="utf-8")
        (d / "fig1.png").write_bytes(b"\x89PNG fake")
        return d

    def test_tex_only(self):
        with TemporaryDirectory() as tmp:
            d = self._write_paper(tmp)
            result = tp.typeset_paper(d, compile_pdf=False)
            self.assertNotIn("error", result)
            self.assertTrue(Path(result["tex_path"]).is_file())
            self.assertIsNone(result["pdf_path"])
            self.assertEqual(result["missing_figures"], ["fig_missing.png"])

    def test_missing_toolchain_is_clear_message_not_traceback(self):
        with TemporaryDirectory() as tmp:
            d = self._write_paper(tmp)
            orig_find = tp.find_latex_engine
            tp.find_latex_engine = lambda: None
            try:
                result = tp.typeset_paper(d)
            finally:
                tp.find_latex_engine = orig_find
            self.assertIn("error", result)
            self.assertIn("no LaTeX engine found", result["error"])
            self.assertIn("paper.tex was written", result["error"])
            # the .tex is still delivered
            self.assertTrue(Path(result["tex_path"]).is_file())
            self.assertIsNone(result["pdf_path"])

    def test_stub_engine_produces_pdf(self):
        with TemporaryDirectory() as tmp:
            d = self._write_paper(tmp)
            stub = d / "fakelatex"
            stub.write_text("#!/bin/sh\n: > paper.pdf\n")
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            result = tp.typeset_paper(d, engine=str(stub))
            self.assertNotIn("error", result)
            self.assertEqual(result["pdf_path"], str(d / "paper.pdf"))

    def test_failing_engine_bounded_log_tail(self):
        with TemporaryDirectory() as tmp:
            d = self._write_paper(tmp)
            stub = d / "fakelatex"
            lines = "\n".join(f"echo log line {i}" for i in range(200))
            stub.write_text(f"#!/bin/sh\n{lines}\nexit 1\n")
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            result = tp.typeset_paper(d, engine=str(stub))
            self.assertIn("error", result)
            self.assertIn("LaTeX compilation failed", result["error"])
            self.assertIn("log line 199", result["error"])       # tail kept
            self.assertNotIn("log line 10\n", result["error"])   # head dropped

    def test_missing_paper(self):
        with TemporaryDirectory() as tmp:
            result = tp.typeset_paper(Path(tmp))
            self.assertIn("no paper found", result["error"])

    def test_cli_exit_codes(self):
        with TemporaryDirectory() as tmp:
            d = self._write_paper(tmp)
            self.assertEqual(tp.main([str(d), "--tex-only"]), 0)
            orig_find = tp.find_latex_engine
            tp.find_latex_engine = lambda: None
            try:
                self.assertEqual(tp.main([str(d)]), 1)
            finally:
                tp.find_latex_engine = orig_find

    def test_engine_argv_shapes(self):
        self.assertEqual(tp._engine_argv("/x/tectonic", "paper.tex"),
                         ["/x/tectonic", "paper.tex"])
        self.assertEqual(
            tp._engine_argv("/x/latexmk", "paper.tex"),
            ["/x/latexmk", "-pdf", "-interaction=nonstopmode",
             "-halt-on-error", "paper.tex"])
        self.assertEqual(
            tp._engine_argv("/x/pdflatex", "paper.tex"),
            ["/x/pdflatex", "-interaction=nonstopmode",
             "-halt-on-error", "paper.tex"])


if __name__ == "__main__":
    unittest.main()
