# CPA Codex Quota Telegram Bot

一个部署在 CLIProxyAPI 同机上的轻量 Telegram bot，用 `/quota` 快速查询 Codex OAuth 账号的 5h / 1w 剩余额度。

实现特点：

- 只依赖 Python 标准库，不需要 pip 安装包。
- 使用 Telegram `getUpdates` 长轮询，不要求服务器暴露 webhook。
- 只调用 CLIProxyAPI management API 的 `/auth-files` 和 `/api-call`。
- 支持群组白名单 `TELEGRAM_ALLOWED_CHAT_IDS`、用户白名单 `TELEGRAM_ALLOWED_USER_IDS`。
- 支持主人私聊 `/admin` inline 面板，动态添加群/用户白名单。
- 群组里只响应 `/quota`，并按群组做请求冷却，默认 10 秒一次。
- 被拉进未授权群组时可自动退群。
- 提供 `scripts/install.sh` 管理菜单：安装/配置、启动、停止、更新；缺少 env 时会自动生成模板。

## 一键安装向导

代码上传到 VPS 的 `/home/cpa-codex-quota-bot` 后，直接运行菜单：

```bash
cd /home/cpa-codex-quota-bot
bash scripts/install.sh
```

菜单支持：

- `1) 安装/配置`: 逐步询问 Telegram bot token、主人 user id、群白名单、用户白名单、CLIProxyAPI 地址、management key、群组冷却秒数，写入 `/etc/cpa-codex-quota-bot.env` 并后台运行。
- `2) 启动`: 安装/刷新 systemd 服务并启动。
- `3) 停止`: 停止后台服务。
- `4) 更新`: 如果 `/home/cpa-codex-quota-bot` 是 git 仓库则 `git pull --ff-only`，否则仅刷新服务文件、运行测试并重启。

也可以直接命令式调用：

```bash
bash scripts/install.sh install
bash scripts/install.sh start
bash scripts/install.sh stop
bash scripts/install.sh update
```

查看状态和日志：

```bash
systemctl status cpa-codex-quota-bot
journalctl -u cpa-codex-quota-bot -f
```

## 手动配置

复制环境变量样例：

```bash
cp .env.example .env
```

需要填写：

- `TELEGRAM_BOT_TOKEN`: BotFather 给你的 bot token。
- `TELEGRAM_ALLOWED_CHAT_IDS`: 允许使用 bot 的个人或群组 chat id，逗号分隔。留空表示允许所有 chat，不建议公网长期使用。
- `TELEGRAM_ALLOWED_USER_IDS`: 可选。允许触发 `/quota` 的 Telegram 用户 id，逗号分隔。留空表示允许白名单群组里的所有人使用。
- `TELEGRAM_OWNER_USER_IDS`: bot 主人 Telegram 用户 id，逗号分隔。只有主人能在私聊里使用 `/admin` 和 `/allow_chat` / `/allow_user`。
- `TELEGRAM_LEAVE_UNAUTHORIZED_CHATS`: 默认为 `true`。bot 被拉进不在 `TELEGRAM_ALLOWED_CHAT_IDS` 的群组时会自动退出。
- `TELEGRAM_QUOTA_COOLDOWN_SECONDS`: 群组 `/quota` 请求冷却时间，默认 `10` 秒。
- `CPA_BASE_URL`: CLIProxyAPI 地址。部署在同机时推荐 `http://127.0.0.1:8317`。
- `CPA_MANAGEMENT_KEY`: `config.yaml` 里的 `remote-management.secret-key` 对应明文密钥。
- `CPA_QUOTA_STATE_FILE`: 动态白名单状态文件，systemd 默认使用 `/var/lib/cpa-codex-quota-bot/state.json`。

CLIProxyAPI 需要开启 management API：

```yaml
remote-management:
  allow-remote: false
  secret-key: "replace-me"
```

bot 和 CPA 同机部署时，`allow-remote: false` 更安全。

如果服务首次启动时发现 `/etc/cpa-codex-quota-bot.env` 不存在，会自动创建一个模板文件并在日志里提示缺少的变量。你可以编辑后重启：

```bash
nano /etc/cpa-codex-quota-bot.env
systemctl restart cpa-codex-quota-bot
```

## 本地运行

```bash
export TELEGRAM_BOT_TOKEN="123456789:replace-me"
export TELEGRAM_ALLOWED_CHAT_IDS="123456789"
export TELEGRAM_ALLOWED_USER_IDS=""
export TELEGRAM_OWNER_USER_IDS="123456789"
export TELEGRAM_LEAVE_UNAUTHORIZED_CHATS="true"
export TELEGRAM_QUOTA_COOLDOWN_SECONDS="10"
export CPA_BASE_URL="http://127.0.0.1:8317"
export CPA_MANAGEMENT_KEY="replace-me"

python3 -m cpa_quota_bot
```

在 Telegram 里发送：

```text
/quota
```

返回示例：

```text
📊 Codex 用量: 1 个账号

👤 p**s@example.com
  套餐: plus; 状态: available
  🕔 5h: 🟢 🟩🟩🟩🟩🟩🟩⬜⬜⬜⬜ 57.5% 剩余 (42.5% 已用)
  📅 1w: 🔴 🟥⬜⬜⬜⬜⬜⬜⬜⬜⬜ 8.0% 剩余 (92.0% 已用)
```

群组里只响应 `/quota`，默认同一个群 10 秒内重复请求会返回冷却提示。

私聊里获取群组和用户 id：

```text
/id
```

返回里的 `chat_id` 填到 `TELEGRAM_ALLOWED_CHAT_IDS`。如果你想只允许群内部分人用，再把对应 `user_id` 填到 `TELEGRAM_ALLOWED_USER_IDS`。

主人私聊管理：

```text
/admin
```

面板会显示 inline 按钮：添加群、添加用户、查看白名单、取消。点击添加后发送对应数字 ID，bot 会写入 `CPA_QUOTA_STATE_FILE`，重启后仍然保留。

也可以直接私聊命令：

```text
/allow_chat -1001234567890
/allow_user 123456789
```

## systemd 部署

假设代码放在 `/home/cpa-codex-quota-bot`：

```bash
sudo mkdir -p /home/cpa-codex-quota-bot
sudo cp -a cpa_quota_bot README.md .env.example scripts systemd /home/cpa-codex-quota-bot/
sudo cp systemd/cpa-codex-quota-bot.service /etc/systemd/system/
sudo cp .env.example /etc/cpa-codex-quota-bot.env
sudo nano /etc/cpa-codex-quota-bot.env
sudo chmod 600 /etc/cpa-codex-quota-bot.env

sudo systemctl daemon-reload
sudo systemctl enable --now cpa-codex-quota-bot
sudo journalctl -u cpa-codex-quota-bot -f
```

## 测试

```bash
python3 -m unittest discover -s tests -t .
```

如果在仓库根目录运行：

```bash
python3 -m unittest discover -s cpa-codex-quota-bot/tests -t cpa-codex-quota-bot
```

## 安全边界

`/v0/management/api-call` 是通用上游请求代理，管理密钥权限很高。建议：

- bot 与 CLIProxyAPI 部署在同一台机器，CPA 只监听内网或 localhost。
- 不把 CPA management API 直接暴露给公网。
- 用 `TELEGRAM_ALLOWED_CHAT_IDS` 限制能查询额度的 chat/group。
- 小群共享时，只填群组 id 即可让群内成员使用；如果还想限制具体成员，再填 `TELEGRAM_ALLOWED_USER_IDS`。
- 定期轮换 `CPA_MANAGEMENT_KEY` 和 Telegram bot token。
