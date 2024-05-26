import json
import logging
import os
from datetime import datetime
from typing import Mapping

from openai import OpenAI

logger = logging.getLogger(__name__)


def make_query(
    prompt: str, *args, logger_extra: Mapping[str, object] | None = None
) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        return "Couldn't reach OpenAI"
    client = OpenAI(
        api_key=api_key,
    )
    messages = [
        {"role": "system", "content": prompt},
        *args,
    ]
    logger.info(
        f"""Making query: <pre>
{json.dumps(messages, indent=2)}
</pre>""",
        extra=logger_extra,
    )
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        # model="gpt-4-turbo-preview",  # long response times
        messages=messages,
    )
    logger.info(f"Response: <code>{response}</code>", extra=logger_extra)
    return response.choices[0].message.content


def get_too_early_message(
    username: str,
    chatmessage: str,
    points_left: int,
    logger_extra: Mapping[str, object] | None = None,
) -> str:
    prompt = f"""
{username} hat heute um 13:36 statt 13:37 eine Chatnachricht geschrieben und damit einen Punkt verloren.
Die Person hat jetzt noch {points_left}. Die Nachricht war: "{chatmessage}". Beleidige die Person lustig dafür.
"""
    return make_query(prompt, logger_extra=logger_extra)


def get_success_message(
    bot_name: str,
    username: str,
    chatmessage: str,
    current_scores: str,
    bot_wins_extra: int = 0,
    logger_extra: Mapping[str, object] | None = None,
) -> str:
    if bot_wins_extra > 0:
        extra_text = (
            f"Weil die letzten {bot_wins_extra} Tage niemand um 13:37 geschrieben hat, hast "
            f"du {bot_wins_extra} Punkt(e) erhalten. Mache dich darüber besonders lustig.\n"
        )
    else:
        extra_text = ""
    now = datetime.now()
    prompt = f"""
Du bist {bot_name}. {username} hat heute um 13:37 die erste Chatnachricht geschrieben und damit einen Punkt erhalten.
Gib eine lustige Antwort auf seine Nachricht. Mache dich über den Punktestand aller Teilnehmer lustig.
{extra_text}
- Heute ist der {now.strftime("%d.%m.%Y")}
- Der Inhalt der Chatnachricht ist: "{chatmessage}"
- Aktuelle Punktzahl:
{current_scores}
- Man bekommt Punkte abgezogen, wenn man um 13:36 schreibt
- Du bekommst Punkte für jeden Tag, an dem jemand anders NICHT um 13:37 schreibt"""
    return make_query(prompt, logger_extra=logger_extra)


def get_lost_message(
    bot_name: str,
    username: str,
    chatmessage: str,
    current_scores: str,
    bot_points: int,
    logger_extra: Mapping[str, object] | None = None,
) -> str:
    now = datetime.now()
    prompt = f"""
Du bist {bot_name}.
Weil die Chatteilnehmer die letzten {bot_points} Tage vergessen haben,
um 13:37 zu schreiben, hast du {bot_points} Punkt(e) erhalten.
Mache dich über den Punktestand aller Teilnehmer lustig. Achte genau darauf, auf welchem Platz du selbst bist.
Mache dich über die letzte Nachricht lustig.

- Heute ist der {now.strftime("%d.%m.%Y")}
- Letzte Nachricht (von {username}): "{chatmessage}"
- Aktuelle Punktzahl:
{current_scores}
- Man bekommt Punkte abgezogen, wenn man um 13:36 schreibt
- Du bekommst Punkte für jeden Tag, an dem jemand anders NICHT um 13:37 schreibt"""
    return make_query(prompt, logger_extra=logger_extra)


def get_challenge_message(logger_extra: Mapping[str, object] | None = None) -> str:
    now = datetime.now()
    prompt = f"""
Du bist ein Quizmaster. Stelle eine Frage zu dem heutigen Datum, den {now.strftime("%d.%m")}.
Die Frage muss beantwortbar sein. Sie muss der Realität entsprechen, prüfe die Fakten genau.
Die Frage darf nicht zu spezifisch sein, damit sie von den meisten beantwortet werden kann.
Sie darf nicht zu einfach sein, damit nicht alle Teilnehmer die Antwort wissen.
Gib keine Antwortmöglichkeiten an.
"""
    return make_query(prompt, logger_extra=logger_extra)


def answer_is_correct(
    question: str, answer: str, logger_extra: Mapping[str, object] | None = None
) -> bool:
    prompt = f"""
    Bewerte die Antwort auf eine Quizfrage. Antworte nur mit "Richtig" oder "Falsch".
    Prüfe die Fakten genau.
    Frage: "{question}"
    """
    response = make_query(
        prompt,
        {"role": "user", "content": answer},
        logger_extra=logger_extra,
    )
    logger.info(f"AI response: {response}")
    return "richtig" in response.strip().lower()


def get_challenge_won_message(
    *,
    bot_name: str,
    username: str,
    current_scores: str,
    question: str,
    answer: str,
    logger_extra: Mapping[str, object] | None = None,
) -> str:
    prompt = f"""
Du bist {bot_name}.
Weil {username} die Quizfrage richtig beantwortet hat, hat er einen Punkt erhalten.
Lobe {username} für die Antwort, mache dich über die übrigen Teilnehmer lustig.
Gib Fun-Facts zu der Frage und der Antwort.

- Die Quizfrage lautete: "{question}"
- Die Antwort von {username} war: "{answer}"
- Aktuelle Punktzahl:
{current_scores}
"""
    return make_query(prompt, logger_extra=logger_extra)


def get_challenge_lost_message(
    *,
    bot_name: str,
    username: str,
    current_scores: str,
    question: str,
    answer: str,
    logger_extra: Mapping[str, object] | None = None,
) -> str:
    prompt = f"""
Weil {username} die Quizfrage nicht richtig beantwortet hat, hat er einen Punkt verloren und du einen Punkt erhalten.
Mache dich über die Antwort von {username} lustig. Gib NICHT die richtige Antwort an.

- Die Quizfrage lautete: "{question}"
- Die Antwort von {username} war: "{answer}"
    """
    return make_query(prompt, logger_extra=logger_extra)
