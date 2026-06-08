#!/usr/bin/env bash
set -euo pipefail

APP_NAME="cpa-codex-quota-bot"
APP_DIR="${APP_DIR:-/home/${APP_NAME}}"
ENV_FILE="${ENV_FILE:-/etc/${APP_NAME}.env}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
STATE_FILE="/var/lib/${APP_NAME}/state.json"
REPO_URL="${REPO_URL:-https://github.com/zhiluop/CPA-codex_usage_bot.git}"
RAW_INSTALL_URL="${RAW_INSTALL_URL:-https://raw.githubusercontent.com/zhiluop/CPA-codex_usage_bot/main/scripts/install.sh}"

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "请用 root 运行。非 root 可使用：" >&2
    echo "curl -fsSL ${RAW_INSTALL_URL} | sudo bash -s -- install" >&2
    exit 1
  fi
}

require_systemd() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "当前系统找不到 systemctl，暂只支持 systemd 部署。" >&2
    exit 1
  fi
}

install_missing_packages() {
  local missing=()
  command -v git >/dev/null 2>&1 || missing+=(git)
  command -v python3 >/dev/null 2>&1 || missing+=(python3)

  if [ "${#missing[@]}" -eq 0 ]; then
    return
  fi

  echo "缺少依赖: ${missing[*]}，尝试自动安装..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "${missing[@]}"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "${missing[@]}"
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache "${missing[@]}"
  else
    echo "无法自动安装依赖，请先安装: ${missing[*]}" >&2
    exit 1
  fi
}

read_input() {
  local prompt_text="$1"
  local secret="${2:-false}"
  local value

  if [ -r /dev/tty ]; then
    printf '%s' "$prompt_text" >/dev/tty
    if [ "$secret" = "true" ]; then
      stty -echo </dev/tty
      IFS= read -r value </dev/tty
      stty echo </dev/tty
      printf '\n' >/dev/tty
    else
      IFS= read -r value </dev/tty
    fi
  else
    printf '%s' "$prompt_text" >&2
    if [ "$secret" = "true" ]; then
      IFS= read -r -s value
      printf '\n' >&2
    else
      IFS= read -r value
    fi
  fi

  printf '%s' "$value"
}

prompt() {
  local label="$1"
  local default_value="${2:-}"
  local value
  if [ -n "$default_value" ]; then
    value=$(read_input "${label} [${default_value}]: ")
    printf '%s' "${value:-$default_value}"
  else
    value=$(read_input "${label}: ")
    printf '%s' "$value"
  fi
}

prompt_secret() {
  local label="$1"
  read_input "${label}: " true
}

ensure_app_dir() {
  install_missing_packages

  if [ -d "$APP_DIR/cpa_quota_bot" ] && [ -f "$APP_DIR/systemd/${APP_NAME}.service" ]; then
    return
  fi

  if [ -e "$APP_DIR" ] && [ ! -d "$APP_DIR" ]; then
    echo "$APP_DIR 已存在但不是目录，请移走后重试，或设置 APP_DIR。" >&2
    exit 1
  fi

  if [ -d "$APP_DIR/.git" ]; then
    echo "检测到已有 git 仓库，尝试更新: $APP_DIR"
    git -C "$APP_DIR" pull --ff-only
    if [ -d "$APP_DIR/cpa_quota_bot" ] && [ -f "$APP_DIR/systemd/${APP_NAME}.service" ]; then
      return
    fi
    echo "$APP_DIR 是 git 仓库，但不像本项目目录，请检查 APP_DIR。" >&2
    exit 1
  fi

  if [ -d "$APP_DIR" ] && [ -n "$(find "$APP_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    echo "$APP_DIR 已存在但缺少本项目代码。" >&2
    echo "请先备份/移走该目录，或设置 APP_DIR=/path/to/${APP_NAME} 后重试。" >&2
    exit 1
  fi

  install -d -m 755 "$(dirname "$APP_DIR")"
  echo "正在从 GitHub 拉取项目到 $APP_DIR ..."
  git clone "$REPO_URL" "$APP_DIR"
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
  install -d -m 755 "$(dirname "$ENV_FILE")"
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
  ensure_app_dir
  install -d -m 755 "/var/lib/${APP_NAME}"
  awk -v app_dir="$APP_DIR" -v env_file="$ENV_FILE" '
    /^WorkingDirectory=/ { print "WorkingDirectory=" app_dir; next }
    /^EnvironmentFile=/ { print "EnvironmentFile=" env_file; next }
    { print }
  ' "$APP_DIR/systemd/${APP_NAME}.service" > "$SERVICE_FILE"
  chmod 644 "$SERVICE_FILE"
  systemctl daemon-reload
}

run_checks() {
  if [ -d "$APP_DIR/tests" ]; then
    python3 -m unittest discover -s "$APP_DIR/tests" -t "$APP_DIR"
  else
    echo "未找到 tests 目录，跳过单元测试。"
  fi
  PYTHONPYCACHEPREFIX=/tmp/${APP_NAME}-pycache python3 -m compileall "$APP_DIR/cpa_quota_bot"
}

install_app() {
  require_root
  require_systemd
  echo "== 安装/配置 ${APP_NAME} =="
  echo "程序目录: $APP_DIR"
  echo "环境文件: $ENV_FILE"
  echo
  ensure_app_dir

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
    token=$(prompt_secret "Telegram Bot Token（已有值，回车沿用）")
    token="${token:-$old_token}"
  else
    token=$(prompt_secret "Telegram Bot Token（BotFather 给你的 token）")
  fi
  owner_ids=$(prompt "主人 Telegram user_id（可私聊 bot 发 /id 获取）" "$old_owner")
  chat_ids=$(prompt "允许使用的群/会话 chat_id，逗号分隔；可先留空，之后用 /admin 添加" "$old_chat")
  user_ids=$(prompt "允许使用 /quota 的用户 user_id，逗号分隔；留空=群内所有人" "$old_user")
  cpa_url=$(prompt "CLIProxyAPI 地址" "${old_url:-http://127.0.0.1:8317}")
  if [ -n "$old_key" ]; then
    cpa_key=$(prompt_secret "CLIProxyAPI management secret-key（已有值，回车沿用）")
    cpa_key="${cpa_key:-$old_key}"
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
  require_systemd
  install_service_file
  systemctl enable --now "$APP_NAME"
  systemctl restart "$APP_NAME"
  systemctl status "$APP_NAME" --no-pager
}

stop_app() {
  require_root
  require_systemd
  systemctl stop "$APP_NAME"
  systemctl status "$APP_NAME" --no-pager || true
}

update_app() {
  require_root
  require_systemd
  ensure_app_dir
  if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
  else
    echo "$APP_DIR 不是 git 仓库。已跳过拉取，仅刷新服务文件。"
  fi
  install_service_file
  run_checks
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
      choice=$(read_input "请选择操作 [1-4]: ")
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
      echo "一键安装: curl -fsSL ${RAW_INSTALL_URL} | bash -s -- install" >&2
      exit 1
      ;;
  esac
}

main "$@"
