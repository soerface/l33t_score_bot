import os
import sys
from datetime import datetime, timedelta
from random import choice
from typing import List

import pytz
from pytz import timezone

from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext, CallbackQueryHandler
from telegram import Update, BotCommand, User, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from redis import Redis

import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.getLevelName(os.environ.get('LOG_LEVEL', 'INFO')))

redis = Redis(
    host=os.environ.get('REDIS_HOST', 'redis'),
    port=os.environ.get('REDIS_PORT', 6379),
    charset='utf-8',
    decode_responses=True
)

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


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def increase_score(chat_id: int, user: User, n=1):
    score = int(redis.get(f'group:{chat_id}:score:{user.id}') or 0)
    redis.set(f'group:{chat_id}:score:{user.id}', score + n)
    redis.set(f'user:{user.id}:name', user.first_name)


def build_chat_scores(chat_id: int):
    scores = []
    for key in redis.scan_iter(f'group:{chat_id}:score:*'):
        user_id = int(key.rpartition(b':')[2])
        name = redis.get(f'user:{user_id}:name')
        value = int(redis.get(key))
        scores.append((name, value))
    if not scores:
        return 'No one has made any points so far…'
    scores = sorted(scores, key=lambda x: x[1], reverse=True)
    return '\n'.join([f'- {x[0]}: {x[1]}' for x in scores])


def get_timezone_region_markup(continents):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(x, callback_data=':'.join(['timezone', x])) for x in continents[i:i + 3]]
         for i in range(0, len(continents), 3)]
    )


def handle_incoming_message(update: Update, context: CallbackContext):
    logging.debug(update.effective_chat)
    msg = update.message
    {
        'group': handle_group_chat,
        'supergroup': handle_group_chat,
    }.get(update.message.chat.type, handle_unknown_message_type)(update, context)
    user = msg.from_user.username or msg.from_user.first_name
    logging.debug(f'Received message from "{user}": "{msg.text}"')


def handle_group_chat(update: Update, context: CallbackContext):
    chat_id: int = update.message.chat_id
    current_timezone = redis.get(f'group:{chat_id}:settings:timezone')
    if not current_timezone:
        context.bot.send_message(chat_id=chat_id,
                                 text="Sorry to interrupt you, but you need to set a /timezone")
        return
    tz = timezone(current_timezone)
    msg_sent_date = update.message.date.astimezone(tz)
    hour, minute = msg_sent_date.hour, msg_sent_date.minute

    today = msg_sent_date.strftime('%Y-%m-%d')
    yesterday = (msg_sent_date - timedelta(days=1)).strftime('%Y-%m-%d')
    last_scored_day = redis.get(f'group:{chat_id}:last_scored_day')
    this_day = datetime.strptime(today, '%Y-%m-%d').astimezone(tz)
    last_day = datetime.strptime(last_scored_day, '%Y-%m-%d').astimezone(tz)
    delta = (this_day - last_day)

    if hour == 13 and minute == 37 and delta.days >= 1:
        winner: User = update.message.from_user
        increase_score(chat_id, winner)
        redis.set(f'group:{chat_id}:last_scored_day', today)
        context.bot.send_message(chat_id=chat_id, text=f'Congratz, {winner.first_name}! Scores:')
        if delta.days > 1:
            n = delta.days - 1
            msg = 'day' if n == 1 else f'{n} days'
            context.bot.send_message(chat_id=chat_id,
                                     text=f"Wait a second. You forgot the last {msg}. So I'll get some points, too.")
            increase_score(chat_id, context.bot, n=n)
        context.bot.send_message(chat_id=chat_id, text=build_chat_scores(chat_id))

    elif ((hour == 13 and minute > 37) or hour > 13) and delta.days == 1 or delta.days > 1:
        if redis.get(f'group:{update.message.chat_id}:settings:sprueche'):
            context.bot.send_message(chat_id=chat_id, text=choice(SPRUECHE))
        else:
            context.bot.send_message(chat_id=chat_id, text=f'Oh dear. You forgot 13:37. Point for me')

        if (hour == 13 and minute > 37) or hour > 13:
            n = delta.days
            redis.set(f'group:{chat_id}:last_scored_day', today)
        else:
            n = delta.days - 1
            redis.set(f'group:{chat_id}:last_scored_day', yesterday)

        if n > 1:
            context.bot.send_message(chat_id=chat_id,
                                     text=f"You even forgot it for {n} days... I'm disappointed.")
        increase_score(chat_id, context.bot, n=n)
        context.bot.send_message(chat_id=chat_id, text=build_chat_scores(chat_id))

    # out_msg = context.bot.send_message(...)chat_id=update.message.chat_id, text=f'Your message was from {msg_sent_date}')
    # try:
    #     context.bot.pin_chat_message(out_msg.chat_id, out_msg.message_id)
    # except BadRequest:
    #     pass


def handle_unknown_message_type(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.message.chat_id,
                             text=f"I'm sorry, I can't handle messages of type \"{update.message.chat.type}\"")


def handle_added_to_group(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if member['id'] == context.bot.id:
            logging.info(f'Added to group {update.message.chat}')
            update.message.reply_text('Hi! Would you mind telling me your /timezone?')


def handle_removed_from_group(update: Update, context: CallbackContext):
    if update.message.left_chat_member['id'] == context.bot.id:
        logging.info(f'Removed from group {update.message.chat}')
        for key in redis.scan_iter(f'group:{update.message.chat_id}:*'):
            logging.debug(f'Removing from redis: {key}')
            redis.delete(key)


def handle_timezone_command(update: Update, context: CallbackContext):
    continents = sorted(set([x.partition('/')[0] for x in pytz.common_timezones]))
    current_timezone = redis.get(f'chat:{update.message.chat_id}:settings:timezone')
    reply = get_timezone_region_markup(continents)
    context.bot.send_message(chat_id=update.message.chat_id,
                             text=f'Your current timezone is set to "{current_timezone}". '
                                  'If you want to change it, choose your region',
                             reply_markup=reply)


def handle_start_command(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.message.chat_id,
                             text="Hi there! I'll check the 13:37 score in a group chat. "
                                  "Just add me to a group, and when the clock says 13:37, "
                                  "be the first to write something in the group!")
    # "If you want to, I'll pin the current score to the chat. "
    # "Make me an admin of the group to allow me to do that.")


def handle_score_command(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.message.chat_id, text=build_chat_scores(update.message.chat_id))


def handle_clock_command(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    current_timezone = redis.get(f'group:{chat_id}:settings:timezone')
    if not current_timezone:
        context.bot.send_message(chat_id=chat_id,
                                 text="Sorry to interrupt you, but you need to set a /timezone")
        return
    tz = timezone(current_timezone)
    msg_sent_date = update.message.date.astimezone(tz)
    context.bot.send_message(chat_id=update.message.chat_id, text=f'I received your message at {msg_sent_date}')


def handle_my_id_command(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.message.chat_id,
                             text='\n'.join([
                                 f'set group:{update.message.chat_id}:score:{update.message.from_user.id} X',
                                 f'set user:{update.message.from_user.id}:name "{update.message.from_user.first_name}"'
                             ]))


def handle_sprueche_command(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        return
    if context.args[0] == 'AN':
        redis.set(f'group:{update.message.chat_id}:settings:sprueche', 1)
        context.bot.send_message(chat_id=update.message.chat_id, text='Na wenn ihr das vertragt')
    elif context.args[0] == 'AUS':
        redis.delete(f'group:{update.message.chat_id}:settings:sprueche')
        context.bot.send_message(chat_id=update.message.chat_id, text='Dann halt nich')


def handle_inlinebutton_click(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    cmd, *args = query.data.split(':')

    if cmd == 'timezone':
        inlinebutton_timezone(update, context, query, args)
    elif cmd == 'cancel':
        query.edit_message_text('Canceled')

    query.answer()


def inlinebutton_timezone(update: Update, context: CallbackContext, query: CallbackQuery, args: List[str]):
    continents = sorted(set([x.partition('/')[0] for x in pytz.common_timezones]))
    location = args[0]
    if location == 'region_selection':
        reply = get_timezone_region_markup(continents)
        query.edit_message_text('Choose your region')
        query.edit_message_reply_markup(reply)
    elif location in pytz.all_timezones:
        redis.set(f'chat:{query.message.chat_id}:settings:timezone', location)
        tz = timezone(location)
        local_time = query.message.date.astimezone(tz).strftime('%X')
        reply = InlineKeyboardMarkup(
            [[(InlineKeyboardButton('Change timezone', callback_data='timezone:region_selection'))]]
        )
        query.edit_message_text(
            f'Timezone of this chat was set to {location}. '
            f'Looks like it was {local_time} when you sent the last /timezone command. '
            'If this is incorrect, please execute /timezone again or click the button below.'
        )
        query.edit_message_reply_markup(reply)
    elif location in continents:
        zones = [x for x in pytz.all_timezones if x.startswith(location)]
        reply = InlineKeyboardMarkup(
            [[InlineKeyboardButton(x.partition('/')[2], callback_data=':'.join(['timezone', x]))] for x in zones]
            + [[(InlineKeyboardButton('« Back', callback_data='timezone:region_selection'))]],
        )
        query.edit_message_text('Choose your timezone')
        query.edit_message_reply_markup(reply)


def main():
    if 'TELEGRAM_TOKEN' not in os.environ:
        logging.error('You need to set the environment variable "TELEGRAM_TOKEN"')
        return sys.exit(-1)
    updater = Updater(token=os.environ.get('TELEGRAM_TOKEN'), use_context=True)
    updater.bot.set_my_commands([
        BotCommand('start', 'Returns a warming welcome message'),
        BotCommand('timezone', 'Changes the timezone of a group'),
        BotCommand('score', 'Prints the scores of everyone'),
        BotCommand('clock', 'Outputs the date of the received message'),
        BotCommand('my_id', 'Outputs your id which is internally used for score tracking'),
    ])
    updater.dispatcher.add_handler(CommandHandler('timezone', handle_timezone_command))
    updater.dispatcher.add_handler(CommandHandler('start', handle_start_command))
    updater.dispatcher.add_handler(CommandHandler('score', handle_score_command))
    updater.dispatcher.add_handler(CommandHandler('clock', handle_clock_command))
    updater.dispatcher.add_handler(CommandHandler('my_id', handle_my_id_command))
    updater.dispatcher.add_handler(CommandHandler('sprueche', handle_sprueche_command))
    updater.dispatcher.add_handler(CallbackQueryHandler(handle_inlinebutton_click))
    updater.dispatcher.add_handler(
        MessageHandler(Filters.group & (Filters.text | Filters.sticker), handle_incoming_message))
    updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_added_to_group))
    updater.dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, handle_removed_from_group))

    updater.start_polling()


if __name__ == '__main__':
    main()
