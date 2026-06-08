#!/usr/bin/env bash
set -euo pipefail

APP_NAME="cpa-codex-quota-bot"
APP_DIR="${APP_DIR:-/home/${APP_NAME}}"
ENV_FILE="${ENV_FILE:-/etc/${APP_NAME}.env}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
STATE_FILE="/var/lib/${APP_NAME}/state.json"
REPO_URL="${REPO_URL:-}"

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "请用 root 运行，或使用 sudo: sudo bash scripts/install.sh" >&2
    exit 1
  fi
}

prompt() {
  local label="$1"
  local default_value="${2:-}"
  local value
  if [ -n "$default_value" ]; then
    read -r -p "${label} [${default_value}]: " value
    printf '%s' "${value:-$default_value}"
  else
    read -r -p "${label}: " value
    printf '%s' "$value"
  fi
}

prompt_secret() {
  local label="$1"
  local value
  read -r -s -p "${label}: " value
  echo >&2
  printf '%s' "$value"
}

current_env_value() {
  local key="$1"
  if [ ! -f "$ENV_FILE" ]; then
    return 0
  fi
  grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
}

write_env() {
  local token="$1"
  local owner_ids="$2"
  local chat_ids="$3"
  local user_ids="$4"
  local cpa_url="$5"
  local cpa_key="$6"
  local cooldown="$7"

  umask 077
  cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=${token}
TELEGRAM_ALLOWED_CHAT_IDS=${chat_ids}
TELEGRAM_ALLOWED_USER_IDS=${user_ids}
TELEGRAM_OWNER_USER_IDS=${owner_ids}
TELEGRAM_LEAVE_UNAUTHORIZED_CHATS=true
TELEGRAM_QUOTA_COOLDOWN_SECONDS=${cooldown}

CPA_BASE_URL=${cpa_url}
CPA_MANAGEMENT_KEY=${cpa_key}
CPA_QUOTA_STATE_FILE=${STATE_FILE}

# Optional. Keep the default unless the upstream Codex usage endpoint changes
# behavior for older clients.
# CODEX_USER_AGENT=codex_cli_rs/0.76.0

# Optional. Telegram long-poll timeout in seconds.
# TELEGRAM_POLL_TIMEOUT=50
EOF
  chmod 600 "$ENV_FILE"
}

install_service_file() {
  if [ ! -d "$APP_DIR/cpa_quota_bot" ]; then
    echo "找不到程序目录: $APP_DIR/cpa_quota_bot" >&2
    echo "请先把项目上传到 $APP_DIR，或设置 APP_DIR=/path/to/${APP_NAME}" >&2
    exit 1
  fi
  install -d -m 755 "/var/lib/${APP_NAME}"
  cp "$APP_DIR/systemd/${APP_NAME}.service" "$SERVICE_FILE"
  systemctl daemon-reload
}

install_app() {
  require_root
  echo "== 安装/配置 ${APP_NAME} =="
  echo "程序目录: $APP_DIR"
  echo "环境文件: $ENV_FILE"
  echo

  local old_token old_owner old_chat old_user old_url old_key old_cooldown
  old_token=$(current_env_value TELEGRAM_BOT_TOKEN)
  old_owner=$(current_env_value TELEGRAM_OWNER_USER_IDS)
  old_chat=$(current_env_value TELEGRAM_ALLOWED_CHAT_IDS)
  old_user=$(current_env_value TELEGRAM_ALLOWED_USER_IDS)
  old_url=$(current_env_value CPA_BASE_URL)
  old_key=$(current_env_value CPA_MANAGEMENT_KEY)
  old_cooldown=$(current_env_value TELEGRAM_QUOTA_COOLDOWN_SECONDS)

  local token owner_ids chat_ids user_ids cpa_url cpa_key cooldown
  if [ -n "$old_token" ]; then
    token=$(prompt "Telegram Bot Token（留空沿用现有值）" "$old_token")
  else
    token=$(prompt_secret "Telegram Bot Token（BotFather 给你的 token）")
  fi
  owner_ids=$(prompt "主人 Telegram user_id（可私聊 bot 发 /id 获取）" "$old_owner")
  chat_ids=$(prompt "允许使用的群/会话 chat_id，逗号分隔；可先留空，之后用 /admin 添加" "$old_chat")
  user_ids=$(prompt "允许使用 /quota 的用户 user_id，逗号分隔；留空=群内所有人" "$old_user")
  cpa_url=$(prompt "CLIProxyAPI 地址" "${old_url:-http://127.0.0.1:8317}")
  if [ -n "$old_key" ]; then
    cpa_key=$(prompt "CLIProxyAPI management secret-key（留空沿用现有值）" "$old_key")
  else
    cpa_key=$(prompt_secret "CLIProxyAPI management secret-key 明文")
  fi
  cooldown=$(prompt "群组 /quota 冷却秒数" "${old_cooldown:-10}")

  write_env "$token" "$owner_ids" "$chat_ids" "$user_ids" "$cpa_url" "$cpa_key" "$cooldown"
  install_service_file
  systemctl enable --now "$APP_NAME"
  systemctl restart "$APP_NAME"
  echo "安装完成。查看日志: journalctl -u ${APP_NAME} -f"
}

start_app() {
  require_root
  install_service_file
  systemctl enable --now "$APP_NAME"
  systemctl restart "$APP_NAME"
  systemctl status "$APP_NAME" --no-pager
}

stop_app() {
  require_root
  systemctl stop "$APP_NAME"
  systemctl status "$APP_NAME" --no-pager || true
}

update_app() {
  require_root
  if [ -n "$REPO_URL" ] && [ ! -d "$APP_DIR/.git" ]; then
    git clone "$REPO_URL" "$APP_DIR"
  elif [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
  else
    echo "未配置 REPO_URL，且 $APP_DIR 不是 git 仓库。已跳过拉取，仅刷新服务文件。"
  fi
  install_service_file
  python3 -m unittest discover -s "$APP_DIR/tests" -t "$APP_DIR"
  PYTHONPYCACHEPREFIX=/tmp/${APP_NAME}-pycache python3 -m compileall "$APP_DIR/cpa_quota_bot"
  systemctl restart "$APP_NAME"
  systemctl status "$APP_NAME" --no-pager
}

show_menu() {
  echo "== ${APP_NAME} 管理菜单 =="
  echo "1) 安装/配置"
  echo "2) 启动"
  echo "3) 停止"
  echo "4) 更新"
  echo "0) 退出"
}

main() {
  local action="${1:-}"
  case "$action" in
    install|configure) install_app ;;
    start) start_app ;;
    stop) stop_app ;;
    update) update_app ;;
    "")
      show_menu
      local choice
      read -r -p "请选择操作 [1-4]: " choice
      case "$choice" in
        1) install_app ;;
        2) start_app ;;
        3) stop_app ;;
        4) update_app ;;
        0) exit 0 ;;
        *) echo "无效选择" >&2; exit 1 ;;
      esac
      ;;
    *)
      echo "用法: bash scripts/install.sh [install|start|stop|update]" >&2
      exit 1
      ;;
  esac
}

main "$@"
