import os

COMMIT_SHA = os.getenv("COMMIT_SHA", "0000000000000000000000000000000000000000")

OPENAI_ENABLED_GROUPS = [
    -1001275377792,
    -379119028,
]

ADMIN_USER_ID: int | None = 19426036
