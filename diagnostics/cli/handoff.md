# CLI-001..003 handoff

Implemented the one-puzzle CLI in `src/sudoku/cli.py`, exposed as
`python -m sudoku` through `src/sudoku/__main__.py`. It selects SAT or any
baseline method, accepts SAT encoding and a positive finite cutoff, delegates
to the production adapters, prints block-separated grids to stderr, and emits
the complete JSON-compatible `SolveResult` on stdout (optionally also saved
with `--json-output`). Input file/JSON/schema failures produce
`INVALID_INPUT`; adapter statuses such as `UNAVAILABLE` and `LICENSE_LIMIT`
are preserved. No solver/checker code or dependencies were changed.

Focused tests: 10 passed with
`python -B -m pytest -q -p no:cacheprovider --basetemp diagnostics/cli/pytest-temp-cli-r1 tests/test_cli.py`.
The first attempt using pytest's default temporary directory failed before
test setup because that Windows sandbox temp location was not writable; the
workspace-local basetemp resolved it.

Real path-with-spaces smoke command:

```powershell
$env:PYTHONPATH='src'
& '.\.venv\Scripts\python.exe' -B -m sudoku 'diagnostics\cli\puzzle with spaces.json' --method sat --encoding seqcounter --cutoff 5 --json-output 'diagnostics\cli\result.json'
```

Result: SAT, independent validation passed, block separators printed, JSON
saved in `result.json`. Captured outputs are `stdout.json` and `table.txt`.
Cutoff behavior remains the adapters' cooperative/native behavior; this CLI
does not claim a hard Windows timeout. CLI-004..006 remain out of scope here.
