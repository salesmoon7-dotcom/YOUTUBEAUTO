# Phase1 Bootstrap Execution

- Root: D:/YOUTUBEAUTO
- Includes runtime_v2 supervisor skeleton
- CLI modes: `python -m runtime_v2.cli --once`, `python -m runtime_v2.cli --selftest`
- GUI payload fields: `execution_env`, `schema_version`, `runtime`, `run_id`, `mode`, `stage`, `exit_code`, `status`
- n8n callback fields: `execution_env`, `schema_version`, `callback_url`, `ok`, `runtime`, `run_id`, `mode`, `exit_code`, `status`
- Callback mock: `--callback-url https://n8n.example/webhook --callback-mock-out system/runtime_v2/evidence/callback.json`
- Validation: `python -c "from pathlib import Path; import py_compile; [py_compile.compile(str(p), doraise=True) for p in Path('runtime_v2').rglob('*.py')]"`
- Validation workdir: `D:/YOUTUBEAUTO`
