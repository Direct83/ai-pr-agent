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
from .github_client import (
    get_issue_comments,
    post_issue_comment,
    post_review_comment_reply,  # NEW
)

SYSTEM = (
    "Ты помощник-ревьюер. Отвечай кратко и по делу. "
    "Давай конкретику по code style и безопасности. Если контекста не хватает — попроси уточнить."
)


def _contains_mention(text: str, mention: str) -> bool:
    return (mention or "").lower() in (text or "").lower()


def _safe_resp_text(resp) -> str:
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


def _llm_reply(history_lines: List[str]) -> str:
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    prompt = (
        "Контекст обсуждения (последние сообщения):\n"
        + "\n".join(history_lines[-20:])
        + "\n\nОтветь на последний вопрос/замечание."
    )
    resp = llm.invoke(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": prompt}]
    )
    return _safe_resp_text(resp).strip() or "Нужны детали: укажи файл/строку и суть вопроса."


def _build_history(pr_number: int) -> List[str]:
    # берём issue-комменты PR как «историю» — этого хватает для ответа
    history = get_issue_comments(pr_number)
    out: List[str] = []
    for c in history[-20:]:
        user = (c.get("user") or {}).get("login") or "user"
        body = c.get("body") or ""
        out.append(f"{user}: {body}")
    return out


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

    # Общие поля
    pr_number = None
    body = ""

    # 1) Комментарии в Conversation PR
    if event_name == "issue_comment":
        issue = evt.get("issue") or {}
        if "pull_request" not in issue:
            print("[responder] skip: comment is not on a PR")
            raise SystemExit(0)
        pr_number = issue.get("number")
        body = (evt.get("comment") or {}).get("body") or ""
        print(f"[responder] event=issue_comment pr={pr_number} body={body!r}")

        if not _contains_mention(body, BOT_MENTION):
            print("[responder] no mention in issue_comment")
            raise SystemExit(0)

        history_lines = _build_history(int(pr_number))
        text = _llm_reply(history_lines)
        post_issue_comment(int(pr_number), text)
        print(f"[responder] issue reply posted to PR #{pr_number}")
        raise SystemExit(0)

    # 2) ИНЛАЙН-комментарии к строкам кода
    if event_name == "pull_request_review_comment":
        pr = evt.get("pull_request") or {}
        pr_number = pr.get("number")
        comment = evt.get("comment") or {}
        body = (comment.get("body") or "")
        comment_id = comment.get("id")
        print(f"[responder] event=pull_request_review_comment pr={pr_number} comment_id={comment_id} body={body!r}")

        if not (pr_number and comment_id and _contains_mention(body, BOT_MENTION)):
            print("[responder] skip inline: missing data or no mention")
            raise SystemExit(0)

        history_lines = _build_history(int(pr_number))
        text = _llm_reply(history_lines)
        # ВАЖНО: отвечаем в треде этого комментария
        post_review_comment_reply(int(comment_id), text)
        print(f"[responder] inline reply posted under comment {comment_id} (PR #{pr_number})")
        raise SystemExit(0)

    print(f"[responder] unsupported event: {event_name}")
    raise SystemExit(0)
