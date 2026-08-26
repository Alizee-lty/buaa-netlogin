#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-buaa-netlogin.service}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_PATH="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
LOG_DIR="${SCRIPT_DIR}/logs"
ENV_PATH="${HOME}/.config/buaa-netlogin.env"

usage() {
  cat <<EOF
Usage:
  ./linux_autostart.sh install <username> <password> [interval_seconds]
  ./linux_autostart.sh status
  ./linux_autostart.sh uninstall

Examples:
  ./linux_autostart.sh install by123456 'your!password'
  ./linux_autostart.sh install by123456 'your!password' 30

Notes:
  - This script uses systemd user services.
  - interval_seconds controls how often the login script checks network status. Default: 5.
  - Passwords with special characters should be wrapped in single quotes.
  - Credentials are stored in ${ENV_PATH}.
EOF
}

require_linux() {
  if [[ "$(uname)" != "Linux" ]]; then
    echo "This autostart script only supports Linux systemd." >&2
    exit 1
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl was not found. This script requires systemd." >&2
    exit 1
  fi
}

find_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "${PYTHON_BIN}"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  echo "python3 was not found. Install Python3 first." >&2
  exit 1
}

systemd_escape_env_value() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

validate_interval() {
  local interval="$1"
  if ! [[ "${interval}" =~ ^[1-9][0-9]*$ ]]; then
    echo "interval_seconds must be a positive integer, got: ${interval}" >&2
    exit 1
  fi
}

install_service() {
  if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
    exit 1
  fi

  local username="$1"
  local password="$2"
  local interval="${3:-5}"
  local python_bin
  validate_interval "${interval}"
  python_bin="$(find_python)"

  mkdir -p "${SYSTEMD_USER_DIR}" "${LOG_DIR}" "$(dirname "${ENV_PATH}")"

  {
    printf 'user=%s\n' "$(systemd_escape_env_value "${username}")"
    printf 'pwd=%s\n' "$(systemd_escape_env_value "${password}")"
    printf 'interval=%s\n' "$(systemd_escape_env_value "${interval}")"
  } > "${ENV_PATH}"
  chmod 600 "${ENV_PATH}"

  cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=BUAA campus network auto login
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${ENV_PATH}
ExecStart=${python_bin} ${SCRIPT_DIR}/main_login_modern.py
Restart=always
RestartSec=5
StandardOutput=append:${LOG_DIR}/netlogin.out.log
StandardError=append:${LOG_DIR}/netlogin.err.log

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable --now "${SERVICE_NAME}"

  echo "Installed and started ${SERVICE_NAME}."
  echo "Interval: ${interval} seconds"
  echo "Service: ${SERVICE_PATH}"
  echo "Env: ${ENV_PATH}"
  echo "Logs: ${LOG_DIR}/netlogin.out.log and ${LOG_DIR}/netlogin.err.log"
}

uninstall_service() {
  systemctl --user disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
  rm -f "${SERVICE_PATH}" "${ENV_PATH}"
  systemctl --user daemon-reload
  echo "Uninstalled ${SERVICE_NAME}."
}

status_service() {
  systemctl --user status "${SERVICE_NAME}"
}

main() {
  require_linux

  local action="${1:-}"
  if [[ -z "${action}" ]]; then
    usage
    exit 1
  fi
  shift

  case "${action}" in
    install)
      install_service "$@"
      ;;
    uninstall)
      uninstall_service
      ;;
    status)
      status_service
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
