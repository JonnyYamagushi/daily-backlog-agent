@echo off
REM Wrapper chamado pelo Windows Task Scheduler todas as manhas.
REM Roda o pipeline completo (coleta -> normaliza -> metricas -> newsletter c/ IA)
REM e grava log em logs\run.log.

cd /d C:\PROJETOS\daily-backlog-agent
if not exist logs mkdir logs

echo ===================================================== >> logs\run.log
echo Execucao iniciada em %date% %time% >> logs\run.log

py run_all.py >> logs\run.log 2>&1

echo Execucao finalizada em %date% %time% >> logs\run.log
