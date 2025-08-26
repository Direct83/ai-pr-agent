from typing import TypedDict, List, Dict, Any
from typing import Annotated
import operator

from langgraph.graph import StateGraph, END

from .agents.codestyle_agent import run_codestyle_agent
from .utils import resolve_positions
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
        new_it["body"] = body
        tagged.append(new_it)
    return {"raw_comments": tagged, "codestyle_done": True}


def post_node(state: ReviewState) -> Dict[str, Any]:
    # Публикуем один раз, когда ветка codestyle завершена
    if state.get("posted"):
        return {}
    if not state.get("codestyle_done"):
        return {}
    raw = state.get("raw_comments", [])
    total = len(raw or [])
    resolved = resolve_positions(raw, state["diff_index"])
    final_items = resolved
    if final_items:
        post_inline_comments(state["pr_number"], final_items, state["head_sha"])
    return {"final_comments": final_items, "posted": True}


# Сборка Parallel Graph
graph = StateGraph(ReviewState)

graph.add_node("Start", start_node)
graph.add_node("CodeStyle", codestyle_node)
graph.add_node("Post", post_node)

graph.set_entry_point("Start")
# Линейный граф: Start -> CodeStyle -> Post
graph.add_edge("Start", "CodeStyle")
graph.add_edge("CodeStyle", "Post")
graph.add_edge("Post", END)

review_graph = graph.compile()
