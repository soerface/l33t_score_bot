FROM python:3.11-slim
WORKDIR /

RUN pip install poetry

COPY poetry.lock pyproject.toml ./
RUN poetry install --no-interaction --no-ansi -vvv

RUN mkdir /app

WORKDIR /app

COPY app.py ./
ENTRYPOINT ["poetry", "run"]
CMD python app.py