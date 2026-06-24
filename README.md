# 📊 daily-backlog-agent

> **Analista Sênior de Operações & Backlog apoiado por IA.**
> Lê o backlog no **Microsoft Planner/Tasks** (via Microsoft Graph), analisa os
> dados — incluindo os **comentários dos cards** — e gera, automaticamente todas
> as manhãs, uma **Newsletter Executiva Diária** ("Daily Backlog Intelligence")
> com diagnósticos, riscos, gargalos, duplicatas, bloqueios e recomendações
> acionáveis no nível de apresentação para coordenadores.

O objetivo é que você abra **um único arquivo** e, em **5 minutos**, entenda todo
o cenário do dia: o que exige atenção, o que está atrasado, o que virou risco, o
que está bloqueado, quem resolveu o quê, onde estão os gargalos e o que precisa de
decisão da coordenação.

---

## ✨ O que o agente entrega

A newsletter (Markdown) inclui as seções:

- **Resumo Executivo** — narrativa de analista sênior (gerada por IA).
- **O que mudou desde ontem** — novas, concluídas, reabertas, mudanças de prioridade.
- **Minha agenda operacional do dia** — suas top prioridades.
- **Alertas críticos** — itens que exigem ação imediata.
- **Demandas bloqueadas** — com o motivo extraído dos **comentários dos cards**.
- **Demandas sem responsável** — com sugestão de direcionamento.
- **Demandas vencidas** — ordenadas por criticidade.
- **Possíveis demandas duplicadas** — por similaridade semântica (IA).
- **Quem resolveu o quê** — ranking de resoluções.
- **Destaques dos comentários** — decisões, handoffs e dependências relevantes.
- **Demandas no Teams sem card** — pedidos/bugs mencionados em chats/canais que
  ainda não viraram card no Planner (classificados por IA, deduplicados).
- **Gargalos identificados** — áreas/sistemas com mais represamento.
- **Visão para coordenação** — resumo executivo para liderança.
- **O que precisa de decisão hoje** + **Recomendações priorizadas**.

---

## 🏗️ Arquitetura

O agente é um pipeline determinístico + uma camada de IA por cima. Os **números**
vêm de cálculo puro (confiáveis e auditáveis); a **IA apenas interpreta** esses
números e os comentários — nunca os inventa.

```
[Microsoft Graph]
       │  (MSAL, auth delegada via Device Code)
       ▼
1. COLETA          src/collectors/planner.py   → planos, tasks, buckets, usuários
   COLETA COMENT.  src/collectors/comments.py  → comentários (threads do grupo)
       ▼   data/raw/snapshot_*.json  +  data/comments/comments_*.json
2. NORMALIZAÇÃO    src/normalize.py            → modelo único (aging, status, vencidas)
       ▼   data/normalized/backlog_*.json
3. MÉTRICAS        src/metrics.py              → carga, vencidas, ranking, gargalos
       ▼   data/metrics/metrics_*.json
4. IA (insights)   src/ai_insights.py          → resumo, duplicatas, riscos, bloqueios
       │           (via `claude -p` headless + context.md)
       ▼
5. NEWSLETTER      src/newsletter.py           → reports/daily_*.md
```

Tudo é orquestrado por **`run_all.py`** (um comando roda as 5 etapas).

---

## 📁 Estrutura do projeto

```
daily-backlog-agent/
├── run_all.py              # Orquestrador: roda todo o pipeline (use este)
├── run_daily.bat           # Wrapper chamado pelo Agendador do Windows
│
├── step1_test_auth.py      # Teste isolado: valida autenticação no Graph
├── step2_collect_planner.py# Teste isolado: coleta o backlog
├── step3_normalize.py      # Teste isolado: normaliza
├── step4_metrics.py        # Teste isolado: calcula métricas
├── step5_newsletter.py     # Teste isolado: gera a newsletter (--ai opcional)
├── step6_comments.py       # Teste isolado: coleta comentários
├── step7_collect_teams.py  # Teste isolado: coleta mensagens do Teams
│
├── src/
│   ├── auth.py             # Login MSAL (Device Code) + cache de token
│   ├── graph_client.py     # Wrapper do Graph (paginação, throttling)
│   ├── collectors/
│   │   ├── planner.py      # Coleta planos/tasks/buckets/usuários
│   │   ├── comments.py     # Coleta e limpa comentários dos cards
│   │   └── teams.py        # Coleta mensagens de canais/chats do Teams
│   ├── normalize.py        # Modelo limpo (aging, faixas, vencidas, prioridade)
│   ├── metrics.py          # Métricas determinísticas (sem IA)
│   ├── ai_insights.py      # Camada de IA (claude headless)
│   └── newsletter.py       # Montagem do Markdown + diff dia-a-dia
│
├── .env.example            # Modelo de configuração (copie para .env)
├── context.example.md      # Modelo do contexto operacional (copie p/ context.md)
├── requirements.txt
└── data/ , reports/ , logs/   # Criados em tempo de execução (ignorados no git)
```

---

## ✅ Pré-requisitos

- **Python 3.10+** (no Windows, o launcher `py`).
- **Claude Code** instalado e logado (a IA usa `claude -p` headless).
- Uma conta Microsoft 365 com acesso ao Planner.
- Permissão para **registrar um app no Entra ID** (ou um admin que faça o consentimento).

---

## 🔐 1) Registrar o app no Microsoft Entra ID

1. Acesse <https://entra.microsoft.com> → **Aplicativos → Registros de aplicativo → Novo registro**.
2. Nome: `daily-backlog-agent`; conta: *somente este diretório (locatário único)*; URI de redirecionamento: em branco. **Registrar**.
3. Anote o **ID do aplicativo (cliente)** e o **ID do diretório (locatário)**.
4. Em **Autenticação → Configurações avançadas**, ative **"Permitir fluxos de cliente público" = Sim**. Salvar.
5. Em **Permissões de API → Adicionar → Microsoft Graph → Permissões delegadas**, adicione:

   | Permissão | Para quê |
   |---|---|
   | `Tasks.Read` | Ler tarefas do Planner |
   | `Group.Read.All` | Enumerar planos dos grupos **e ler comentários dos cards** |
   | `User.Read` | Identificar você |
   | `User.ReadBasic.All` | Resolver o **nome** dos demais responsáveis |
   | `offline_access` | Refresh token (execução agendada silenciosa) |

   **Para a Fase 2 (Teams)**, adicione também:

   | Permissão | Para quê |
   |---|---|
   | `Team.ReadBasic.All` | Listar as equipes que você participa |
   | `Channel.ReadBasic.All` | Listar os canais |
   | `ChannelMessage.Read.All` | Ler mensagens dos canais (**exige admin consent**) |
   | `Chat.Read` | Listar e ler seus chats |

6. Clique em **"Conceder consentimento de administrador"** (ou peça a um admin).

> ℹ️ **Por que auth delegada (Device Code)?** A API do Planner praticamente não
> suporta permissões de aplicação. Usamos login delegado: você loga **uma vez** no
> navegador e o MSAL guarda um *refresh token* que renova sozinho nas próximas
> execuções, inclusive as agendadas.

---

## ⚙️ 2) Instalação e configuração

```bash
git clone <seu-repositorio> daily-backlog-agent
cd daily-backlog-agent

py -m venv .venv
# Windows (Git Bash): source .venv/Scripts/activate
# Windows (CMD):       .venv\Scripts\activate
py -m pip install -r requirements.txt
```

### `.env`
```bash
cp .env.example .env     # (CMD: copy .env.example .env)
```
Edite o `.env`:
```
TENANT_ID=<seu-tenant-id>
CLIENT_ID=<seu-client-id>
GRAPH_SCOPES=Tasks.Read Group.Read.All User.Read User.ReadBasic.All Team.ReadBasic.All Channel.ReadBasic.All ChannelMessage.Read.All Chat.Read
MY_DISPLAY_NAME=Seu Nome Exato (como aparece no Planner)
# TEAMS_WINDOW_DAYS=3   # (opcional) janela de dias varrida no Teams
```

### `context.md` (opcional, mas recomendado)
Dá à IA o conhecimento de negócio do seu time (papéis, quem só acompanha vs. quem
executa, etc.) — melhora muito a qualidade da análise.
```bash
cp context.example.md context.md   # edite com a realidade do seu time
```
> 🔒 `context.md` é **privado** (está no `.gitignore`) porque contém nomes/papéis internos.

---

## ▶️ 3) Uso

**Primeira execução** (vai pedir login no navegador via Device Code):
```bash
py step1_test_auth.py     # valida só a autenticação
```

**Rodar o pipeline completo** (coleta → comentários → normaliza → métricas → newsletter com IA):
```bash
py run_all.py
```
Variações:
```bash
py run_all.py --no-ai     # só camada determinística (rápido, sem IA)
py run_all.py --details   # coleta também descrição/checklist dos cards (mais lento)
py run_all.py --no-teams  # pula a coleta/análise do Teams
```

O relatório final fica em **`reports/daily_AAAA-MM-DD.md`** (abra no VS Code para
ver formatado).

### Rodar etapas isoladas (debug)
```bash
py step2_collect_planner.py   # coleta
py step6_comments.py          # comentários
py step3_normalize.py         # normalização
py step4_metrics.py           # métricas
py step5_newsletter.py --ai   # newsletter (com IA)
```

---

## 🗂️ 4) Saídas geradas

| Pasta | Conteúdo |
|---|---|
| `data/raw/` | Snapshot cru do Planner (JSON) |
| `data/comments/` | Comentários coletados por card (JSON) |
| `data/normalized/` | Backlog normalizado (JSON) |
| `data/metrics/` | Métricas determinísticas (JSON) |
| `data/cache/` | Cache de token MSAL (**não versionar**) |
| `reports/` | **A newsletter diária (Markdown)** |
| `logs/` | Log das execuções agendadas |

Todas essas pastas são ignoradas pelo Git (contêm dados internos).

---

## ⏰ 5) Agendamento diário (Windows)

Para gerar a newsletter automaticamente toda manhã, registre uma tarefa no
Agendador. Use **PowerShell** (suporta "rodar ao ligar o PC se o horário foi perdido"):

```powershell
$action   = New-ScheduledTaskAction -Execute "C:\PROJETOS\daily-backlog-agent\run_daily.bat"
$trigger  = New-ScheduledTaskTrigger -Daily -At 7:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "DailyBacklogAgent" -Action $action -Trigger $trigger -Settings $settings -Force
```

- Roda às **07:00**, ou **assim que o PC ligar** se estava desligado no horário.
- Roda **no seu usuário logado** (necessário para o `claude` headless e o cache de token).
- Testar agora: `schtasks /Run /TN "DailyBacklogAgent"` → confira `logs\run.log`.
- Remover: `schtasks /Delete /TN "DailyBacklogAgent" /F`.

---

## 🤖 Como funciona a camada de IA

A IA usa o **Claude Code em modo headless** (`claude -p --output-format json`),
reaproveitando sua assinatura — **sem API key separada**. O `src/ai_insights.py`
monta um contexto compacto (métricas + demandas abertas + comentários + `context.md`),
pede um JSON estruturado de insights e injeta o resultado na newsletter.

Se a IA falhar (CLI ausente, timeout, etc.), a newsletter **cai automaticamente**
na versão determinística — nada quebra.

---

## 🔒 Boas práticas de segurança

- **Nunca** comite `.env`, `context.md`, `data/` ou o token (`*.bin`) — já estão no `.gitignore`.
- Use **permissões mínimas** no Graph (apenas as listadas acima).
- O token fica em `data/cache/` (cliente público, sem client secret).
- Os comentários dos cards podem conter dados sensíveis — por isso `data/` é ignorado.

---

## 🗺️ Roadmap

- [x] **Fase 1** — Coleta Planner + normalização + métricas + newsletter (MD/JSON)
- [x] **Fase 1.5** — Leitura dos comentários dos cards (bloqueios, dependências, evidência)
- [x] **Fase 2.1** — Camada de IA (resumo, duplicatas semânticas, riscos, recomendações)
- [x] **Fase 2.2/2.3** — Orquestrador único + agendamento diário
- [x] **Fase 2 (Teams)** — captura demandas em chats/canais que não viraram card
- [ ] **Memória operacional** — snapshots históricos: tendências de 90 dias, recorrências
- [ ] **Fase 3 (Distribuição)** — enviar a newsletter por e-mail / Teams / SharePoint

---

## 📄 Licença

Veja [LICENSE](LICENSE).
