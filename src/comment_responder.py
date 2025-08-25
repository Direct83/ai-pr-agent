"""
Responder по упоминанию бота (@ai-reviewer) в комментариях PR.
Событие: issue_comment (PR — это вид issue).
Видит историю обсуждения (issue comments последних ~20) и отвечает одним сообщением.
"""
import json
import os
from typing import List, Dict, Any

from langchain_openai import ChatOpenAI
from .config import OPENAI_MODEL, BOT_MENTION
from .github_client import get_issue_comments, post_issue_comment

SYSTEM = (
    "Ты помощник-ревьюер. Отвечай кратко и по делу. "
    "Давай конкретику по code style и безопасности. Если контекста не хватает — попроси уточнить."
)


def _contains_mention(text: str, mention: str) -> bool:
    return mention.lower() in (text or "").lower()


def run_responder(pr_number: int, trigger_text: str):
    if not _contains_mention(trigger_text, BOT_MENTION):
        return
    history = get_issue_comments(pr_number)  # все комменты PR (issue)
    convo_lines: List[str] = []
    for c in history[-20:]:  # последние 20 сообщений
        user = (c.get("user") or {}).get("login") or "user"
        body = c.get("body") or ""
        convo_lines.append(f"{user}: {body}")

    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    prompt = (
        "Контекст обсуждения (последние сообщения):\n"
        + "\n".join(convo_lines)
        + "\n\nОтветь на последний вопрос/замечание."
    )
    resp = llm.invoke([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}])
    text = (getattr(resp, "content", None) or "").strip() or "Нужны детали: укажи файл/строку и суть вопроса."
    post_issue_comment(pr_number, text)


if __name__ == "__main__":
    # GitHub Actions кладёт событие в файл GITHUB_EVENT_PATH
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        raise SystemExit("GITHUB_EVENT_PATH not set")
    with open(event_path, "r", encoding="utf-8") as f:
        evt = json.load(f)

    # Интересуют только новые комментарии
    if evt.get("action") != "created":
        raise SystemExit(0)

    # Это должен быть комментарий к PR (а не к обычному issue)
    issue = evt.get("issue") or {}
    if "pull_request" not in issue:
        raise SystemExit(0)

    body = (evt.get("comment") or {}).get("body") or ""
    pr_number = issue.get("number")
    if not pr_number or not body:
        raise SystemExit(0)

    run_responder(int(pr_number), body)
