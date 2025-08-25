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


def post_issue_comment(pr_number: int, body: str):
    repo = resolve_repo()
    url = f"{API_URL}/repos/{repo}/issues/{pr_number}/comments"
    r = requests.post(url, headers=_auth_headers(), json={"body": body})
    r.raise_for_status()
    return r.json()


def get_issue_comments(pr_number: int) -> List[Dict[str, Any]]:
    repo = resolve_repo()
    out: List[Dict[str, Any]] = []
    page = 1
    while True:
        url = f"{API_URL}/repos/{repo}/issues/{pr_number}/comments?page={page}&per_page=100"
        r = requests.get(url, headers=_auth_headers())
        r.raise_for_status()
        items = r.json()
        out.extend(items)
        if len(items) < 100:
            break
        page += 1
    return out


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
