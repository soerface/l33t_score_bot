import logging
from typing import List

import pytz
from telegram import Update, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext

from db import redis
from utils import get_timezone_region_markup, build_chat_scores

logger = logging.getLogger(__name__)


async def timezone_command(update: Update, context: CallbackContext):
    continents = sorted(set([x.partition('/')[0] for x in pytz.common_timezones]))
    current_timezone = redis.get(f'group:{update.message.chat_id}:settings:timezone')
    reply = get_timezone_region_markup(continents)
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=f'Your current timezone is set to "{current_timezone}". '
             'If you want to change it, choose your region',
        reply_markup=reply
    )


async def inlinebutton_click(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    cmd, *args = query.data.split(':')

    if cmd == 'timezone':
        await _inlinebutton_timezone(update, context, query, args)
    elif cmd == 'cancel':
        await query.edit_message_text('Canceled')

    await query.answer()


async def score_command(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.message.chat_id, text=build_chat_scores(update.message.chat_id))


async def clock_command(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    current_timezone = redis.get(f'group:{chat_id}:settings:timezone')
    if not current_timezone:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry to interrupt you, but you need to set a /timezone"
        )
        return
    tz = pytz.timezone(current_timezone)
    msg_sent_date = update.message.date.astimezone(tz)
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=f'I received your message at {msg_sent_date}'
    )


async def my_id_command(update: Update, context: CallbackContext):
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text='\n'.join([
            f'set group:{update.message.chat_id}:score:{update.message.from_user.id} X',
            f'set user:{update.message.from_user.id}:name "{update.message.from_user.first_name}"'
        ])
    )


async def sprueche_command(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.message.chat_id, text='Du musst schon "AN" oder "AUS" sagen')
        return
    if context.args[0] == 'AN':
        redis.set(f'group:{update.message.chat_id}:settings:sprueche', 1)
        logger.info(f"Sprueche were enabled in {update.message.chat_id}")
        await context.bot.send_message(chat_id=update.message.chat_id, text='Na wenn ihr das vertragt')
    elif context.args[0] == 'AUS':
        redis.delete(f'group:{update.message.chat_id}:settings:sprueche')
        logger.info(f"Sprueche were disabled in {update.message.chat_id}")
        await context.bot.send_message(chat_id=update.message.chat_id, text='Dann halt nich')


async def sprueche_early_command(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.message.chat_id, text='Du musst schon "AN" oder "AUS" sagen')
        return
    if context.args[0] == 'AN':
        redis.set(f'group:{update.message.chat_id}:settings:sprueche_early', 1)
        await context.bot.send_message(chat_id=update.message.chat_id, text='Na wenn ihr das vertragt')
    elif context.args[0] == 'AUS':
        redis.delete(f'group:{update.message.chat_id}:settings:sprueche_early')
        await context.bot.send_message(chat_id=update.message.chat_id, text='Dann halt nich')


async def start_command(update: Update, context: CallbackContext):
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text="Hi there! I'll check the 13:37 score in a group chat. "
             "Just add me to a group, and when the clock says "
             "13:37, be the first to write something in the group!",
        reply_markup=ReplyKeyboardRemove()
    )
    # "If you want to, I'll pin the current score to the chat. "
    # "Make me an admin of the group to allow me to do that.")


async def _inlinebutton_timezone(update: Update, context: CallbackContext, query: CallbackQuery, args: List[str]):
    continents = sorted(set([x.partition('/')[0] for x in pytz.common_timezones]))
    location = args[0]
    if location == 'region_selection':
        reply = get_timezone_region_markup(continents)
        await query.edit_message_text('Choose your region')
        await query.edit_message_reply_markup(reply)
    elif location in pytz.all_timezones:
        redis.set(f'group:{query.message.chat_id}:settings:timezone', location)
        tz = pytz.timezone(location)
        local_time = query.message.date.astimezone(tz).strftime('%X')
        reply = InlineKeyboardMarkup(
            [[(InlineKeyboardButton('Change timezone', callback_data='timezone:region_selection'))]]
        )
        await query.edit_message_text(
            f'Timezone of this chat was set to {location}. '
            f'Looks like it was {local_time} when you sent the last /timezone command. '
            'If this is incorrect, please execute /timezone again or click the button below.'
        )
        await query.edit_message_reply_markup(reply)
    elif location in continents:
        zones = [x for x in pytz.all_timezones if x.startswith(location)]
        reply = InlineKeyboardMarkup(
            [[InlineKeyboardButton(x.partition('/')[2], callback_data=':'.join(['timezone', x]))] for x in zones]
            + [[(InlineKeyboardButton('« Back', callback_data='timezone:region_selection'))]],
        )
        await query.edit_message_text('Choose your timezone')
        await query.edit_message_reply_markup(reply)
