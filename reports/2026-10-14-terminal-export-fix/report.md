# Terminal queue export fix — 2026-10-14

Full SAR trace inspection corrects the reported initial diagnosis. The first
failure is its composite-stage acceptance adapter requiring redundant record_dir.
Later taskdb YAML export resolves an unexecuted bindings reference and masks it.
SAR received precise helper feedback; no scientific source was changed centrally.

_atomic_write_yaml now serializes OmegaConf nodes with resolve=False. This exports
the stored invocation faithfully rather than evaluating it against today's files.
The added real SQLite queue regression exports a failed pipeline whose downstream
producer never existed and checks both argument and data-snapshot expressions.

Validation: PYTHONPATH set explicitly to the validation checkout;
pytest -q tests/test_task_export_deferred.py tests/test_pipeline_tasks.py:
22 passed in 13.49 seconds. An initial command without PYTHONPATH tested installed
0.9.2 instead, reproduced the export failure and unrelated package/test-target
import failures; rerun used the intended branch. No installed environment changed.

Result-file and source-capture compatibility proposals are in
../../docs/urgent_fix_decisions.md. They remain proposals pending user agreement.
