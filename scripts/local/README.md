# Local orchestration (no Docker)

| Script | Purpose |
| --- | --- |
| `setup.sh` | venv + deps + runtime dirs |
| `doctor.sh` | PASS/WARN/FAIL diagnostics |
| `start.sh` | API + Worker (pid/log managed) |
| `status.sh` | Process/port/ready |
| `stop.sh` | Stop only pid-file processes |
| `test_fast.sh` | Daily fast gate |
| `test_full.sh` | Extended JSON regression |

```bash
bash scripts/local/setup.sh
bash scripts/local/doctor.sh
bash scripts/local/start.sh
bash scripts/local/status.sh
bash scripts/local/stop.sh
bash scripts/local/test_fast.sh
```

Optional:

- `START_WORKER=0 bash scripts/local/start.sh` — API only
- `READY_TIMEOUT_SEC=60` — readiness wait
- `APP_PORT=9000` — API port
