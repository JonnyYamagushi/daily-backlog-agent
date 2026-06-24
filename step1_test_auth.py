"""
step1_test_auth.py
------------------
PRIMEIRO TESTE — valida apenas:
  1. Autenticação no Microsoft Graph (Device Code).
  2. Uma chamada real ao Graph (/me).
  3. Leitura básica do Planner (planos a que você tem acesso via /me).

NÃO coleta tudo nem gera relatório ainda. É só o "ping" de validação.

Como rodar (no terminal, dentro de C:\\PROJETOS\\daily-backlog-agent):
    py step1_test_auth.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.graph_client import GraphClient


def main():
    g = GraphClient()

    # 1) Quem sou eu?
    me = g.get("/me")
    print("\n[OK] Autenticado no Microsoft Graph.")
    print(f"     Usuario: {me.get('displayName')} <{me.get('userPrincipalName')}>")

    # 2) Planos do Planner aos quais voce tem acesso direto
    try:
        plans = g.get_all("/me/planner/plans")
        print(f"\n[OK] Planos do Planner via /me: {len(plans)}")
        for p in plans:
            print(f"     - {p.get('title')}  (id={p.get('id')})")
        if not plans:
            print("     (nenhum plano em /me/planner/plans — na Fase 1.1 vamos")
            print("      enumerar os planos pelos Grupos/Times em que voce participa)")
    except Exception as e:
        print(f"\n[ATENCAO] Falha ao ler planos do Planner: {e}")
        print("Verifique se a permissao Tasks.Read foi consentida no App.")

    print("\nTeste concluido.\n")


if __name__ == "__main__":
    main()
