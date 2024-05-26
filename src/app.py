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

COMMANDS = [
    {
        "command": "start",
        "description": "Returns a warming welcome message",
        "handler": handlers.start_command,
    },
    {
        "command": "timezone",
        "description": "Changes the timezone of a group",
        "handler": handlers.timezone_command,
    },
    {
        "command": "score",
        "description": "Prints the scores of everyone",
        "handler": handlers.score_command,
    },
    {
        "command": "clock",
        "description": "Outputs the date of the received message",
        "handler": handlers.clock_command,
    },
    {
        "command": "my_id",
        "description": "Outputs your id which is internally used for score tracking",
        "handler": handlers.my_id_command,
    },
    {
        "command": "challenge",
        "description": "Enable / disable daily challenges. The bot will send a challenge every day at 13:37",
        "handler": handlers.challenge_command,
    },
    {
        "command": "autochallenge",
        "description": (
            "Enable / disable automatic challenges. After a challenge is solved, the bot will "
            "schedule a new one"
        ),
        "handler": handlers.autochallenge_command,
    },
    {
        "command": "debuglog",
        "description": (
            "Enable / disable debug logging. "
            "When enabled, it will show the messages between the bot and OpenAI in the chat"
        ),
        "handler": handlers.debuglog_command,
    },
]


async def post_init(app: Application) -> None:
    app.bot: ExtBot
    await app.bot.set_my_commands(
        [BotCommand(command["command"], command["description"]) for command in COMMANDS]
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

    app.add_handlers(
        [CommandHandler(command["command"], command["handler"]) for command in COMMANDS]
    )
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
