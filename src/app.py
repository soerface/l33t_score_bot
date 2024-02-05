import os
import sys

from telegram.constants import ParseMode
from telegram.ext import (
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    Application,
    filters,
    ExtBot,
)
from telegram import BotCommand

import logging

import constants
import handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO")),
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    app.bot: ExtBot
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Returns a warming welcome message"),
            BotCommand("timezone", "Changes the timezone of a group"),
            BotCommand("score", "Prints the scores of everyone"),
            BotCommand("clock", "Outputs the date of the received message"),
            BotCommand(
                "my_id", "Outputs your id which is internally used for score tracking"
            ),
        ]
    )
    SHA = constants.COMMIT_SHA
    logger.info(f"Application ready. Version {SHA}")
    if constants.ADMIN_USER_ID:
        version_link = (
            f"[{SHA[:7]}](https://github.com/soerface/l33t_score_bot/commit/{SHA})"
        )
        await app.bot.send_message(
            chat_id=constants.ADMIN_USER_ID,
            text=f"Application ready\\. Version {version_link}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


def main():
    if not (token := os.environ.get("TELEGRAM_TOKEN")):
        logger.error('You need to set the environment variable "TELEGRAM_TOKEN"')
        return sys.exit(-1)

    builder = Application.builder().token(token)
    builder.post_init(post_init)
    app = builder.build()

    app.add_handler(CommandHandler("timezone", handlers.timezone_command))
    app.add_handler(CommandHandler("start", handlers.start_command))
    app.add_handler(CommandHandler("score", handlers.score_command))
    app.add_handler(CommandHandler("clock", handlers.clock_command))
    app.add_handler(CommandHandler("my_id", handlers.my_id_command))
    app.add_handler(CallbackQueryHandler(handlers.inlinebutton_click))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handlers.added_to_group)
    )
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.LEFT_CHAT_MEMBER, handlers.removed_from_group
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & (filters.TEXT | filters.Sticker.ALL | filters.ATTACHMENT),
            handlers.group_chat_message,
        )
    )

    logger.info("Ready")
    app.run_polling()


if __name__ == "__main__":
    main()
