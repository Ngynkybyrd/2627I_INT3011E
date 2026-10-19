# Preflight note

The first invocation of pilot_protocol.py stopped during selection with
StopIteration: the diagnostic script expected the source label `public`, while
the frozen manifest uses `public_sudoku_exchange_hard`. No plan directory or
solver job had been created. Corrected only that diagnostic-script predicate;
the intended first public B16 ID remains public-se-hard-L069940. No dataset,
scope, runtime-based selection or adapter change was made. The subsequent
pilot-20261016-01 invocation is the first and only executed pilot batch.

The suite preceding this pilot was rerun after adding the SAT-evidence
disagreement stop guard: full-suite-pilot-01 had 617 passes, and
full-suite-pilot-02 has 618 passes including the new regression. Both XML files
are retained; neither is a main-experiment code freeze.
