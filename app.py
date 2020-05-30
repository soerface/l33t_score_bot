import os
import sys
import pytz
from pytz import timezone
from telegram.error import BadRequest

from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from telegram import KeyboardButton, ReplyKeyboardMarkup
from redis import Redis

import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

redis = Redis(host=os.environ.get('REDIS_HOST', 'redis'), port=os.environ.get('REDIS_PORT', 6379))

def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def handle_incoming_message(bot, update):
    logging.debug(update.effective_chat)
    msg = update.message
    {
        'private': handle_private_chat,
        'group': handle_group_chat,
        'supergroup': handle_group_chat,
    }.get(update.message.chat.type, handle_unknown_message_type)(bot, update)
    user = msg.from_user.username or msg.from_user.first_name
    logging.info(f'Received: "{user}: {msg.text}"')


def handle_private_chat(bot, update):
    if update.message.text == '/start':
        bot.send_message(chat_id=update.message.chat_id,
                         text="Hi there! I'll check the 13:37 score in a group chat. "
                              "Just add me to a group, and when the clock says 13:37, "
                              "be the first to write something in the group! "
                              "If you want to, I'll pin the current score to the chat. "
                              "Make me an admin of the group to allow me to do that.")


def handle_group_chat(bot, update):
    user = update.message.from_user.username
    # os.environ['TZ'] = 'Europe/Madrid'
    # time.tzset()
    tz = timezone('Europe/Berlin')
    msg_sent_date = update.message.date.astimezone(tz)
    out_msg = bot.send_message(chat_id=update.message.chat_id, text=f'Your message was from {msg_sent_date}')
    try:
        bot.pin_chat_message(out_msg.chat_id, out_msg.message_id)
    except BadRequest:
        pass


def handle_unknown_message_type(bot, update):
    bot.send_message(chat_id=update.message.chat_id,
                     text=f"I'm sorry, I can't handle messages of type \"{update.message.chat.type}\"")


def handle_added_to_group(bot, update):
    for member in update.message.new_chat_members:
        print(member)
        if member['id'] == bot.id:
            update.message.reply_text('Hi! Would you mind settings the /timezone?')


def handle_timezone_command(bot, update, args):
    continents = sorted(set([x.partition('/')[0] for x in pytz.common_timezones]))
    if len(args) == 0:
        reply = ReplyKeyboardMarkup(
            [[KeyboardButton(f'/timezone {x}') for x in continents[i:i+3]] for i in range(0, len(continents), 3)],
            one_time_keyboard=True
        )
        bot.send_message(chat_id=update.message.chat_id, text='Choose your region', reply_markup=reply)
        return
    location = args[0]
    if location in pytz.all_timezones:
        tz = timezone(location)
        local_time = update.message.date.astimezone(tz).strftime('%X')
        bot.send_message(chat_id=update.message.chat_id,
                         text=f'Timezone of this group was set to {location}. Looks like it is {local_time}. '
                              f'If this is incorrect, please execute /timezone again.')
    elif location in continents:
        zones = [x for x in pytz.all_timezones if x.startswith(location)]
        reply = ReplyKeyboardMarkup(
            [[KeyboardButton(f'/timezone {zone}')] for zone in zones],
            one_time_keyboard=True
        )
        bot.send_message(chat_id=update.message.chat_id, text='Choose your timezone', reply_markup=reply)
    else:
        bot.send_message(chat_id=update.message.chat_id, text="Sorry, I've never heard of that timezone")


def main():
    if 'TELEGRAM_TOKEN' not in os.environ:
        logging.error('You need to set the environment variable "TELEGRAM_TOKEN"')
        return sys.exit(-1)
    updater = Updater(token=os.environ.get('TELEGRAM_TOKEN'))
    updater.dispatcher.add_handler(CommandHandler('timezone', handle_timezone_command, pass_args=True))
    updater.dispatcher.add_handler(MessageHandler(Filters.text, handle_incoming_message))
    updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_added_to_group))

    updater.start_polling()


if __name__ == '__main__':
    main()
