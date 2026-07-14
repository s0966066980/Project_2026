# Local Operations — Single-Store Pilot

## Profiles

| Profile | Purpose |
| --- | --- |
| `local-dev` | Fast JSON/dev coding (not pilot) |
| `local-postgres` | Postgres commercial path, soft security |
| `local-pilot` | Single-store pilot: postgres SoT, security enforced, no demo routes |
| `local-full` | Postgres + redis + strict flags |

## Commands

```bash
# Core install
bash scripts/local/setup.sh --profile local-pilot

# Optional AI extras
bash scripts/local/setup.sh --profile local-pilot --with-ai

# Bootstrap one tenant/store/admin/device (idempotent)
cd UI_API
export ADMIN_BOOTSTRAP_PASSWORD='...'   # never commit
python backend/scripts/bootstrap_local_pilot.py --tenant-name "Owner" --store-name "Store A"

bash scripts/local/doctor.sh
APP_PROFILE=local-pilot bash scripts/local/start.sh
bash scripts/local/status.sh
bash scripts/local/stop.sh

bash scripts/local/test_fast.sh
bash scripts/local/test_full.sh
```

## Ports

- Kiosk: `http://127.0.0.1:9000/kiosk`
- Admin: `http://127.0.0.1:9001/admin`
- Live/Ready: `/live`, `/ready`

## Data paths

- Runtime: `runtime/{pids,logs,object_storage,tmp,state}`
- Tests: temporary dirs only (never rewrite tracked `learning_data/settings.json`)
- Commercial data: PostgreSQL only under `local-pilot`

## Payment / POS

Manual adapters: order may be `pending_manual_payment` / `pending_manual_entry`. No fake capture or fake POS ACK.
