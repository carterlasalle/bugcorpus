# Detector ladder — cheapest adequate engine wins
<!-- trace:v1 id=doc.bugcorpus-ladder work=WORK-BUG-ZJBDCZZ0 -->

0. existing (ruff/mypy/...) — record the rule, add a stay-enabled check
1. lexical — stable textual structure only (forbidden APIs)
2. ast-grep — syntax-tree relationships
3. semgrep — semantic structural patterns
4. semgrep-taint — source → propagation → sink
5. codeql — interprocedural / cross-file / path-sensitive
6. pysa — project-specific taint models for Python
7. custom AST analyzer (`bugcorpus.sdk`: traversal, ranges, fingerprints)
8. purpose-built searcher in `.bugcorpus/detectors/custom/` with a documented
   minimum semantic model (what it needs vs what it skips).

Custom contract: `python entrypoint --format json <files...>` prints a JSON
list of findings. Never let a crash read as clean — errors are `detector-error`.
