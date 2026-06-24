"""
run_all.py
----------
Orquestrador do daily-backlog-agent. Executa TODO o pipeline em um comando:

    coleta (Planner) -> normaliza -> metricas -> newsletter (com IA)

Saidas (todas com data no nome):
    data/raw/snapshot_*.json
    data/normalized/backlog_*.json
    data/metrics/metrics_*.json
    reports/daily_*.md

Uso:
    py run_all.py              # pipeline completo COM IA (padrao)
    py run_all.py --no-ai      # sem a camada de IA (so deterministico)
    py run_all.py --details    # coleta tambem descricao/checklist dos cards

E' este script que o agendador (Task Scheduler) vai chamar toda manha.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Corrige acentuacao no console do Windows (cp1252 -> utf-8)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from src.graph_client import GraphClient
from src.collectors import planner
from src.collectors.comments import collect_comments
from src.collectors.teams import collect_teams
from src.normalize import normalize_snapshot
from src.metrics import compute_metrics
from src.newsletter import build_newsletter, compute_changes
from src.ai_insights import generate_insights, classify_teams_demands

load_dotenv()

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
NORM_DIR = ROOT / "data" / "normalized"
MET_DIR = ROOT / "data" / "metrics"
COM_DIR = ROOT / "data" / "comments"
REPORTS = ROOT / "reports"

MY_NAME = os.getenv("MY_DISPLAY_NAME", "João Guilherme")
TEAMS_DAYS = int(os.getenv("TEAMS_WINDOW_DAYS", "3"))


def _latest_existing(d: Path, pattern: str):
    files = sorted(d.glob(pattern))
    return files[-1] if files else None


def main():
    use_ai = "--no-ai" not in sys.argv
    with_details = "--details" in sys.argv
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for d in (RAW_DIR, NORM_DIR, MET_DIR, COM_DIR, REPORTS):
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n===== daily-backlog-agent | {date_str} | IA={'on' if use_ai else 'off'} =====\n")

    # ---- 1) Coleta -----------------------------------------------------------
    print("[1/5] Coletando backlog do Planner...")
    g = GraphClient()
    backlog = planner.collect_full_backlog(g, with_details=with_details)
    snapshot = {"collected_at": datetime.now(timezone.utc).isoformat(),
                "with_details": with_details, **backlog}
    (RAW_DIR / f"snapshot_{date_str}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 1b) Comentarios dos cards (abertos + concluidos recentes) ----------
    print("[2/6] Coletando comentarios dos cards...")
    comments = collect_comments(g, snapshot)
    (COM_DIR / f"comments_{date_str}.json").write_text(
        json.dumps(comments, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 1c) Mensagens do Teams (canais + chats, ultimos N dias) ------------
    teams_data = None
    if "--no-teams" not in sys.argv:
        print("[3/6] Coletando mensagens do Teams...")
        try:
            teams_data = collect_teams(g, days=TEAMS_DAYS)
            (RAW_DIR / f"teams_{date_str}.json").write_text(
                json.dumps(teams_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"   [aviso] coleta do Teams falhou (segue sem ela): {e}")
            teams_data = None

    # ---- 2) Diff (carrega normalizado anterior ANTES de sobrescrever) -------
    prev_file = _latest_existing(NORM_DIR, "backlog_*.json")
    prev_norm = json.loads(prev_file.read_text(encoding="utf-8")) if prev_file else None

    # ---- 3) Normalizacao -----------------------------------------------------
    print("[4/6] Normalizando...")
    normalized = normalize_snapshot(snapshot)
    norm_path = NORM_DIR / f"backlog_{date_str}.json"
    # Nota: numa reexecucao no mesmo dia, prev_file e' o proprio arquivo de hoje,
    # entao o diff "desde ontem" sai zerado (comportamento esperado).
    norm_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 4) Metricas ---------------------------------------------------------
    print("[5/6] Calculando metricas...")
    metrics = compute_metrics(normalized)
    (MET_DIR / f"metrics_{date_str}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 5) Newsletter (com IA opcional) ------------------------------------
    print("[6/6] Gerando newsletter" + (" (com IA)..." if use_ai else "..."))
    insights = generate_insights(metrics, normalized, comments) if use_ai else None
    teams_demands = classify_teams_demands(teams_data, normalized) if (use_ai and teams_data) else None
    changes = compute_changes(prev_norm, normalized)
    md = build_newsletter(metrics, normalized, changes, MY_NAME,
                          insights=insights, teams_demands=teams_demands)
    out = REPORTS / f"daily_{date_str}.md"
    out.write_text(md, encoding="utf-8")

    r = metrics["resumo"]
    print(f"\n[OK] Concluido. Abertas={r['abertas']} Vencidas={r['vencidas']} "
          f"SemDono={r['sem_dono']} | IA={'sim' if insights else 'nao'}")
    print(f"[OK] Newsletter: {out}\n")


if __name__ == "__main__":
    main()
