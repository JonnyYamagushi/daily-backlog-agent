"""
step2_collect_planner.py
------------------------
Coleta COMPLETA do backlog no Planner e salva um snapshot JSON cru.

Uso (Git Bash ou CMD), dentro de C:\\PROJETOS\\daily-backlog-agent:
    py step2_collect_planner.py            # rapido (sem details das tasks)
    py step2_collect_planner.py --details  # inclui descricao/checklist (mais lento)

Saida:
    data/raw/snapshot_YYYY-MM-DD.json
E imprime um resumo de sanidade (totais por status, vencidas, sem dono).
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.graph_client import GraphClient
from src.collectors import planner


RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _quick_summary(backlog: dict) -> None:
    now = datetime.now(timezone.utc)
    total = 0
    nao_iniciada = em_andamento = concluida = 0
    sem_dono = vencidas = 0

    for plan in backlog["plans"]:
        for t in plan["tasks"]:
            total += 1
            pct = t.get("percentComplete", 0)
            if pct == 100:
                concluida += 1
            elif pct >= 50:
                em_andamento += 1
            else:
                nao_iniciada += 1

            if not (t.get("assignments") or {}):
                sem_dono += 1

            due = _parse_dt(t.get("dueDateTime"))
            if due and due < now and pct < 100:
                vencidas += 1

    print("\n================ RESUMO DA COLETA ================")
    print(f" Planos.................: {len(backlog['plans'])}")
    print(f" Tasks (total).........: {total}")
    print(f"   - nao iniciadas.....: {nao_iniciada}")
    print(f"   - em andamento......: {em_andamento}")
    print(f"   - concluidas........: {concluida}")
    print(f" Sem responsavel.......: {sem_dono}")
    print(f" Vencidas (em aberto)..: {vencidas}")
    print(f" Usuarios resolvidos...: {len(backlog['users'])}")
    print("=================================================\n")


def main():
    with_details = "--details" in sys.argv

    g = GraphClient()
    backlog = planner.collect_full_backlog(g, with_details=with_details)

    snapshot = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "with_details": with_details,
        **backlog,
    }

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = RAW_DIR / f"snapshot_{date_str}.json"
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    _quick_summary(snapshot)
    print(f"[OK] Snapshot salvo em: {out_path}")


if __name__ == "__main__":
    main()
