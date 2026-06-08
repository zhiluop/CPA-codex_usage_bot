# CPA Codex Usage Bot

Telegram bot，用来在群里快速查询 CLIProxyAPI 里 Codex 账号的 5h / 1w 剩余额度。

## 一键安装

推荐和 CLIProxyAPI 部署在同一台 VPS 上：

```bash
curl -fsSL https://raw.githubusercontent.com/zhiluop/CPA-codex_usage_bot/main/scripts/install.sh | sudo bash -s -- install
```

或者：

```bash
wget -qO- https://raw.githubusercontent.com/zhiluop/CPA-codex_usage_bot/main/scripts/install.sh | sudo bash -s -- install
```

如果你已经是 root 用户，可以去掉 `sudo`。

脚本会把项目拉到 `/home/cpa-codex-quota-bot`，逐步询问配置，写入 `/etc/cpa-codex-quota-bot.env`，然后用 systemd 后台运行。

## 配置项

安装向导会询问这些值：

- `TELEGRAM_BOT_TOKEN`: BotFather 给你的 bot token。
- `TELEGRAM_OWNER_USER_IDS`: bot 主人的 Telegram user id，主人可以私聊使用 `/admin`。
- `TELEGRAM_ALLOWED_CHAT_IDS`: 允许使用 bot 的群组或会话 chat id，可先留空，之后用 `/admin` 添加。
- `TELEGRAM_ALLOWED_USER_IDS`: 可选。限制哪些用户能查 `/quota`；留空表示白名单群里的所有人都能查。
- `CPA_BASE_URL`: CLIProxyAPI 地址，同机部署通常填 `http://127.0.0.1:8317`。
- `CPA_MANAGEMENT_KEY`: CLIProxyAPI `remote-management.secret-key` 对应明文。
- `TELEGRAM_QUOTA_COOLDOWN_SECONDS`: 群组查询冷却秒数，默认 `10`。

修改配置：

```bash
sudo nano /etc/cpa-codex-quota-bot.env
sudo systemctl restart cpa-codex-quota-bot
```

## Telegram 用法

群组里：

```text
/quota
```

私聊里：

```text
/id
/admin
/allow_chat -1001234567890
/allow_user 123456789
```

`/admin` 会打开 inline 管理面板，可以添加群白名单、用户白名单、查看当前白名单。

## 维护命令

```bash
# 打开管理菜单
curl -fsSL https://raw.githubusercontent.com/zhiluop/CPA-codex_usage_bot/main/scripts/install.sh | sudo bash

# 启动、停止、更新
sudo bash /home/cpa-codex-quota-bot/scripts/install.sh start
sudo bash /home/cpa-codex-quota-bot/scripts/install.sh stop
sudo bash /home/cpa-codex-quota-bot/scripts/install.sh update

# 查看状态和日志
systemctl status cpa-codex-quota-bot
journalctl -u cpa-codex-quota-bot -f
```

建议 CLIProxyAPI management API 只监听本机或内网，不要直接暴露到公网。
