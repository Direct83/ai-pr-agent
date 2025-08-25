import os
import requests
from typing import List, Dict, Any, Optional
from .config import GITHUB_TOKEN, GITHUB_REPO

API_URL = "https://api.github.com"


def _auth_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    if extra:
        h.update(extra)
    return h


def resolve_repo() -> str:
    repo = GITHUB_REPO or os.getenv("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("GITHUB_REPO не задан и GITHUB_REPOSITORY отсутствует. Ожидалось 'owner/repo'.")
    return repo


def get_pr_info(pr_number: int) -> Dict[str, Any]:
    repo = resolve_repo()
    url = f"{API_URL}/repos/{repo}/pulls/{pr_number}"
    r = requests.get(url, headers=_auth_headers())
    r.raise_for_status()
    return r.json()


def get_pr_diff_text(pr_number: int) -> str:
    repo = resolve_repo()
    url = f"{API_URL}/repos/{repo}/pulls/{pr_number}"
    r = requests.get(url, headers=_auth_headers({"Accept": "application/vnd.github.v3.diff"}))
    r.raise_for_status()
    return r.text


def get_pr_files(pr_number: int) -> List[Dict[str, Any]]:
    repo = resolve_repo()
    out: List[Dict[str, Any]] = []
    page = 1
    while True:
        url = f"{API_URL}/repos/{repo}/pulls/{pr_number}/files?page={page}&per_page=100"
        r = requests.get(url, headers=_auth_headers())
        r.raise_for_status()
        items = r.json()
        out.extend(items)
        if len(items) < 100:
            break
        page += 1
    return out


def post_inline_comments(pr_number: int, comments: List[Dict[str, Any]], commit_id: str) -> int:
    """
    Публикуем inline-комменты по одному.
    Ожидается: [{"path": str, "line": int, "body": str}, ...]
    """
    repo = resolve_repo()
    url = f"{API_URL}/repos/{repo}/pulls/{pr_number}/comments"
    posted = 0
    for c in comments:
        if not all(k in c for k in ("path", "line", "body")):
            continue
        payload = {
            "body": c["body"],
            "commit_id": commit_id,
            "path": c["path"],
            "line": int(c["line"]),
            "side": "RIGHT"
        }
        r = requests.post(url, headers=_auth_headers(), json=payload)
        if r.status_code in (200, 201):
            posted += 1
    return posted


def post_review_comment_reply(pr_number: int, comment_id: int, body: str):
    """
    Ответ в треде review-комментария.
    Рекомендуемый путь: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
    с payload {"body": ..., "in_reply_to": <comment_id>}
    """
    repo = resolve_repo()
    url = f"{API_URL}/repos/{repo}/pulls/{pr_number}/comments"
    payload = {"body": body, "in_reply_to": int(comment_id)}
    r = requests.post(url, headers=_auth_headers(), json=payload)
    r.raise_for_status()
    return r.json()


def get_review_comment(comment_id: int):
    """GET /repos/{owner}/{repo}/pulls/comments/{comment_id}"""
    repo = resolve_repo()
    url = f"{API_URL}/repos/{repo}/pulls/comments/{int(comment_id)}"
    r = requests.get(url, headers=_auth_headers())
    r.raise_for_status()
    return r.json()


def list_pull_review_comments(pr_number: int, per_page: int = 100):
    """GET /repos/{owner}/{repo}/pulls/{pull_number}/comments"""
    repo = resolve_repo()
    url = f"{API_URL}/repos/{repo}/pulls/{int(pr_number)}/comments"
    r = requests.get(url, headers=_auth_headers(), params={"per_page": per_page})
    r.raise_for_status()
    return r.json()


def get_review_thread(pr_number: int, comment_id: int):
    """
    Вернём весь тред для review-комментария:
    - узнаём root_id (in_reply_to_id или сам id),
    - берём все комменты PR и фильтруем по root_id,
    - сортируем по created_at по возрастанию.
    """
    try:
        c = get_review_comment(int(comment_id))
        root_id = c.get("in_reply_to_id") or c.get("id")
        comments = list_pull_review_comments(int(pr_number))
        thread = [
            x for x in comments
            if (x.get("id") == root_id) or (x.get("in_reply_to_id") == root_id)
        ]
        thread.sort(key=lambda x: x.get("created_at", ""))
        return thread
    except Exception as e:
        print(f"[github_client] get_review_thread failed: {e}")
        return []
