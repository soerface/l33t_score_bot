import logging
from datetime import timedelta, datetime
from typing import List

import pytz
from telegram import (
    Update,
    CallbackQuery,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    User,
)
from telegram.constants import ChatAction
from telegram.ext import CallbackContext

import ai
from constants import OPENAI_ENABLED_GROUPS
from db import redis
from utils import (
    get_timezone_region_markup,
    build_chat_scores,
    decrease_score,
    increase_score,
)

logger = logging.getLogger(__name__)


async def timezone_command(update: Update, context: CallbackContext):
    continents = sorted(set([x.partition("/")[0] for x in pytz.common_timezones]))
    current_timezone = redis.get(f"group:{update.message.chat_id}:settings:timezone")
    reply = get_timezone_region_markup(continents)
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=f'Your current timezone is set to "{current_timezone}". '
        "If you want to change it, choose your region",
        reply_markup=reply,
    )


async def inlinebutton_click(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    cmd, *args = query.data.split(":")

    if cmd == "timezone":
        await _inlinebutton_timezone(update, context, query, args)
    elif cmd == "cancel":
        await query.edit_message_text("Canceled")

    await query.answer()


async def score_command(update: Update, context: CallbackContext):
    await context.bot.send_message(
        chat_id=update.message.chat_id, text=build_chat_scores(update.message.chat_id)
    )


async def clock_command(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    current_timezone = redis.get(f"group:{chat_id}:settings:timezone")
    if not current_timezone:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry to interrupt you, but you need to set a /timezone",
        )
        return
    tz = pytz.timezone(current_timezone)
    msg_sent_date = update.message.date.astimezone(tz)
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=f"I received your message at {msg_sent_date}",
    )


async def my_id_command(update: Update, context: CallbackContext):
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text="\n".join(
            [
                f"set group:{update.message.chat_id}:score:{update.message.from_user.id} X",
                f'set user:{update.message.from_user.id}:name "{update.message.from_user.first_name}"',
            ]
        ),
    )


async def added_to_group(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if member["id"] == context.bot.id:
            logger.info(f"Added to group {update.message.chat}")
            await update.message.reply_text(
                "Hi! Would you mind telling me your /timezone?"
            )
    if update.message.chat_id in OPENAI_ENABLED_GROUPS:
        redis.set(f"group:{update.message.chat_id}:settings:openai", "1")


async def removed_from_group(update: Update, context: CallbackContext):
    if update.message.left_chat_member["id"] == context.bot.id:
        logger.info(f"Removed from group {update.message.chat}")
        for key in redis.scan_iter(f"group:{update.message.chat_id}:*"):
            logger.debug(f"Removing from redis: {key}")
            redis.delete(key)


async def start_command(update: Update, context: CallbackContext):
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text="Hi there! I'll check the 13:37 score in a group chat. "
        "Just add me to a group, and when the clock says "
        "13:37, be the first to write something in the group!",
        reply_markup=ReplyKeyboardRemove(),
    )
    # "If you want to, I'll pin the current score to the chat. "
    # "Make me an admin of the group to allow me to do that.")


async def challenge_callback(context: CallbackContext):
    chat_id = context.job.chat_id
    # data = context.job.data
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    challenge = ai.get_challenge_message()
    redis.set(f"group:{chat_id}:last_challenge", challenge)
    await context.bot.send_message(
        chat_id=chat_id,
        text=challenge,
    )


async def challenge_command(update: Update, context: CallbackContext):
    if not redis.get(f"group:{update.message.chat_id}:settings:openai"):
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="I'm sorry, but this feature is not available for this group.",
        )
        return

    # cancel all previous jobs
    for job in context.job_queue.get_jobs_by_name(
        f"challenge_{update.message.chat_id}"
    ):
        job.schedule_removal()

    redis.delete(f"group:{update.message.chat_id}:last_challenge")

    timezone = redis.get(f"group:{update.message.chat_id}:settings:timezone")
    tz = pytz.timezone(timezone)
    due = tz.localize(
        datetime.now().replace(hour=13, minute=37, second=0, microsecond=0)
    )
    # DEBUG
    # due = datetime.now(tz) + timedelta(seconds=1)
    if datetime.now(tz) > due:
        due += timedelta(days=1)
    # Just pretend that for tomorrow, the regular 1337 challenge was already scored.
    # Otherwise, after the challenge is done, it will give extra points for the next message after the challenge.
    # Known downside: If you don't use the bot for multiple days and then start a challenge, the bot will
    # not notice that it earns points for the forgotten days. This would need to be checked here before the
    # "last_scored_day" is overwritten.
    redis.set(
        f"group:{update.message.chat_id}:last_scored_day",
        due.strftime("%Y-%m-%d"),
    )
    chat_id = update.message.chat_id
    context.job_queue.run_once(
        challenge_callback,
        due.astimezone(pytz.utc),
        chat_id=chat_id,
        name=f"challenge_{chat_id}",
        # data="foobar",
    )
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=(
            f"Neue Challenge aktiviert. Ich melde mich wieder am {due.strftime('%d.%m.%Y um %H:%M:%S %Z')} "
            "(falls ich zwischendurch nicht neugestartet werde)."
        ),
    )


async def group_chat_message_with_challenges(
    challenge: str, update: Update, context: CallbackContext
):
    user_answer = update.message.text
    chat_id = update.message.chat_id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    if ai.answer_is_correct(challenge, user_answer):
        winner: User = update.message.from_user
        increase_score(chat_id, winner)
        redis.delete(f"group:{chat_id}:last_challenge")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        message = ai.get_challenge_won_message(
            bot_name=context.bot.first_name,
            username=winner.first_name,
            current_scores=build_chat_scores(chat_id, indent=2),
            question=challenge,
            answer=user_answer,
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
        )
    else:
        looser: User = update.message.from_user
        decrease_score(chat_id, looser)
        increase_score(chat_id, context.bot)
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        message = ai.get_challenge_lost_message(
            bot_name=context.bot.first_name,
            username=looser.first_name,
            current_scores=build_chat_scores(chat_id, indent=2),
            question=challenge,
            answer=user_answer,
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
        )


async def group_chat_message(update: Update, context: CallbackContext):
    chat_id: int = update.message.chat_id
    current_timezone = redis.get(f"group:{chat_id}:settings:timezone")
    if not current_timezone:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry to interrupt you, but you need to set a /timezone",
        )
        return

    # check if a challenge is running
    if challenge := redis.get(f"group:{chat_id}:last_challenge"):
        await group_chat_message_with_challenges(challenge, update, context)
        return

    tz = pytz.timezone(current_timezone)
    msg_sent_date = update.message.date.astimezone(tz)
    hour, minute = msg_sent_date.hour, msg_sent_date.minute

    today = msg_sent_date.strftime("%Y-%m-%d")
    yesterday = (msg_sent_date - timedelta(days=1)).strftime("%Y-%m-%d")
    last_scored_day = redis.get(f"group:{chat_id}:last_scored_day") or yesterday
    # last_scored_day = (msg_sent_date - timedelta(days=1)).strftime("%Y-%m-%d")  # DEBUG
    this_day = datetime.strptime(today, "%Y-%m-%d").astimezone(tz)
    last_day = datetime.strptime(last_scored_day, "%Y-%m-%d").astimezone(tz)
    delta = this_day - last_day

    if hour == 13 and minute == 36:
        looser: User = update.message.from_user
        await decrease_score(chat_id, looser)
        current_score = int(redis.get(f"group:{chat_id}:score:{looser.id}"))
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        if current_score >= 0 and redis.get(
            f"group:{update.message.chat_id}:settings:openai"
        ):
            text = ai.get_too_early_message(
                looser.first_name, update.message.text, current_score
            )
            await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="That was too early. That's gonna cost you a point.",
            )

    # elif delta.days >= 1:  # DEBUG
    elif hour == 13 and minute == 37 and delta.days >= 1:
        winner: User = update.message.from_user
        increase_score(chat_id, winner)
        redis.set(f"group:{chat_id}:last_scored_day", today)
        if redis.get(f"group:{update.message.chat_id}:settings:openai"):
            if delta.days > 1:
                bot_wins_extra = delta.days - 1
                increase_score(chat_id, context.bot, n=bot_wins_extra)
            else:
                bot_wins_extra = 0
            await context.bot.send_chat_action(
                chat_id=chat_id, action=ChatAction.TYPING
            )
            text = ai.get_success_message(
                context.bot.first_name,
                winner.first_name,
                update.message.text,
                build_chat_scores(chat_id, indent=2),
                bot_wins_extra=bot_wins_extra,
            )
            await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=f"Congratz, {winner.first_name}! Scores:"
            )
            if delta.days > 1:
                n = delta.days - 1
                msg = "day" if n == 1 else f"{n} days"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Wait a second. You forgot the last {msg}. So I'll get some points, too.",
                )
                increase_score(chat_id, context.bot, n=n)
            await context.bot.send_message(
                chat_id=chat_id, text=build_chat_scores(chat_id)
            )

    elif (
        ((hour == 13 and minute > 37) or hour > 13)
        and delta.days == 1
        or delta.days > 1
    ):
        # elif delta.days > 1:  # DEBUG
        logger.info(f"Last scored day: {last_scored_day}")
        if (hour == 13 and minute > 37) or hour > 13:
            n = delta.days
            redis.set(f"group:{chat_id}:last_scored_day", today)
        else:
            n = delta.days - 1
            redis.set(f"group:{chat_id}:last_scored_day", yesterday)

        logger.info(f"Bot gets {n} points")
        increase_score(chat_id, context.bot, n=n)
        logger.info("Sending message")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        logger.info("Chat action sent")

        if redis.get(f"group:{update.message.chat_id}:settings:openai"):
            logger.info("Using OpenAI")
            text = ai.get_lost_message(
                context.bot.first_name,
                update.message.from_user.first_name,
                update.message.text,
                build_chat_scores(chat_id, indent=2),
                n,
            )
            logger.info("Message generated")
            await context.bot.send_message(chat_id=chat_id, text=text)
            logger.info("Message sent")
        else:
            await context.bot.send_message(
                chat_id=chat_id, text="Oh dear. You forgot 13:37. Point for me"
            )

            if n > 1:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"You even forgot it for {n} days... I'm disappointed.",
                )
            await context.bot.send_message(
                chat_id=chat_id, text=build_chat_scores(chat_id)
            )


async def _inlinebutton_timezone(
    update: Update, context: CallbackContext, query: CallbackQuery, args: List[str]
):
    continents = sorted(set([x.partition("/")[0] for x in pytz.common_timezones]))
    location = args[0]
    if location == "region_selection":
        reply = get_timezone_region_markup(continents)
        await query.edit_message_text("Choose your region")
        await query.edit_message_reply_markup(reply)
    elif location in pytz.all_timezones:
        redis.set(f"group:{query.message.chat_id}:settings:timezone", location)
        tz = pytz.timezone(location)
        local_time = query.message.date.astimezone(tz).strftime("%X")
        reply = InlineKeyboardMarkup(
            [
                [
                    (
                        InlineKeyboardButton(
                            "Change timezone", callback_data="timezone:region_selection"
                        )
                    )
                ]
            ]
        )
        await query.edit_message_text(
            f"Timezone of this chat was set to {location}. "
            f"Looks like it was {local_time} when you sent the last /timezone command. "
            "If this is incorrect, please execute /timezone again or click the button below."
        )
        await query.edit_message_reply_markup(reply)
    elif location in continents:
        zones = [x for x in pytz.all_timezones if x.startswith(location)]
        reply = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        x.partition("/")[2], callback_data=":".join(["timezone", x])
                    )
                ]
                for x in zones
            ]
            + [
                [
                    (
                        InlineKeyboardButton(
                            "« Back", callback_data="timezone:region_selection"
                        )
                    )
                ]
            ],
        )
        await query.edit_message_text("Choose your timezone")
        await query.edit_message_reply_markup(reply)
