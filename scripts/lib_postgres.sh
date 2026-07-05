#!/usr/bin/env bash

# Shared PostgreSQL bootstrap for local Ubuntu development.
# shellcheck shell=bash

postgres_bool_enabled() {
  local value="${1:-true}"
  case "${value,,}" in
    0|false|no|off) return 1 ;;
    *) return 0 ;;
  esac
}

postgres_sql_escape() {
  printf "%s" "$1" | sed "s/'/''/g"
}

postgres_require_safe_identifier() {
  local value="$1" label="$2"
  if [[ ! "$value" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "❌ ${label} 只能使用英文字母、數字與底線，且不能以數字開頭：$value"
    return 1
  fi
}

postgres_install_ubuntu_package() {
  if command -v psql >/dev/null 2>&1 && command -v pg_isready >/dev/null 2>&1; then
    return 0
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    echo "❌ 找不到 apt-get；本腳本只支援 Ubuntu/Debian 本機 PostgreSQL 安裝。"
    return 1
  fi

  if ! postgres_bool_enabled "${POSTGRES_AUTO_INSTALL:-true}"; then
    echo "❌ PostgreSQL 尚未安裝，且 POSTGRES_AUTO_INSTALL=false。"
    echo "   請手動執行：sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib"
    return 1
  fi

  echo "📦 安裝 Ubuntu PostgreSQL 套件（需要 sudo 密碼）…"
  sudo apt-get update
  sudo apt-get install -y postgresql postgresql-contrib
}

postgres_start_service() {
  if systemctl list-unit-files postgresql.service >/dev/null 2>&1; then
    sudo systemctl enable --now postgresql
  else
    sudo service postgresql start
  fi

  local i=0
  while ! pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT:-5432}" >/dev/null 2>&1; do
    i=$((i + 1))
    if [[ $i -gt 40 ]]; then
      echo "❌ PostgreSQL 等待逾時（127.0.0.1:${POSTGRES_PORT:-5432} 未就緒）"
      return 1
    fi
    sleep 0.5
  done
}

postgres_ensure_role_and_database() {
  local user="${POSTGRES_USER:-ui_api_user}"
  local password="${POSTGRES_PASSWORD:-ui_api_password}"
  local database="${POSTGRES_DB:-ui_api_migration_test}"

  postgres_require_safe_identifier "$user" "POSTGRES_USER"
  postgres_require_safe_identifier "$database" "POSTGRES_DB"

  local escaped_password
  escaped_password="$(postgres_sql_escape "$password")"

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${user}'" | grep -q 1; then
    echo "🧑‍💻 建立 PostgreSQL user：$user"
    sudo -u postgres psql -c "CREATE USER ${user} WITH PASSWORD '${escaped_password}';"
  else
    sudo -u postgres psql -c "ALTER USER ${user} WITH PASSWORD '${escaped_password}';" >/dev/null
  fi

  POSTGRES_DATABASE_CREATED=0
  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${database}'" | grep -q 1; then
    echo "🗄️  建立 PostgreSQL database：$database"
    sudo -u postgres createdb -O "$user" "$database"
    POSTGRES_DATABASE_CREATED=1
  fi
  export POSTGRES_DATABASE_CREATED

  sudo -u postgres psql -d "$database" -c "GRANT ALL PRIVILEGES ON DATABASE ${database} TO ${user};" >/dev/null
  sudo -u postgres psql -d "$database" -c "GRANT ALL ON SCHEMA public TO ${user};" >/dev/null
}

postgres_ensure_python_driver() {
  local ui_python="$1"
  local repo_root="$2"

  if "$ui_python" -c "import psycopg" >/dev/null 2>&1; then
    return 0
  fi

  if ! postgres_bool_enabled "${POSTGRES_AUTO_INSTALL_PYTHON_DEPS:-true}"; then
    echo "❌ Python 環境缺少 psycopg，且 POSTGRES_AUTO_INSTALL_PYTHON_DEPS=false。"
    echo "   請手動執行：$ui_python -m pip install 'psycopg[binary]'"
    return 1
  fi

  echo "📦 安裝 Python PostgreSQL driver：psycopg[binary]"
  "$ui_python" -m pip install "psycopg[binary]"
}

postgres_export_app_env() {
  local user="${POSTGRES_USER:-ui_api_user}"
  local password="${POSTGRES_PASSWORD:-ui_api_password}"
  local database="${POSTGRES_DB:-ui_api_migration_test}"
  local host="${POSTGRES_HOST:-127.0.0.1}"
  local port="${POSTGRES_PORT:-5432}"

  export POSTGRES_USER="$user"
  export POSTGRES_PASSWORD="$password"
  export POSTGRES_DB="$database"
  export POSTGRES_HOST="$host"
  export POSTGRES_PORT="$port"
  export MEMBER_STORAGE_BACKEND="${MEMBER_STORAGE_BACKEND:-postgres}"
  export DATABASE_URL="${DATABASE_URL:-postgresql://${user}:${password}@${host}:${port}/${database}}"
}

postgres_init_app_schema() {
  local ui_python="$1"
  local repo_root="$2"

  echo "🧱 初始化 PostgreSQL schema …"
  (
    cd "$repo_root/UI_API"
    PYTHONPATH="$repo_root/UI_API/backend:$repo_root/UI_API${PYTHONPATH:+:$PYTHONPATH}" \
      "$ui_python" -c "from repositories import postgres_utils; postgres_utils.init_schema()"
  )
}

postgres_run_migration_and_validation() {
  local ui_python="$1"
  local repo_root="$2"

  echo "🧪 執行會員資料 migration 並驗證 PostgreSQL 狀態…"
  (
    cd "$repo_root/UI_API"
    PYTHONPATH="$repo_root/UI_API/backend:$repo_root/UI_API${PYTHONPATH:+:$PYTHONPATH}" \
      "$ui_python" backend/scripts/migrate_member_storage.py --apply
    PYTHONPATH="$repo_root/UI_API/backend:$repo_root/UI_API${PYTHONPATH:+:$PYTHONPATH}" \
      "$ui_python" backend/scripts/validate_member_postgres_migration.py --allow-extra --smoke-write
  )
}

prepare_local_postgres() {
  local ui_python="$1"
  local repo_root="$2"

  if ! postgres_bool_enabled "${POSTGRES_ENABLED:-true}"; then
    echo "ℹ️  POSTGRES_ENABLED=false，略過本機 PostgreSQL 準備。"
    return 0
  fi

  postgres_export_app_env
  postgres_install_ubuntu_package
  postgres_start_service
  postgres_ensure_role_and_database
  postgres_ensure_python_driver "$ui_python" "$repo_root"
  postgres_init_app_schema "$ui_python" "$repo_root"

  if postgres_bool_enabled "${POSTGRES_RUN_MIGRATION_ON_START:-false}"; then
    postgres_run_migration_and_validation "$ui_python" "$repo_root"
  elif [[ "${POSTGRES_DATABASE_CREATED:-0}" == "1" ]] && postgres_bool_enabled "${POSTGRES_MIGRATE_NEW_DATABASE:-true}"; then
    echo "ℹ️  偵測到新建 PostgreSQL database，執行首次 JSON migration。"
    postgres_run_migration_and_validation "$ui_python" "$repo_root"
  else
    echo "ℹ️  PostgreSQL database 已存在，略過 JSON migration apply。"
  fi

  echo "✓ PostgreSQL 就緒：${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
}
