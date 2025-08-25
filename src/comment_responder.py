"""
Responder по упоминанию бота (@ai-reviewer) в комментариях PR.
Событие: issue_comment (PR — это вид issue).
Видит историю обсуждения (issue comments последних ~20) и отвечает одним сообщением.
"""
import json
import os
from typing import List

from langchain_openai import ChatOpenAI
from .config import OPENAI_MODEL, BOT_MENTION
from .github_client import get_issue_comments, post_issue_comment

SYSTEM = (
    "Ты помощник-ревьюер. Отвечай кратко и по делу. "
    "Давай конкретику по code style и безопасности. Если контекста не хватает — попроси уточнить."
)


def _contains_mention(text: str, mention: str) -> bool:
    return (mention or "").lower() in (text or "").lower()


def _safe_resp_text(resp) -> str:
    # Универсально достаём текст из ответа LLM
    if hasattr(resp, "content") and isinstance(resp.content, str):
        return resp.content
    if hasattr(resp, "content") and isinstance(resp.content, list):
        parts = []
        for c in resp.content:
            t = getattr(c, "text", None)
            if t:
                parts.append(t)
        return "\n".join(parts)
    return str(resp or "")


def run_responder(pr_number: int, trigger_text: str):
    if not _contains_mention(trigger_text, BOT_MENTION):
        print(f"[responder] no mention in comment: {trigger_text!r}")
        return

    # Берём последние ~20 сообщений из обсуждения PR (issue comments)
    history = get_issue_comments(pr_number)
    convo_lines: List[str] = []
    for c in history[-20:]:
        user = (c.get("user") or {}).get("login") or "user"
        body = c.get("body") or ""
        convo_lines.append(f"{user}: {body}")

    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    prompt = (
        "Контекст обсуждения (последние сообщения):\n"
        + "\n".join(convo_lines)
        + "\n\nОтветь на последний вопрос/замечание."
    )
    resp = llm.invoke(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": prompt}]
    )
    text = _safe_resp_text(resp).strip() or "Нужны детали: укажи файл/строку и суть вопроса."
    post_issue_comment(pr_number, text)
    print(f"[responder] replied to PR #{pr_number}")


if __name__ == "__main__":
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        raise SystemExit("GITHUB_EVENT_PATH not set")

    with open(event_path, "r", encoding="utf-8") as f:
        evt = json.load(f)

    action = evt.get("action")
    if action != "created":
        print(f"[responder] skip: action={action}")
        raise SystemExit(0)

    pr_number = None
    body = ""

    # Поддерживаем ДВА источника событий:
    # 1) issue_comment — комментарии во вкладке Conversation PR
    # 2) pull_request_review_comment — inline-комментарии к строкам кода
    if event_name == "issue_comment":
        issue = evt.get("issue") or {}
        if "pull_request" not in issue:
            print("[responder] skip: comment is not on a PR")
            raise SystemExit(0)
        pr_number = issue.get("number")
        body = (evt.get("comment") or {}).get("body") or ""
    elif event_name == "pull_request_review_comment":
        pr = evt.get("pull_request") or {}
        pr_number = pr.get("number")
        body = (evt.get("comment") or {}).get("body") or ""
    else:
        print(f"[responder] unsupported event: {event_name}")
        raise SystemExit(0)

    print(f"[responder] event={event_name} pr={pr_number} body={body!r}")
    if not pr_number or not body:
        raise SystemExit(0)

    run_responder(int(pr_number), body)
