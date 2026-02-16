#!/usr/bin/env python3
"""Extract readable body text from a LaTeX file.

Extracts content between \\begin{document} and \\end{document},
strips comments, labels, and other noise. Preserves all semantic
content including math, citations, and section structure.

Usage: python3 extract_latex_body.py <tex_file>
Output: Cleaned body text to stdout
"""
import re
import sys


def extract_body(tex_path: str) -> str:
    with open(tex_path) as f:
        content = f.read()

    # Extract body between \begin{document} and \end{document}
    m = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', content, re.DOTALL)
    body = m.group(1) if m else content

    # Strip LaTeX comments (% to end of line, but not \%)
    # Use odd-backslash lookbehind: \% is escaped (keep), \\% is linebreak+comment (strip)
    body = re.sub(r'(?<!\\)(\\\\)*%.*', r'\1', body)

    # Strip noise commands
    body = re.sub(r'\\maketitle', '', body)
    body = re.sub(r'\\label\{[^}]*\}', '', body)

    # Collapse multiple blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)

    return body.strip()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 extract_latex_body.py <tex_file>", file=sys.stderr)
        sys.exit(1)
    print(extract_body(sys.argv[1]))
