"""
ai_insights.py
--------------
Camada de IA do agente. Em vez de usar a API da Anthropic com key, chamamos
o Claude Code em modo HEADLESS (`claude -p`), reaproveitando a assinatura ja
existente.

Fluxo:
  1. Monta um CONTEXTO COMPACTO (metricas agregadas + demandas abertas).
  2. Envia um prompt pedindo um JSON estruturado de insights.
  3. Faz o parse e devolve um dict.

Filosofia: a IA INTERPRETA os numeros (narrativa, duplicatas semanticas,
riscos, recomendacoes) mas NAO inventa numeros — estes vem das metricas
determinísticas. Se a IA falhar, retorna None e a newsletter usa o fallback.
"""

import os
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


SYSTEM = """Você é um Analista Sênior de Operações e Gestão de Backlog.
Recebe métricas já calculadas e a lista de demandas ABERTAS de um time de TI.
Algumas demandas trazem COMENTÁRIOS dos cards (campo "comentarios") — eles são
sua fonte mais rica de contexto: use-os para entender bloqueios, dependências,
quem está atuando, decisões e evidência (ou falta) de conclusão.

REGRAS:
- Baseie-se SOMENTE nos dados fornecidos. NÃO invente números, nomes ou fatos.
- Escreva em português profissional, claro e direto.
- Para duplicatas, agrupe por SIMILARIDADE SEMÂNTICA de título (mesmo assunto),
  não apenas título idêntico.
- Para riscos, gere hipóteses acionáveis no formato "se nada for feito...".
- Para BLOQUEADAS, marque apenas demandas com EVIDÊNCIA nos comentários
  (ex.: "aguardando cliente", "depende de outra área", "parado esperando X").
  Cite o motivo baseado no comentário. Não invente bloqueio sem evidência.
- Para DESTAQUES DOS COMENTÁRIOS, resuma os comentários mais relevantes
  (decisões, handoffs, dependências, pedidos de ajuda), citando a demanda.
- Responda APENAS com um JSON válido, sem markdown, sem comentários, sem texto fora do JSON.

Formato EXATO do JSON de saída:
{
  "resumo_executivo": "2-4 parágrafos em markdown, narrativa de analista sênior",
  "visao_coordenacao": "texto objetivo para liderança, em markdown com bullets",
  "duplicatas": [
    {"tema": "assunto comum", "titulos": ["t1", "t2"], "confianca": "alta|media|baixa"}
  ],
  "riscos_preditivos": [
    {"titulo": "demanda ou tema", "hipotese": "se nada for feito...", "severidade": "alta|media|baixa"}
  ],
  "bloqueadas": [
    {"titulo": "demanda", "motivo": "motivo do bloqueio segundo o comentário", "depende_de": "pessoa/área/cliente"}
  ],
  "destaques_comentarios": [
    {"titulo": "demanda", "destaque": "resumo do comentário relevante"}
  ],
  "recomendacoes": [
    {"acao": "ação concreta", "alvo": "responsável/área", "prioridade": 1}
  ],
  "o_que_decidir_hoje": ["decisão 1 que a coordenação precisa tomar hoje"]
}"""


def _fmt_comentarios(posts: list, max_posts: int = 6, max_chars: int = 500) -> list:
    """Formata os comentarios de um card para o contexto (limitado em tamanho)."""
    out = []
    for p in (posts or [])[-max_posts:]:
        texto = (p.get("text") or "")[:max_chars]
        out.append(f"[{p.get('from')} em {(p.get('created') or '')[:10]}] {texto}")
    return out


def _build_context(metrics: dict, normalized: dict, comments: dict | None = None) -> dict:
    comments = comments or {}
    abertas = []
    for d in normalized["demands"]:
        if d["status"] == "concluida":
            continue
        item = {
            "titulo": d["title"],
            "responsaveis": d["assignees"],
            "prioridade": d["priority"],
            "aging_dias": d["aging_days"],
            "vencida": d["is_overdue"],
            "dias_atraso": d["days_overdue"],
            "area": d["bucket"],
            "plano": d["plan_title"],
        }
        coments = comments.get(d["id"])
        if coments:
            item["comentarios"] = _fmt_comentarios(coments)
        abertas.append(item)
    return {
        "resumo": metrics["resumo"],
        "carga_media_por_responsavel": metrics["carga_media_por_responsavel"],
        "backlog_por_responsavel": metrics["backlog_por_responsavel"][:10],
        "sobrecarregados": metrics["sobrecarregados"],
        "criticas_sem_dono": metrics["criticas_sem_dono"],
        "gargalos_por_area": metrics["gargalos_por_area"],
        "resolucao_resumo": {
            "concluidas_7d": metrics["resolucao"]["concluidas_ultimos_7_dias"],
            "concluidas_30d": metrics["resolucao"]["concluidas_ultimos_30_dias"],
            "tempo_medio_dias": metrics["resolucao"]["tempo_medio_resolucao_dias"],
        },
        "demandas_abertas": abertas,
    }


def _load_extra_context() -> str:
    """Le o contexto operacional do gestor (context.md), se existir.

    Caminho: variavel de ambiente EXTRA_CONTEXT_FILE (relativa a raiz ou
    absoluta) ou, por padrao, context.md na raiz do projeto.
    """
    nome = os.getenv("EXTRA_CONTEXT_FILE", "context.md")
    caminho = Path(nome)
    if not caminho.is_absolute():
        caminho = ROOT / caminho
    if caminho.exists():
        try:
            return caminho.read_text(encoding="utf-8").strip()
        except Exception as e:
            print(f"[IA] nao consegui ler {caminho}: {e}")
    return ""


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove primeira linha (```json) e ultima (```)
        linhas = t.splitlines()
        linhas = linhas[1:] if linhas and linhas[0].startswith("```") else linhas
        if linhas and linhas[-1].strip().startswith("```"):
            linhas = linhas[:-1]
        t = "\n".join(linhas)
    return t.strip()


def _call_claude(prompt: str, timeout: int = 240) -> dict | None:
    """Chama o Claude Code headless e devolve o JSON parseado (ou None)."""
    claude = shutil.which("claude")
    if not claude:
        print("[IA] CLI 'claude' nao encontrada no PATH — pulando camada de IA.")
        return None
    try:
        proc = subprocess.run(
            [claude, "-p", "--output-format", "json"],
            input=prompt, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"[IA] claude -p excedeu {timeout}s.")
        return None
    if proc.returncode != 0:
        print(f"[IA] claude -p retornou erro {proc.returncode}: {proc.stderr[:300]}")
        return None
    # Envelope do Claude Code: {"type":"result","result":"<texto>", ...}
    try:
        texto = json.loads(proc.stdout).get("result", proc.stdout)
    except json.JSONDecodeError:
        texto = proc.stdout
    try:
        return json.loads(_strip_fences(texto))
    except json.JSONDecodeError as e:
        print(f"[IA] resposta nao era JSON valido ({e}).")
        return None


def generate_insights(metrics: dict, normalized: dict, comments: dict | None = None,
                      timeout: int = 240) -> dict | None:
    contexto = _build_context(metrics, normalized, comments)
    extra = _load_extra_context()
    bloco_extra = (
        "\n\n=== CONTEXTO OPERACIONAL (fornecido pelo gestor; use para interpretar "
        "papéis, autoria real, carga e produtividade) ===\n" + extra
        if extra else ""
    )
    if extra:
        print("[IA] contexto operacional (context.md) carregado.")
    prompt = (
        SYSTEM
        + bloco_extra
        + "\n\n=== DADOS (JSON) ===\n"
        + json.dumps(contexto, ensure_ascii=False)
        + "\n\nResponda APENAS com o JSON de insights."
    )
    result = _call_claude(prompt, timeout)
    if result is not None:
        print("[IA] insights gerados com sucesso.")
    return result


SYSTEM_TEAMS = """Você é um analista de operações de TI. Recebe MENSAGENS recentes
do Microsoft Teams (chats e canais) e a lista de TÍTULOS de demandas já abertas no
Planner. Sua tarefa: identificar mensagens que representam DEMANDAS de trabalho para
o time de TI (bugs, solicitações, pedidos, problemas a resolver, ajustes) que possam
AINDA NÃO ter virado card no Planner.

REGRAS:
- Agrupe mensagens relacionadas ao MESMO assunto em uma única demanda candidata.
- IGNORE conversa social, agradecimentos, avisos, combinados de horário, "ok", "bom dia".
- Para cada candidata, compare com os títulos do Planner e diga se já parece rastreada.
- Não invente: use apenas o que está nas mensagens. Cite um trecho como evidência.
- Responda APENAS com JSON válido, sem markdown nem texto fora do JSON.

Formato EXATO:
{
  "demandas_teams": [
    {
      "assunto": "resumo curto da demanda",
      "solicitante": "quem pediu (autor)",
      "origem": "container (chat/canal)",
      "evidencia": "trecho representativo da mensagem",
      "ja_rastreada": "nao" ou "título do card semelhante no Planner",
      "confianca": "alta|media|baixa",
      "acao_sugerida": "criar card | vincular a card existente | acompanhar"
    }
  ]
}"""


def _build_teams_context(teams_data: dict, normalized: dict) -> dict:
    msgs = [
        {"de": m.get("from"), "em": (m.get("created") or "")[:16],
         "onde": m.get("container"), "texto": m.get("text")}
        for m in teams_data.get("messages", [])
    ]
    titulos_abertos = [d["title"] for d in normalized["demands"] if d["status"] != "concluida"]
    return {"mensagens_teams": msgs, "titulos_no_planner": titulos_abertos}


def classify_teams_demands(teams_data: dict, normalized: dict,
                           timeout: int = 240) -> dict | None:
    """Classifica mensagens do Teams em demandas candidatas (dedup vs Planner)."""
    if not teams_data or not teams_data.get("messages"):
        return None
    contexto = _build_teams_context(teams_data, normalized)
    prompt = (
        SYSTEM_TEAMS
        + "\n\n=== DADOS (JSON) ===\n"
        + json.dumps(contexto, ensure_ascii=False)
        + "\n\nResponda APENAS com o JSON."
    )
    result = _call_claude(prompt, timeout)
    if result is not None:
        n = len(result.get("demandas_teams", []))
        print(f"[IA] {n} demanda(s) candidata(s) identificada(s) no Teams.")
    return result
