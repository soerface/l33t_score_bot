import os

from redis import Redis

redis = Redis(
    host=os.environ.get("REDIS_HOST", "redis"),
    port=os.environ.get("REDIS_PORT", 6379),
    charset="utf-8",
    decode_responses=True,
)
