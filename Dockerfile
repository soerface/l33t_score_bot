FROM python:3.11-slim
WORKDIR /

RUN pip install poetry

COPY poetry.lock pyproject.toml ./
RUN poetry install --no-interaction --no-ansi -vvv

RUN mkdir /app

WORKDIR /app

ARG COMMIT_SHA
ENV COMMIT_SHA=$COMMIT_SHA

COPY src/. ./
ENTRYPOINT ["poetry", "run"]
CMD python app.py