import os
import sys
import pytz
from pytz import timezone
from telegram.error import BadRequest

from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, BotCommand
from redis import Redis

import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.getLevelName(os.environ.get('LOG_LEVEL', 'INFO')))

redis = Redis(host=os.environ.get('REDIS_HOST', 'redis'), port=os.environ.get('REDIS_PORT', 6379))


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def handle_incoming_message(update: Update, context: CallbackContext):
    logging.debug(update.effective_chat)
    msg = update.message
    {
        'group': handle_group_chat,
        'supergroup': handle_group_chat,
    }.get(update.message.chat.type, handle_unknown_message_type)(update, context)
    user = msg.from_user.username or msg.from_user.first_name
    logging.debug(f'Received message from "{user}": "{msg.text}"')


def handle_start_command(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.message.chat_id,
                             text="Hi there! I'll check the 13:37 score in a group chat. "
                                  "Just add me to a group, and when the clock says 13:37, "
                                  "be the first to write something in the group!")
    # "If you want to, I'll pin the current score to the chat. "
    # "Make me an admin of the group to allow me to do that.")


def handle_group_chat(update: Update, context: CallbackContext):
    user = update.message.from_user.username
    current_timezone = redis.get(f'{update.message.chat_id}:settings:timezone')
    if not current_timezone:
        context.bot.send_message(chat_id=update.message.chat_id,
                                 text="Sorry to interrupt you, but you need to set a /timezone")
        return
    tz = timezone(current_timezone)
    msg_sent_date = update.message.date.astimezone(tz)
    hour, minute = msg_sent_date.hour, msg_sent_date.minute
    if hour != 13 or minute != 37:
        return

    out_msg = context.bot.send_message(chat_id=update.message.chat_id, text=f'Your message was from {msg_sent_date}')
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
        for key in redis.scan_iter(f'{update.message.chat_id}:*'):
            logging.debug(f'Removing from redis: {key}')
            redis.delete(key)


def handle_timezone_command(update: Update, context: CallbackContext):
    continents = sorted(set([x.partition('/')[0] for x in pytz.common_timezones]))
    if len(context.args) == 0:
        current_timezone = redis.get(f'{update.message.chat_id}:settings:timezone')
        reply = ReplyKeyboardMarkup(
            [[KeyboardButton(f'/timezone {x}') for x in continents[i:i + 3]] for i in range(0, len(continents), 3)],
            one_time_keyboard=True
        )
        context.bot.send_message(chat_id=update.message.chat_id,
                                 text=f'Your current timezone is set to "{current_timezone}". '
                                      'If you want to change it, choose your region',
                                 reply_markup=reply)
        return
    location = context.args[0]
    if location in pytz.all_timezones:
        redis.set(f'{update.message.chat_id}:settings:timezone', location)
        tz = timezone(location)
        local_time = update.message.date.astimezone(tz).strftime('%X')
        context.bot.send_message(chat_id=update.message.chat_id,
                                 text=f'Timezone of this group was set to {location}. Looks like it is {local_time}. '
                                      f'If this is incorrect, please execute /timezone again.')
    elif location in continents:
        zones = [x for x in pytz.all_timezones if x.startswith(location)]
        reply = ReplyKeyboardMarkup(
            [[KeyboardButton(f'/timezone {zone}')] for zone in zones],
            one_time_keyboard=True
        )
        context.bot.send_message(chat_id=update.message.chat_id, text='Choose your timezone', reply_markup=reply)
    else:
        context.bot.send_message(chat_id=update.message.chat_id, text="Sorry, I've never heard of that timezone")


def main():
    if 'TELEGRAM_TOKEN' not in os.environ:
        logging.error('You need to set the environment variable "TELEGRAM_TOKEN"')
        return sys.exit(-1)
    updater = Updater(token=os.environ.get('TELEGRAM_TOKEN'), use_context=True)
    updater.bot.set_my_commands([
        BotCommand('start', 'Returns a warming welcome message'),
        BotCommand('timezone', 'Changes the timezone of a group')
    ])
    updater.dispatcher.add_handler(CommandHandler('timezone', handle_timezone_command, Filters.group))
    updater.dispatcher.add_handler(CommandHandler('start', handle_start_command))
    updater.dispatcher.add_handler(MessageHandler(Filters.text & Filters.group, handle_incoming_message))
    updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_added_to_group))
    updater.dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, handle_removed_from_group))

    updater.start_polling()


if __name__ == '__main__':
    main()
