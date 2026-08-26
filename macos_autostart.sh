#!/usr/bin/env bash
set -euo pipefail

LABEL="${LABEL:-edu.buaa.netlogin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${SCRIPT_DIR}/logs"
STDOUT_LOG="${LOG_DIR}/netlogin.out.log"
STDERR_LOG="${LOG_DIR}/netlogin.err.log"

usage() {
  cat <<EOF
Usage:
  ./macos_autostart.sh install <username> <password> [interval_seconds]
  ./macos_autostart.sh status
  ./macos_autostart.sh uninstall

Examples:
  ./macos_autostart.sh install by123456 'your!password'
  ./macos_autostart.sh install by123456 'your!password' 30

Notes:
  - This script is for macOS launchd.
  - interval_seconds controls how often the login script checks network status. Default: 5.
  - Passwords with special characters should be wrapped in single quotes.
  - Credentials are stored in ${PLIST_PATH}.
EOF
}

require_macos() {
  if [[ "$(uname)" != "Darwin" ]]; then
    echo "This autostart script only supports macOS launchd." >&2
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

validate_interval() {
  local interval="$1"
  if ! [[ "${interval}" =~ ^[1-9][0-9]*$ ]]; then
    echo "interval_seconds must be a positive integer, got: ${interval}" >&2
    exit 1
  fi
}

install_agent() {
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

  mkdir -p "${HOME}/Library/LaunchAgents" "${LOG_DIR}"

  LAUNCHD_LABEL="${LABEL}" \
  LAUNCHD_PLIST_PATH="${PLIST_PATH}" \
  NETLOGIN_REPO_DIR="${SCRIPT_DIR}" \
  NETLOGIN_PYTHON_BIN="${python_bin}" \
  NETLOGIN_USERNAME="${username}" \
  NETLOGIN_PASSWORD="${password}" \
  NETLOGIN_INTERVAL="${interval}" \
  NETLOGIN_STDOUT_LOG="${STDOUT_LOG}" \
  NETLOGIN_STDERR_LOG="${STDERR_LOG}" \
  "${python_bin}" - <<'PY'
import os
import plistlib

plist = {
    "Label": os.environ["LAUNCHD_LABEL"],
    "ProgramArguments": [
        os.environ["NETLOGIN_PYTHON_BIN"],
        os.path.join(os.environ["NETLOGIN_REPO_DIR"], "main_login_modern.py"),
    ],
    "WorkingDirectory": os.environ["NETLOGIN_REPO_DIR"],
    "EnvironmentVariables": {
        "user": os.environ["NETLOGIN_USERNAME"],
        "pwd": os.environ["NETLOGIN_PASSWORD"],
        "interval": os.environ["NETLOGIN_INTERVAL"],
        "PATH": os.environ.get("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"),
    },
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": os.environ["NETLOGIN_STDOUT_LOG"],
    "StandardErrorPath": os.environ["NETLOGIN_STDERR_LOG"],
}

with open(os.environ["LAUNCHD_PLIST_PATH"], "wb") as f:
    plistlib.dump(plist, f, sort_keys=False)
PY

  chmod 600 "${PLIST_PATH}"
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
  launchctl kickstart -k "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true

  echo "Installed and started ${LABEL}."
  echo "Interval: ${interval} seconds"
  echo "Plist: ${PLIST_PATH}"
  echo "Logs: ${STDOUT_LOG} and ${STDERR_LOG}"
}

uninstall_agent() {
  launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
  rm -f "${PLIST_PATH}"
  echo "Uninstalled ${LABEL}."
}

status_agent() {
  launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null || {
    echo "${LABEL} is not loaded."
    exit 1
  }
}

main() {
  require_macos

  local action="${1:-}"
  if [[ -z "${action}" ]]; then
    usage
    exit 1
  fi
  shift

  case "${action}" in
    install)
      install_agent "$@"
      ;;
    uninstall)
      uninstall_agent
      ;;
    status)
      status_agent
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
