from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from db import redis


def get_timezone_region_markup(continents):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(x, callback_data=':'.join(['timezone', x])) for x in continents[i:i + 3]]
         for i in range(0, len(continents), 3)]
    )


def build_chat_scores(chat_id: int, indent: int = 0):
    scores = []
    for key in redis.scan_iter(f'group:{chat_id}:score:*'):
        user_id = int(key.rpartition(':')[2])
        name = redis.get(f'user:{user_id}:name')
        value = int(redis.get(key))
        scores.append((name, value))
    if not scores:
        return 'No one has made any points so far…'
    scores = sorted(scores, key=lambda x: x[1], reverse=True)
    space = " " * indent
    return '\n'.join([f'{space}- {x[0]}: {x[1]}' for x in scores])
