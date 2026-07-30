# Complete-control disposable-world probe

The template at `native/probes/STAGE_PROBE_TEMPLATE.json` is the minimum acceptance matrix. Both Windows and Linux require their own completed report.

## Coverage

The probe covers:

- world CRUD, IDs, byte counts, bulk set, rename, flush, and restart;
- online-player CRUD and reconnect;
- offline-player read/write, later join, and restart;
- loaded-entity CRUD;
- stored-entity read/write, chunk activation, and restart;
- every supported player item section;
- block-container and dropped-item stacks;
- client slot refresh and stale slot conflicts;
- item stackability/custom-data safeguards;
- supported block property CRUD, chunk reload, restart, replacement cleanup;
- property and collection copy/move;
- behavior-pack UUID migration;
- export/import;
- plugin isolation and raw administration;
- cross-target transactions and rollback;
- external Script API set/remove/clear observation and cancellation;
- hook recursion/load/rollback suppression;
- complete audits;
- no direct live LevelDB editing;
- shutdown flush and forced-crash recovery.

## Evidence

Each result should include an operator, timestamp, exact server/client versions, world backup identifier, expected result, observed result, and supporting log or hash. Do not include private player records or full database dumps in the public report.

Validate a completed report with:

```bash
python tools/validate_stage_probe_report.py \
  native/probes/linux-x64-1.26.33.1-stage-probe.json
```
