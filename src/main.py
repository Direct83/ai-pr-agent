import sys
from .github_client import get_pr_info, get_pr_files
from .utils import build_diff_index, build_filtered_files, build_diff_text_from_files
from .graph import review_graph


def main(pr_number: int):
    # 1) Метаданные PR (нужен head sha для inline-комментариев)
    pr = get_pr_info(pr_number)
    head_sha = pr["head"]["sha"]

    # 2) Файлы PR и фильтрация по префиксам (по умолчанию: src/)
    files = get_pr_files(pr_number)
    included_files = build_filtered_files(files)
    diff_index = build_diff_index(included_files)
    diff_text = build_diff_text_from_files(included_files)

    # 3) Начальное состояние графа
    initial_state = {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "diff_text": diff_text,      # даём агентам дифф только по src/**
        "diff_index": diff_index,    # и индексы только по src/**
        "raw_comments": []
    }

    # 4) Запуск графа
    review_graph.invoke(initial_state)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m src.main <PR_NUMBER>")
    main(int(sys.argv[1]))
