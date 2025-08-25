from typing import TypedDict, List, Dict, Any
from typing import Annotated
import operator

from langgraph.graph import StateGraph, END

from .agents.codestyle_agent import run_codestyle_agent
from .agents.security_agent import run_security_agent
from .utils import resolve_positions, merge_by_line_match
from .github_client import post_inline_comments


class ReviewState(TypedDict, total=False):
    # входные данные
    pr_number: int
    head_sha: str
    diff_text: str
    diff_index: Dict[str, List]
    # коллекция сырых комментариев от агентов (накапливаем из параллельных веток)
    raw_comments: Annotated[List[Dict[str, Any]], operator.add]
    # выход/флаги
    final_comments: List[Dict[str, Any]]
    codestyle_done: bool
    security_done: bool
    posted: bool


def start_node(state: ReviewState) -> Dict[str, Any]:
    # Ничего не делает — точка ветвления на параллельные узлы
    return {}


def codestyle_node(state: ReviewState) -> Dict[str, Any]:
    items = run_codestyle_agent(state["diff_text"])
    tagged: List[Dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        body = (it.get("body") or it.get("message") or "").strip()
        if not body:
            continue
        new_it = dict(it)
        if not body.lower().startswith("code-style:"):
            body = f"code-style: {body}"
        new_it["body"] = body
        tagged.append(new_it)
    return {"raw_comments": tagged, "codestyle_done": True}


def security_node(state: ReviewState) -> Dict[str, Any]:
    items = run_security_agent(state["diff_text"])
    tagged: List[Dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        body = (it.get("body") or it.get("message") or "").strip()
        if not body:
            continue
        new_it = dict(it)
        if not body.lower().startswith("security:"):
            body = f"security: {body}"
        new_it["body"] = body
        tagged.append(new_it)
    return {"raw_comments": tagged, "security_done": True}


def post_node(state: ReviewState) -> Dict[str, Any]:
    # Публикуем один раз, когда обе ветки завершены
    if state.get("posted"):
        return {}
    if not (state.get("codestyle_done") and state.get("security_done")):
        return {}
    premerged = merge_by_line_match(state.get("raw_comments", []))
    resolved = resolve_positions(premerged, state["diff_index"])
    if resolved:
        post_inline_comments(state["pr_number"], resolved, state["head_sha"])
    return {"final_comments": resolved, "posted": True}


# Сборка Parallel Graph
graph = StateGraph(ReviewState)

graph.add_node("Start", start_node)
graph.add_node("CodeStyle", codestyle_node)
graph.add_node("Security", security_node)
graph.add_node("Post", post_node)

graph.set_entry_point("Start")
# Параллельные ветки от Start
graph.add_edge("Start", "CodeStyle")
graph.add_edge("Start", "Security")
# Обе ветки сходятся в Post; он сам проверяет готовность обеих
graph.add_edge("CodeStyle", "Post")
graph.add_edge("Security", "Post")
graph.add_edge("Post", END)

review_graph = graph.compile()
