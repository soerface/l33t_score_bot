import os
import sys
from datetime import datetime, timedelta
from random import choice

from pytz import timezone
from telegram.constants import ChatAction

from telegram.ext import Updater, MessageHandler, CommandHandler, CallbackContext, CallbackQueryHandler, filters, \
    Application
from telegram import Update, BotCommand, User
from telegram.ext.filters import ChatType, Text, Sticker, StatusUpdate

from db import redis

import logging

import ai
import handlers
from utils import build_chat_scores

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.getLevelName(os.environ.get('LOG_LEVEL', 'INFO')))

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

SPRUECHE = [
    'Weil ihr nix könnt. Punkt für mich.',
    'Was könnt ihr eigentlich?',
    'Wieder mal versagt, ihr Luschen',
    'Ihr wollt gar keine Punkte mehr machen, oder?',
    'Was ist mit euch los…',
    'Hallo? Keine Motivation mehr oder was?',
    'Joah. Mal wieder gepennt. Mein Punkt.',
    'Aus euch wird nix mehr, oder?',
    '👀',
    'Originale Nichtskönner 💩',
    '8=====D💦 (.Y.Y.)',
    'Wird langsam langweilig mit euch 🙄',
    'Heute geht die hier 🥇 wohl an mich',
]

SPRUECHE_EARLY = [
    'Zu früh!',
    'Noob!',
    'Na, geht die Uhr falsch?',
    'Kauf dir doch mal ne Uhr die richtig geht!',
    'Kommst du sonst auch zu früh?',
    'So wird das aber nichts.',
    'Knapp vorbei ist auch daneben.',
    '⏱',
]


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def increase_score(chat_id: int, user: User, n=1):
    score = int(redis.get(f'group:{chat_id}:score:{user.id}') or 0)
    redis.set(f'group:{chat_id}:score:{user.id}', score + n)
    redis.set(f'user:{user.id}:name', user.first_name)


def decrease_score(chat_id: int, user: User, n=1):
    increase_score(chat_id, user, n * -1)


async def handle_incoming_message(update: Update, context: CallbackContext):
    logger.debug(update.effective_chat)
    msg = update.message
    if not msg:
        logger.info(f'No message. Update: {update}')
        return
    await {
        'group': handle_group_chat,
        'supergroup': handle_group_chat,
    }.get(msg.chat.type, handle_unknown_message_type)(update, context)
    user = msg.from_user.username or msg.from_user.first_name
    logger.debug(f'Received message from "{user}": "{msg.text}"')


async def handle_group_chat(update: Update, context: CallbackContext):
    chat_id: int = update.message.chat_id
    current_timezone = redis.get(f'group:{chat_id}:settings:timezone')
    if not current_timezone:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry to interrupt you, but you need to set a /timezone"
        )
        return
    tz = timezone(current_timezone)
    msg_sent_date = update.message.date.astimezone(tz)
    hour, minute = msg_sent_date.hour, msg_sent_date.minute

    today = msg_sent_date.strftime('%Y-%m-%d')
    yesterday = (msg_sent_date - timedelta(days=1)).strftime('%Y-%m-%d')
    last_scored_day = redis.get(f'group:{chat_id}:last_scored_day') or yesterday
    # last_scored_day = yesterday  # DEBUG
    this_day = datetime.strptime(today, '%Y-%m-%d').astimezone(tz)
    last_day = datetime.strptime(last_scored_day, '%Y-%m-%d').astimezone(tz)
    delta = (this_day - last_day)

    if hour == 13 and minute == 36:
        looser: User = update.message.from_user
        decrease_score(chat_id, looser)
        current_score = int(redis.get(f'group:{chat_id}:score:{looser.id}'))
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        if current_score >= 0 and redis.get(f'group:{update.message.chat_id}:settings:openai'):
            text = ai.get_too_early_message(looser.first_name, update.message.text, current_score)
            await context.bot.send_message(chat_id=chat_id, text=text)
        elif redis.get(f'group:{update.message.chat_id}:settings:sprueche_early'):
            await context.bot.send_message(chat_id=chat_id, text=choice(SPRUECHE_EARLY))
        else:
            await context.bot.send_message(chat_id=chat_id, text=f'That was too early. That\'s gonna cost you a point.')

    # elif delta.days >= 1:  # debug
    elif hour == 13 and minute == 37 and delta.days >= 1:
        winner: User = update.message.from_user
        increase_score(chat_id, winner)
        redis.set(f'group:{chat_id}:last_scored_day', today)
        if redis.get(f'group:{update.message.chat_id}:settings:openai'):
            if delta.days > 1:
                bot_wins_extra = delta.days - 1
                increase_score(chat_id, context.bot, n=bot_wins_extra)
            else:
                bot_wins_extra = 0
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            text = ai.get_success_message(
                context.bot.first_name,
                winner.first_name,
                update.message.text,
                build_chat_scores(chat_id, indent=2),
                bot_wins_extra=bot_wins_extra,
            )
            await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=f'Congratz, {winner.first_name}! Scores:')
            if delta.days > 1:
                n = delta.days - 1
                msg = 'day' if n == 1 else f'{n} days'
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Wait a second. You forgot the last {msg}. So I'll get some points, too."
                )
                increase_score(chat_id, context.bot, n=n)
            await context.bot.send_message(chat_id=chat_id, text=build_chat_scores(chat_id))

    elif ((hour == 13 and minute > 37) or hour > 13) and delta.days == 1 or delta.days > 1:
        if (hour == 13 and minute > 37) or hour > 13:
            n = delta.days
            redis.set(f'group:{chat_id}:last_scored_day', today)
        else:
            n = delta.days - 1
            redis.set(f'group:{chat_id}:last_scored_day', yesterday)

        increase_score(chat_id, context.bot, n=n)
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        if redis.get(f'group:{update.message.chat_id}:settings:openai'):
            text = ai.get_lost_message(
                context.bot.first_name,
                build_chat_scores(chat_id, indent=2),
                n,
            )
            await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            if redis.get(f'group:{update.message.chat_id}:settings:sprueche'):
                await context.bot.send_message(chat_id=chat_id, text=choice(SPRUECHE))
            else:
                await context.bot.send_message(chat_id=chat_id, text=f'Oh dear. You forgot 13:37. Point for me')

            if n > 1:
                await context.bot.send_message(chat_id=chat_id,
                                         text=f"You even forgot it for {n} days... I'm disappointed.")
            await context.bot.send_message(chat_id=chat_id, text=build_chat_scores(chat_id))

    # out_msg = context.bot.send_message(...)chat_id=update.message.chat_id, text=f'Your message was from {msg_sent_date}')
    # try:
    #     context.bot.pin_chat_message(out_msg.chat_id, out_msg.message_id)
    # except BadRequest:
    #     pass


def handle_unknown_message_type(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.message.chat_id,
                             text=f"I'm sorry, I can't handle messages of type \"{update.message.chat.type}\"")


async def handle_added_to_group(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if member['id'] == context.bot.id:
            logger.info(f'Added to group {update.message.chat}')
            await update.message.reply_text('Hi! Would you mind telling me your /timezone?')


async def handle_removed_from_group(update: Update, context: CallbackContext):
    if update.message.left_chat_member['id'] == context.bot.id:
        logger.info(f'Removed from group {update.message.chat}')
        for key in redis.scan_iter(f'group:{update.message.chat_id}:*'):
            logger.debug(f'Removing from redis: {key}')
            redis.delete(key)


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand('start', 'Returns a warming welcome message'),
        BotCommand('timezone', 'Changes the timezone of a group'),
        BotCommand('score', 'Prints the scores of everyone'),
        BotCommand('clock', 'Outputs the date of the received message'),
        BotCommand('my_id', 'Outputs your id which is internally used for score tracking'),
        BotCommand('sprueche', 'sorueche'),
        BotCommand('sprueche_early', 'sprue early'),
    ])

def main():
    if not (token := os.environ.get("TELEGRAM_TOKEN")):
        logger.error('You need to set the environment variable "TELEGRAM_TOKEN"')
        return sys.exit(-1)

    builder = Application.builder().token(token)
    builder.post_init(post_init)
    app = builder.build()

    app.add_handler(CommandHandler('timezone', handlers.timezone_command))
    app.add_handler(CommandHandler('start', handlers.start_command))
    app.add_handler(CommandHandler('score', handlers.score_command))
    app.add_handler(CommandHandler('clock', handlers.clock_command))
    app.add_handler(CommandHandler('my_id', handlers.my_id_command))
    app.add_handler(CommandHandler('sprueche', handlers.sprueche_command))
    app.add_handler(CommandHandler('sprueche_early', handlers.sprueche_early_command))
    app.add_handler(CallbackQueryHandler(handlers.inlinebutton_click))
    app.add_handler(
        MessageHandler(ChatType.GROUPS, handle_incoming_message)
    )
    app.add_handler(MessageHandler(StatusUpdate.NEW_CHAT_MEMBERS, handle_added_to_group))
    app.add_handler(MessageHandler(StatusUpdate.LEFT_CHAT_MEMBER, handle_removed_from_group))

    logger.info("Ready")
    app.run_polling()


if __name__ == '__main__':
    main()
