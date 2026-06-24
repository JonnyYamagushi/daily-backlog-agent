"""
metrics.py
----------
Calcula metricas DETERMINISTICAS (puro Python, sem IA) sobre o backlog
normalizado. Estas metricas sao a base factual da Newsletter e da Visao
Executiva — numeros confiaveis, auditaveis e reproduziveis.

A camada de IA (Fase 2) vai INTERPRETAR estes numeros (riscos, padroes,
duplicatas, recomendacoes), mas nunca inventar os numeros.
"""

from datetime import datetime, timezone
from collections import Counter, defaultdict


PRIORIDADE_PESO = {"urgente": 0, "importante": 1, "media": 2, "baixa": 3}


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _slim(d: dict) -> dict:
    """Versao enxuta de uma demanda, para listas dentro das metricas."""
    return {
        "id": d["id"],
        "title": d["title"],
        "assignees": d["assignees"],
        "priority": d["priority"],
        "status": d["status"],
        "aging_days": d["aging_days"],
        "days_overdue": d["days_overdue"],
        "due_at": d["due_at"],
        "plan_title": d["plan_title"],
        "bucket": d["bucket"],
    }


def _avg(values) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def compute_metrics(normalized: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    demands = normalized["demands"]

    abertas = [d for d in demands if d["status"] != "concluida"]
    concluidas = [d for d in demands if d["status"] == "concluida"]

    # --- Visao geral ---------------------------------------------------------
    resumo = {
        "total": len(demands),
        "abertas": len(abertas),
        "concluidas": len(concluidas),
        "por_status": dict(Counter(d["status"] for d in demands)),
        "abertas_por_prioridade": dict(Counter(d["priority"] for d in abertas)),
        "abertas_por_faixa_aging": dict(Counter(d["age_bucket"] for d in abertas)),
        "sem_dono": sum(1 for d in abertas if not d["has_owner"]),
        "vencidas": sum(1 for d in abertas if d["is_overdue"]),
    }

    # --- Backlog por responsavel --------------------------------------------
    por_resp = defaultdict(lambda: {"abertas": 0, "vencidas": 0, "agings": [], "urgentes": 0})
    for d in abertas:
        donos = d["assignees"] or ["(sem dono)"]
        for nome in donos:
            r = por_resp[nome]
            r["abertas"] += 1
            if d["is_overdue"]:
                r["vencidas"] += 1
            if d["priority"] == "urgente":
                r["urgentes"] += 1
            r["agings"].append(d["aging_days"])

    backlog_por_responsavel = []
    for nome, r in por_resp.items():
        backlog_por_responsavel.append({
            "responsavel": nome,
            "abertas": r["abertas"],
            "vencidas": r["vencidas"],
            "urgentes": r["urgentes"],
            "aging_medio": _avg(r["agings"]),
        })
    backlog_por_responsavel.sort(key=lambda x: x["abertas"], reverse=True)

    # --- Sobrecarga (acima da media de abertas) ------------------------------
    com_dono = [r for r in backlog_por_responsavel if r["responsavel"] != "(sem dono)"]
    media_carga = _avg([r["abertas"] for r in com_dono]) or 0
    sobrecarregados = [r for r in com_dono if r["abertas"] > media_carga]

    # --- Sem dono / criticas sem dono ---------------------------------------
    sem_dono_lista = [_slim(d) for d in abertas if not d["has_owner"]]
    criticas_sem_dono = [
        _slim(d) for d in abertas
        if not d["has_owner"] and d["priority"] in ("urgente", "importante")
    ]

    # --- Vencidas (ordenadas por atraso) ------------------------------------
    vencidas = sorted(
        [_slim(d) for d in abertas if d["is_overdue"]],
        key=lambda x: x["days_overdue"] or 0, reverse=True,
    )

    # --- Parados ha muito tempo (aging 30+) ---------------------------------
    parados_30plus = sorted(
        [_slim(d) for d in abertas if (d["aging_days"] or 0) > 30],
        key=lambda x: x["aging_days"] or 0, reverse=True,
    )

    # --- Resolucao / produtividade ------------------------------------------
    ranking_resolucao = Counter()
    tempos_resolucao = []
    concluidas_7d, concluidas_30d = [], []
    for d in concluidas:
        if d["completed_by"]:
            ranking_resolucao[d["completed_by"]] += 1
        comp = _parse_dt(d["completed_at"])
        cria = _parse_dt(d["created_at"])
        if comp and cria:
            tempos_resolucao.append((comp - cria).days)
        if comp:
            dias = (now - comp).days
            if dias <= 7:
                concluidas_7d.append(_slim(d) | {"completed_by": d["completed_by"], "completed_at": d["completed_at"]})
            if dias <= 30:
                concluidas_30d.append(d)

    resolucao = {
        "ranking_total": [{"responsavel": n, "resolvidas": q} for n, q in ranking_resolucao.most_common(15)],
        "concluidas_ultimos_7_dias": len(concluidas_7d),
        "concluidas_ultimos_30_dias": len(concluidas_30d),
        "tempo_medio_resolucao_dias": _avg(tempos_resolucao),
        "lista_concluidas_7d": sorted(concluidas_7d, key=lambda x: x["completed_at"] or "", reverse=True),
    }

    # --- Gargalos por area (bucket) e por plano ------------------------------
    por_bucket = Counter((d["bucket"] or "(sem bucket)") for d in abertas)
    por_plano = Counter(d["plan_title"] for d in abertas)

    return {
        "computed_at": now.isoformat(),
        "source_normalized_at": normalized.get("normalized_at"),
        "resumo": resumo,
        "backlog_por_responsavel": backlog_por_responsavel,
        "carga_media_por_responsavel": media_carga,
        "sobrecarregados": sobrecarregados,
        "sem_dono": sem_dono_lista,
        "criticas_sem_dono": criticas_sem_dono,
        "vencidas": vencidas,
        "parados_30plus": parados_30plus,
        "resolucao": resolucao,
        "gargalos_por_area": [{"area": a, "abertas": q} for a, q in por_bucket.most_common(15)],
        "abertas_por_plano": [{"plano": p, "abertas": q} for p, q in por_plano.most_common()],
    }
