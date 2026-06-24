"""
normalize.py
------------
Transforma o snapshot CRU (data/raw/snapshot_*.json) em um modelo LIMPO e
unico: uma lista de "demandas" com campos prontos para analise.

Por que existe: o objeto cru do Planner usa codigos (percentComplete=50,
priority=9, assignments por GUID, datas ISO). Aqui traduzimos tudo para
algo legivel e calculamos derivados (aging, faixa de aging, vencida, dias
de atraso), para que metricas/IA/newsletter nao precisem reinterpretar.

Limitacao conhecida: o Planner nao expoe "ultima atividade" nos campos
basicos da task. Entao "parado ha X dias" e' aproximado pelo aging desde a
criacao ate haver coleta de comentarios (Fase 1.5), que dao atividade real.
"""

from datetime import datetime, timezone


# ---- Mapeamentos do Planner -------------------------------------------------

def map_status(percent: int) -> str:
    if percent == 100:
        return "concluida"
    if percent and percent > 0:
        return "em_andamento"
    return "nao_iniciada"


def map_priority(priority: int | None) -> str:
    # Escala do Planner: 0-1 Urgente, 2-4 Importante, 5-7 Media, 8-10 Baixa
    if priority is None:
        return "media"
    if priority <= 1:
        return "urgente"
    if priority <= 4:
        return "importante"
    if priority <= 7:
        return "media"
    return "baixa"


# ---- Helpers ----------------------------------------------------------------

def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _days_between(start, end) -> int | None:
    if not start or not end:
        return None
    return (end - start).days


def _user_name(users: dict, uid: str | None) -> str | None:
    if not uid:
        return None
    info = users.get(uid) or {}
    return info.get("displayName") or uid


def _assignee_names(users: dict, task: dict) -> list[str]:
    names = []
    for uid in (task.get("assignments") or {}).keys():
        names.append(_user_name(users, uid))
    return [n for n in names if n]


def _age_bucket(days: int | None) -> str:
    if days is None:
        return "desconhecido"
    if days <= 7:
        return "0-7"
    if days <= 15:
        return "8-15"
    if days <= 30:
        return "16-30"
    return "30+"


# ---- Normalizacao principal -------------------------------------------------

def normalize_snapshot(snapshot: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    users = snapshot.get("users", {})
    demands: list[dict] = []

    for plan in snapshot.get("plans", []):
        buckets = plan.get("buckets", {})
        for t in plan.get("tasks", []):
            pct = t.get("percentComplete", 0)
            status = map_status(pct)

            created = _parse_dt(t.get("createdDateTime"))
            due = _parse_dt(t.get("dueDateTime"))
            start = _parse_dt(t.get("startDateTime"))
            completed = _parse_dt(t.get("completedDateTime"))

            assignees = _assignee_names(users, t)
            is_done = status == "concluida"

            # aging: aberto -> desde criacao ate agora; concluido -> criacao ate conclusao
            ref_end = completed if is_done else now
            aging_days = _days_between(created, ref_end)

            is_overdue = bool(due and due < now and not is_done)
            days_overdue = _days_between(due, now) if is_overdue else None

            demands.append({
                "id": t.get("id"),
                "title": t.get("title"),
                "plan_id": plan.get("id"),
                "plan_title": plan.get("title"),
                "group_name": plan.get("group_name"),
                "bucket": buckets.get(t.get("bucketId")),
                "status": status,
                "percent_complete": pct,
                "priority": map_priority(t.get("priority")),
                "priority_raw": t.get("priority"),
                "assignees": assignees,
                "assignee_count": len(assignees),
                "has_owner": len(assignees) > 0,
                "created_at": t.get("createdDateTime"),
                "start_at": t.get("startDateTime"),
                "due_at": t.get("dueDateTime"),
                "completed_at": t.get("completedDateTime"),
                "created_by": _user_name(users, ((t.get("createdBy") or {}).get("user") or {}).get("id")),
                "completed_by": _user_name(users, ((t.get("completedBy") or {}).get("user") or {}).get("id")),
                "aging_days": aging_days,
                "age_bucket": _age_bucket(aging_days),
                "is_overdue": is_overdue,
                "days_overdue": days_overdue,
                "has_description": t.get("hasDescription", False),
                "checklist_count": (t.get("checklistItemCount") or 0),
                "reference_count": (t.get("referenceCount") or 0),
            })

    return {
        "normalized_at": now.isoformat(),
        "source_collected_at": snapshot.get("collected_at"),
        "total": len(demands),
        "demands": demands,
    }
