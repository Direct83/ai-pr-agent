import json
import re
from typing import Dict, List, Any, Tuple, Optional
from .config import REVIEW_ONLY_PREFIXES


def extract_json(text: str):
    """
    Надёжно извлекаем JSON-массив из ответа LLM.
    1) Пробуем распарсить весь текст.
    2) Ищем блок формата fenced-кода (```json ... ```), но без жёсткой привязки.
    3) Иначе берём подстроку между первой '[' и последней ']'.
    Возвращаем [] при неудаче.
    """
    if not text:
        return []
    # Попытка №1: весь текст
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        pass
    # Попытка №2: fenced-подобный блок
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            return data if isinstance(data, list) else []
        except Exception:
            pass
    # Попытка №3: массив верхнего уровня
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        sub = text[start:end+1]
        try:
            data = json.loads(sub)
            return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


def path_included(path: str) -> bool:
    """true, если файл попадает под белый список префиксов (по умолчанию: только src/)."""
    path = (path or "").lstrip("./")
    return any(path.startswith(pref.rstrip("/") + "/") or path == pref.rstrip("/") for pref in REVIEW_ONLY_PREFIXES)


def build_filtered_files(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """вернёт только те элементы из /pulls/{n}/files, чей filename начинается с разрешённых префиксов."""
    out: List[Dict[str, Any]] = []
    for f in files or []:
        fn = f.get("filename") or ""
        if path_included(fn):
            out.append(f)
    return out


def build_diff_text_from_files(files: List[Dict[str, Any]]) -> str:
    """
    Склеиваем дифф только по выбранным файлам.
    Добавляем заголовок '+++ b/<path>' перед патчем, чтобы агенты знали путь.
    """
    parts: List[str] = []
    for f in files or []:
        path = f.get("filename")
        patch = f.get("patch")
        if not path or not patch:
            continue
        parts.append(f"+++ b/{path}\n{patch}\n")
    return "\n".join(parts)


def build_diff_index(files: List[Dict[str, Any]]) -> Dict[str, List[Tuple[int, str]]]:
    """
    Строим индекс строк НОВОЙ версии по каждому файлу на основе unified patch
    из /pulls/{number}/files.
    Возвращаем: { "path": [(new_line_number, line_text_without_prefix), ...] }.
    """
    index: Dict[str, List[Tuple[int, str]]] = {}
    for f in files:
        path = f.get("filename")
        patch = f.get("patch")
        if not path or not patch:
            continue
        lines = patch.splitlines()
        cur_new = None
        acc: List[Tuple[int, str]] = []
        for ln in lines:
            if ln.startswith("@@"):
                # пример заголовка: @@ -a,b +c,d @@
                m = re.search(r"\+(\d+)", ln)
                cur_new = int(m.group(1)) if m else None
            elif cur_new is not None:
                if ln.startswith("+"):
                    acc.append((cur_new, ln[1:]))
                    cur_new += 1
                elif ln.startswith(" "):
                    acc.append((cur_new, ln[1:]))
                    cur_new += 1
                elif ln.startswith("-"):
                    # удалённая строка — номер новой версии не увеличиваем
                    pass
        index[path] = acc
    return index


def resolve_positions(agent_items: List[Dict[str, Any]], diff_index: Dict[str, List[Tuple[int, str]]]) -> List[Dict[str, Any]]:
    """
    Преобразуем элементы агента к виду для GitHub inline-комментов.
    Вход: [{"path","line"|"line_match","body"}]
    Выход: [{"path","line","body"}]
    Приоритет: сначала пытаемся сопоставить по "line_match" (устойчиво к удалённым строкам выше),
    затем используем числовой "line" с валидацией и, при необходимости, ближайшим совпадением.
    """
    resolved: List[Dict[str, Any]] = []
    for it in agent_items or []:
        path = it.get("path")
        body = it.get("body") or it.get("message")
        if not path or not body:
            continue

        candidates = diff_index.get(path) or []
        line_match = (it.get("line_match") or "").strip()

        # 1) Предпочитаем сопоставление по содержимому новой версии
        if line_match:
            best: Optional[int] = None
            # точное вхождение
            for new_line, text in candidates:
                if line_match in text:
                    best = new_line
                    break
            # послабление: игнорируем пробелы
            if best is None and line_match:
                lm_norm = re.sub(r"\s+", "", line_match)
                for new_line, text in candidates:
                    if lm_norm in re.sub(r"\s+", "", text):
                        best = new_line
                        break
            if best is not None:
                resolved.append({"path": path, "line": best, "body": body})
                continue

        # 2) Если задан номер строки, используем его только при ТОЧНОМ совпадении
        if isinstance(it.get("line"), int):
            desired = int(it["line"])  # может ошибаться из‑за удалённых строк выше
            if candidates:
                candidate_lines = [ln for ln, _ in candidates]
                if desired in candidate_lines:
                    resolved.append({"path": path, "line": desired, "body": body})
                # если точного совпадения нет — вероятно, строка была удалена; пропускаем
            # если в новой версии нет кандидатов — весь блок мог быть удалён; пропускаем
            continue

        # 3) fallback — первая строка изменённого контента; если изменений нет — пропускаем
        if candidates:
            fallback = candidates[0][0]
            resolved.append({"path": path, "line": fallback, "body": body})
    return resolved
