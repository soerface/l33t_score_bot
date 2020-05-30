# l33t score bot

Let it join a telegram group. It will give a point to
the person, who is the first to write anything between
13:37:00 and 13:37:59 on each day.

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

    docker-compose up
    
## Advanced configuration

The following environment variables can be used in .env file:
- REDIS_HOST
- REDIS_PORT

## Development setup

- Install [pipenv](https://github.com/pypa/pipenv)
- Install dependencies via `pipenv sync`
- Install [redis](https://redis.io/) (`apt install redis`)
