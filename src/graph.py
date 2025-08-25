from typing import TypedDict, List, Dict, Any
import re
from typing import Annotated
import operator

from langgraph.graph import StateGraph, END

from .agents.codestyle_agent import run_codestyle_agent
from .agents.security_agent import run_security_agent
from .utils import resolve_positions, merge_by_line_match, concat_by_path_line
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
    print(f"[codestyle] raw items: {len(items or [])}")
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
    print(f"[security] raw items: {len(items or [])}")
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
    raw = state.get("raw_comments", [])
    total = len(raw or [])
    sec_n = sum(1 for c in raw if ((c.get("body") or "").strip().lower().startswith("security:")))
    style_n = sum(1 for c in raw if ((c.get("body") or "").strip().lower().startswith("code-style:")))
    print(f"[post] collected raw: total={total}, code-style={style_n}, security={sec_n}")

    # Детализация первых 5 элементов до объединения
    for i, c in enumerate(raw[:5]):
        path = c.get("path")
        lm = (c.get("line_match") or "").strip()
        lm_norm = re.sub(r"\s+", "", lm).rstrip(";") if lm else ""
        body = (c.get("body") or c.get("message") or "").strip()
        print(f"[post] raw[{i}]: path={path}, lm={lm!r}, lm_norm={lm_norm!r}, body={body[:80]!r}")

    # Посмотрим, где есть кандидаты для мерджа по (path, lm_norm)
    group_counts: Dict[tuple, int] = {}
    for c in raw:
        path = c.get("path")
        lm = (c.get("line_match") or "").strip()
        if not (path and lm):
            continue
        lm_norm = re.sub(r"\s+", "", lm).rstrip(";")
        k = (path, lm_norm)
        group_counts[k] = group_counts.get(k, 0) + 1
    for (path, lm_norm), cnt in list(group_counts.items())[:10]:
        if cnt > 1:
            print(f"[post] candidate group to merge: path={path}, lm_norm={lm_norm!r}, count={cnt}")

    premerged = merge_by_line_match(raw)
    print(f"[post] premerge (by path+line_match): {len(premerged)} from {total}")

    resolved = resolve_positions(premerged, state["diff_index"])
    print(f"[post] resolved to inline positions: {len(resolved)}")

    # Группы по (path, line) до финального мерджа
    line_groups: Dict[tuple, int] = {}
    for c in resolved:
        k = (c.get("path"), c.get("line"))
        line_groups[k] = line_groups.get(k, 0) + 1
    for (path, line), cnt in list(line_groups.items())[:10]:
        if cnt > 1:
            print(f"[post] candidate merge by path+line: path={path}, line={line}, count={cnt}")

    # Дополнительное объединение после привязки: по (path, line)
    post_merged = concat_by_path_line(resolved)
    print(f"[post] merged by path+line: {len(post_merged)} from {len(resolved)}")
    if post_merged:
        post_inline_comments(state["pr_number"], post_merged, state["head_sha"])
    return {"final_comments": post_merged, "posted": True}


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
