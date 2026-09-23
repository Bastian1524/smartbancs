# SmartBancs - TCS NextGen - MVP 100% Validado

Transferencias bancarias concurrentes con anti-deadlock, idempotencia, ETL optimizado para IA y observabilidad.

**Repo:** https://github.com/Bastian1524/smartbancs
**Estado final validado:**
- ✅ 30 transferencias concurrentes
- ✅ ETL OK: 30 eventos -> JSONL + Parquet
- ✅ Total Conservado: 20000.0000

## Prerrequisitos Obligatorios

**1. Docker Desktop (Obligatorio para el reto)**
Este proyecto solo funciona con Docker Desktop corriendo.
- Descargar: https://www.docker.com/products/docker-desktop/
- Verificar: `docker --version` y `docker compose version`
- Sin Docker Desktop, `docker compose up` no levanta la DB ni Redis.

**2. Git y Python 3.11+** para `test_concurrent.py`

## Levantar con 1 Comando (para el jurado)

git clone https://github.com/Bastian1524/smartbancs.git && cd smartbancs && docker compose down -v && docker compose up --build -d && echo "Esperando 15s a que DB este Healthy..." && sleep 15 && python test_concurrent.py && docker compose exec transaction_api python src/etl/bancs_etl.py && docker exec -it smartbancs-db-1 psql -U bancs -d smartbancs -c "SELECT id, balance, SUM(balance) OVER() as total_20000 FROM accounts;" && echo "--- METRICS ---" && curl -s http://localhost:8000/metrics | head -20 && echo "--- ETL FILES ---" && docker compose exec transaction_api ls -lh tmp/
