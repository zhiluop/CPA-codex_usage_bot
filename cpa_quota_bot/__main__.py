from __future__ import annotations

import logging

from .bot import QuotaBot
from .config import load_config
from .cpa import CPAClient
from .service import QuotaService
from .state import RuntimeStateStore
from .telegram import TelegramClient


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config()
    cpa = CPAClient(
        config.cpa_base_url,
        config.cpa_management_key,
        codex_user_agent=config.codex_user_agent,
    )
    bot = QuotaBot(
        config,
        TelegramClient(config.telegram_bot_token),
        QuotaService(cpa),
        state_store=RuntimeStateStore(config.state_file),
    )
    bot.run_forever()


if __name__ == "__main__":
    main()
