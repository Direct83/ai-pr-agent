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
    for f in files:
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
    for f in files:
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

    Вход:
    - [{"path", "line_match", "body"}]

    Поведение:
    - Привязка выполняется ТОЛЬКО по содержимому новой версии (line_match).
    - Если задан path, ищем совпадение внутри этого файла; иначе пробуем найти
      уникальное совпадение по всем файлам диффа и используем его.
    - Числовые координаты "line" игнорируем полностью.

    Выход:
    - [{"path", "line", "body"}] — номера строк даны по НОВОЙ версии.
    """
    resolved: List[Dict[str, Any]] = []
    for it in agent_items:
        path = (it.get("path") or "").strip()
        body = it.get("body") or it.get("message")
        if not body:
            continue

        line_match = (it.get("line_match") or "").strip()

        # 1) Сопоставляем только по содержимому новой версии
        if line_match:
            # Вариант А: известен путь
            def find_in_candidates(cands: List[Tuple[int, str]]) -> Optional[int]:
                best_local: Optional[int] = None
                for new_line, text in cands:
                    if line_match in text:
                        best_local = new_line
                        break
                if best_local is None:
                    lm_norm = re.sub(r"\s+", "", line_match)
                    for new_line, text in cands:
                        if lm_norm in re.sub(r"\s+", "", text):
                            best_local = new_line
                            break
                return best_local

            if path and path in diff_index:
                best = find_in_candidates(diff_index.get(path) or [])
                if best is not None:
                    resolved.append({"path": path, "line": best, "body": body})
                    continue

            # Вариант Б: путь не задан — ищем по всем файлам и выбираем уникальное совпадение
            matches: List[Tuple[str, int]] = []
            for p, cands in (diff_index or {}).items():
                best = find_in_candidates(cands or [])
                if best is not None:
                    matches.append((p, best))
            if len(matches) == 1:
                p, ln = matches[0]
                resolved.append({"path": p, "line": ln, "body": body})
                continue

        # 2) Если нет line_match и сопоставления не получилось — пропускаем элемент
        # Чисто числовые координаты небезопасны (съезжают из‑за удалений выше).
        continue
    return resolved


def _merge_generic(items: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
    """
    Общий алгоритм объединения по ключу. Тексты объединяются с разделителем
    из пустой строки ("\n\n"). Порядок — по первым появлениям ключей.
    Элементы без ключа остаются как есть.
    """
    if not items:
        return []
    grouped: Dict[Tuple[Any, ...], List[str]] = {}
    proto: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    order: List[Tuple[str, Any]] = []  # (tag, key_or_item)
    for it in items:
        body = (it.get("body") or it.get("message") or "").strip()
        key = key_fn(it)
        if key is None or not body:
            order.append(("raw", it))
            continue
        if key not in grouped:
            grouped[key] = []
            proto[key] = dict(it)
            order.append(("key", key))
        grouped[key].append(body)

    result: List[Dict[str, Any]] = []
    seen: set = set()
    for tag, obj in order:
        if tag == "raw":
            result.append(obj)  # как есть
        else:
            key = obj
            if key in seen:
                continue
            seen.add(key)
            new_it = dict(proto[key])
            new_it["body"] = "\n\n".join(grouped.get(key) or [])
            result.append(new_it)
    return result


def merge_by_line_match(agent_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Объединение элементов с одинаковыми (path, line_match) до привязки к строкам.
    line_match нормализуется: удаляются все пробелы и финальный ';'.
    Тексты объединяются через пустую строку.
    """
    def _key(it: Dict[str, Any]):
        path = it.get("path") or ""
        lm = (it.get("line_match") or "").strip()
        if not (path and lm):
            return None
        # Нормализуем для устойчивого объединения: убираем пробелы и крайний ';'
        lm_norm = re.sub(r"\s+", "", lm).rstrip(";")
        return (path, lm_norm)
    return _merge_generic(agent_items, _key)


def concat_by_path_line(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Финальное объединение после привязки: группировка по (path, line) с
    объединением текстов через пустую строку.
    """
    def _key(it: Dict[str, Any]):
        path = it.get("path")
        line = it.get("line")
        return (path, line) if (path and isinstance(line, int)) else None
    return _merge_generic(items, _key)
