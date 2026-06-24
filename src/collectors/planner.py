"""
planner.py
----------
Coletor do Microsoft Planner via Graph (auth delegada).

Estratégia para pegar "todas as demandas disponíveis":
  1. Planos diretos do usuario:        /me/planner/plans
  2. Planos dos Grupos/Times do user:  /me/memberOf -> /groups/{id}/planner/plans
  (dedup por id de plano)

Para cada plano coletamos:
  - buckets (colunas) -> mapa id->nome
  - tasks (todos os campos de task: status, datas, responsaveis, prioridade,
    bucket, quem criou, quem concluiu)
  - opcionalmente os "details" de cada task (descricao + checklist + referencias)

Comentarios dos cards NAO entram aqui — eles vivem nas conversations do Grupo
(Exchange) e serao coletados na Fase 1.5 (collectors/comments.py).

A coleta e' "crua": apenas baixa e organiza. A normalizacao/metricas ficam
em etapas seguintes.
"""

from ..graph_client import GraphClient


def collect_member_groups(g: GraphClient) -> list[dict]:
    """Grupos/Times em que o usuario participa."""
    return g.get_all(
        "/me/memberOf/microsoft.graph.group",
        params={"$select": "id,displayName"},
    )


def collect_plans(g: GraphClient) -> list[dict]:
    """Todos os planos acessiveis (diretos + via grupos), deduplicados."""
    plans: dict[str, dict] = {}

    # 1) Planos diretos
    for p in g.get_all("/me/planner/plans"):
        plans[p["id"]] = {
            "id": p["id"],
            "title": p.get("title"),
            "group_id": (p.get("container") or {}).get("containerId"),
            "group_name": None,
            "source": "me",
        }

    # 2) Planos via grupos do usuario
    for grp in collect_member_groups(g):
        gid = grp["id"]
        try:
            for p in g.get_all(f"/groups/{gid}/planner/plans"):
                plans[p["id"]] = {
                    "id": p["id"],
                    "title": p.get("title"),
                    "group_id": gid,
                    "group_name": grp.get("displayName"),
                    "source": "group",
                }
        except Exception as e:
            # Sem acesso ao planner daquele grupo — apenas registra e segue
            print(f"   [aviso] grupo '{grp.get('displayName')}' sem planos legiveis: {e}")

    return list(plans.values())


def collect_buckets(g: GraphClient, plan_id: str) -> dict[str, str]:
    """Mapa bucketId -> nome do bucket (coluna) do plano."""
    buckets = g.get_all(f"/planner/plans/{plan_id}/buckets")
    return {b["id"]: b.get("name") for b in buckets}


def collect_tasks(g: GraphClient, plan_id: str) -> list[dict]:
    """Todas as tasks de um plano (objeto cru do Planner)."""
    return g.get_all(f"/planner/plans/{plan_id}/tasks")


def collect_task_details(g: GraphClient, task_id: str) -> dict | None:
    """Detalhes da task: description, checklist, references. 1 chamada por task."""
    try:
        return g.get(f"/planner/tasks/{task_id}/details")
    except Exception as e:
        print(f"   [aviso] sem details para task {task_id}: {e}")
        return None


def _collect_user_ids_from_task(task: dict) -> set[str]:
    ids: set[str] = set()
    for uid in (task.get("assignments") or {}).keys():
        ids.add(uid)
    cb = (task.get("createdBy") or {}).get("user") or {}
    if cb.get("id"):
        ids.add(cb["id"])
    comp = (task.get("completedBy") or {}).get("user") or {}
    if comp.get("id"):
        ids.add(comp["id"])
    return ids


def resolve_users(g: GraphClient, user_ids: set[str]) -> dict[str, dict]:
    """Resolve userId -> {displayName, mail}. Ignora ids que falham."""
    users: dict[str, dict] = {}
    for uid in user_ids:
        try:
            u = g.get(f"/users/{uid}", params={"$select": "displayName,mail,userPrincipalName"})
            users[uid] = {
                "displayName": u.get("displayName"),
                "mail": u.get("mail") or u.get("userPrincipalName"),
            }
        except Exception:
            users[uid] = {"displayName": None, "mail": None}
    return users


def collect_full_backlog(g: GraphClient, with_details: bool = False) -> dict:
    """Coleta completa: planos -> buckets + tasks (+details) + usuarios."""
    plans_meta = collect_plans(g)
    print(f"[coleta] {len(plans_meta)} plano(s) acessiveis.")

    all_user_ids: set[str] = set()
    plans_out: list[dict] = []

    for pm in plans_meta:
        pid = pm["id"]
        buckets = collect_buckets(g, pid)
        tasks = collect_tasks(g, pid)
        print(f"   - {pm['title']}: {len(tasks)} task(s), {len(buckets)} bucket(s)")

        for t in tasks:
            all_user_ids |= _collect_user_ids_from_task(t)
            if with_details:
                t["_details"] = collect_task_details(g, t["id"])

        plans_out.append({**pm, "buckets": buckets, "tasks": tasks})

    print(f"[coleta] resolvendo {len(all_user_ids)} usuario(s)...")
    users = resolve_users(g, all_user_ids)

    return {"plans": plans_out, "users": users}
