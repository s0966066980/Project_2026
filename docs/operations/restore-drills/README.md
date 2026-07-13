# Restore Drill Records

Store completed restore drill markdown records here.

Generate a dry-run shell with:

```bash
bash scripts/record_restore_drill.sh
```

Execute against an isolated target:

```bash
export DRILL_MODE=execute
export SOURCE_BACKUP=backups/postgres/<file>.dump
export TARGET_DATABASE_URL=postgresql://...isolated...
bash scripts/record_restore_drill.sh
```

Never commit real DATABASE_URL passwords or production dumps into this directory.
