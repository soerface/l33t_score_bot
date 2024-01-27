# l33t score bot

Let it join a telegram group. It will give a point to
the person, who is the first to write anything between
13:37:00 and 13:37:59 on each day.

Get started: https://t.me/leet_score_bot

## Setup

Create a bot account with [BotFather](https://t.me/BotFather).
Disable the [privacy mode](https://core.telegram.org/bots#privacy-mode) so it will be able
to read every message.

    # Write this in the chat to the BotFather
    /newbot
    Printable Name for the bot
    username_of_your_bot
    /setprivacy
    @username_of_your_bot
    Disable

Copy `example.env` to `.env`. Enter the token you received from the bot father.

Install [docker](https://docs.docker.com/engine/install/) and
[docker-compose](https://docs.docker.com/compose/install/#install-compose).

Spin up the application:

    docker compose up
    
## Advanced configuration

The following environment variables can be used in .env file:
- REDIS_HOST
- REDIS_PORT
- LOG_LEVEL, value can be one of the following:
    - CRITICAL
    - ERROR
    - WARNING
    - INFO (default)
    - DEBUG

## Development setup

- Install [poetry](https://python-poetry.org/)
- Install dependencies via `poetry install`
- Run `docker compose -f docker-compose.dev.yml up`
- Run
  - `export TELEGRAM_TOKEN=your_token`
  - `export REDIS_HOST=localhost`
- Run `poetry run python app.py`