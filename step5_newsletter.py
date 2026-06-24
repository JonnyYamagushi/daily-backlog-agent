"""
step5_newsletter.py
-------------------
Gera a Newsletter "Daily Backlog Intelligence" (Markdown) a partir das
metricas + backlog normalizado, com diff contra o dia anterior.

Saida: reports/daily_YYYY-MM-DD.md

Uso:
    py step5_newsletter.py
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from src.newsletter import build_newsletter, compute_changes
from src.ai_insights import generate_insights

load_dotenv()

ROOT = Path(__file__).resolve().parent
NORM_DIR = ROOT / "data" / "normalized"
MET_DIR = ROOT / "data" / "metrics"
COM_DIR = ROOT / "data" / "comments"
REPORTS = ROOT / "reports"

MY_NAME = os.getenv("MY_DISPLAY_NAME", "João Guilherme")


def _latest(glob_dir: Path, pattern: str, n=1):
    files = sorted(glob_dir.glob(pattern))
    return files[-n:] if files else []


def main():
    met_files = _latest(MET_DIR, "metrics_*.json")
    if not met_files:
        raise FileNotFoundError("Sem metricas. Rode step4 antes.")
    metrics = json.loads(met_files[-1].read_text(encoding="utf-8"))

    norm_files = _latest(NORM_DIR, "backlog_*.json", n=2)
    today_norm = json.loads(norm_files[-1].read_text(encoding="utf-8"))
    prev_norm = json.loads(norm_files[0].read_text(encoding="utf-8")) if len(norm_files) > 1 else None

    changes = compute_changes(prev_norm, today_norm)

    insights = None
    if "--ai" in sys.argv:
        com_files = _latest(COM_DIR, "comments_*.json")
        comments = json.loads(com_files[-1].read_text(encoding="utf-8")) if com_files else None
        print("[IA] gerando insights via claude headless... (pode levar ~1-3 min)")
        insights = generate_insights(metrics, today_norm, comments)

    md = build_newsletter(metrics, today_norm, changes, MY_NAME, insights=insights)

    REPORTS.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = REPORTS / f"daily_{date_str}.md"
    out.write_text(md, encoding="utf-8")

    print(f"[OK] Newsletter gerada: {out}")
    print(f"     ({len(md.splitlines())} linhas, responsavel-foco: {MY_NAME})")
    print(f"     Diff dia-a-dia: {'ativo' if changes.get('base') else 'primeira execucao'}")


if __name__ == "__main__":
    main()
