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
    get_review_thread,
    post_issue_comment,
    post_review_comment_reply,
)

SYSTEM = (
    "Ты помощник-ревьюер. Отвечай на русском кратко и по делу. "
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


def _ask_llm(history_lines: List[str], tail_hint: str) -> str:
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    prompt = (
        "Контекст обсуждения (последние сообщения):\n"
        + "\n".join(history_lines[-20:])
        + f"\n\nЗадача: {tail_hint}\n"
        "Отвечай максимально предметно, коротко, на русском."
    )
    resp = llm.invoke(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": prompt}]
    )
    return (_safe_resp_text(resp).strip()
            or "Уточни вопрос: к какой строке/файлу и что именно смущает?")


def _issue_history(pr_number: int) -> List[str]:
    msgs = []
    for c in get_issue_comments(int(pr_number))[-20:]:
        user = (c.get("user") or {}).get("login") or "user"
        body = c.get("body") or ""
        msgs.append(f"{user}: {body}")
    return msgs


if __name__ == "__main__":
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        raise SystemExit("GITHUB_EVENT_PATH not set")

    with open(event_path, "r", encoding="utf-8") as f:
        evt = json.load(f)

    if evt.get("action") != "created":
        print(f"[responder] skip: action={evt.get('action')}")
        raise SystemExit(0)

    # 1) Комментарии во вкладке Conversation
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

        history = _issue_history(int(pr_number))
        text = _ask_llm(history, "Ответь на последний вопрос/замечание из обсуждения PR.")
        post_issue_comment(int(pr_number), text)
        print(f"[responder] issue reply posted to PR #{pr_number}")
        raise SystemExit(0)

    # 2) Инлайн-комментарии к строкам кода (review comments)
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

        # Собираем тред инлайн-обсуждения + хвост обсуждений из Conversation
        thread = get_review_thread(int(pr_number), int(comment_id))
        thread_lines: List[str] = []
        for c in thread:
            user = (c.get("user") or {}).get("login") or "user"
            t = c.get("body") or ""
            thread_lines.append(f"{user}: {t}")

        # если по какой-то причине тред пуст — подстрахуемся issue-историей и самим вопросом
        if not thread_lines:
            thread_lines = _issue_history(int(pr_number))
            thread_lines.append(f"author: {body}")

        text = _ask_llm(thread_lines, "Ответь по текущему треду к изменённой строке.")
        post_review_comment_reply(int(pr_number), int(comment_id), text)
        print(f"[responder] inline reply posted (PR {pr_number}, in_reply_to={comment_id})")
        raise SystemExit(0)

    print(f"[responder] unsupported event: {event_name}")
    raise SystemExit(0)
