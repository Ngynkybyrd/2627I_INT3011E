# README CLI check

Date: 2026-10-16 (Asia/Saigon). This is a one-puzzle CLI smoke check, not a
benchmark.

## Help/parser check

Command, from `D:\KHMT\Project solo`:

```powershell
$env:PYTHONPATH='src'
& '.\.venv\Scripts\python.exe' -B -m sudoku --help
```

Exit code 0. Help listed methods `sat,cpsat,gurobi,cplex_mip,cpoptimizer,highs`,
encodings `pairwise,seqcounter,bitwise`, and `--cutoff SECONDS`.

## Real path-with-spaces solve

Command:

```powershell
$env:PYTHONPATH='src'
& '.\.venv\Scripts\python.exe' -B -m sudoku 'diagnostics\cli\puzzle with spaces.json' --method sat --encoding seqcounter --cutoff 5
```

Result: exit code 0; `SAT`; `validation.valid=true`; 4×4 solution returned with
block separators. The output JSON reports build 0.0014481 s, solve
0.0000649 s, total 0.0015130 s. These are a single smoke run and must not be
used as benchmark evidence. Existing CLI handoff artifacts are
`diagnostics/cli/stdout.json` and `diagnostics/cli/table.txt`.

The CLI uses adapter native/cooperative cutoff behavior only. A hard Windows
process-tree guard belongs to the benchmark runner and is not implemented here.
