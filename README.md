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

# PASO 0 - Prerrequisitos (Docker Desktop debe estar abierto)
docker --version
docker compose version

# PASO 1 - Clonar
git clone https://github.com/Bastian1524/smartbancs.git
cd smartbancs

# PASO 2 - Levantar todo limpio
docker compose down -v
docker compose up --build -d

# PASO 3 - Esperar 15 segundos a que la DB esté Healthy
docker ps

# PASO 4 - Probar 1 transferencia simple
curl -X POST http://localhost:8000/transfer -H "idempotency-key: jurado-1" -H "Content-Type: application/json" -d '{"from":"ACC001","to":"ACC002","amount":10}'

# PASO 5 - Prueba de 30 concurrentes (Reto 3.1)
python test_concurrent.py
# Debe decir: 30 transferencias enviadas

# PASO 6 - Ver que la plata se conserva (Debe ser 20000)
docker exec -it smartbancs-db-1 psql -U bancs -d smartbancs -c "SELECT SUM(balance) FROM accounts;"

# PASO 7 - ETL Bancs Legacy (Reto 3.2)
docker compose exec transaction_api python src/etl/bancs_etl.py
# Debe decir: ETL OK: 30 eventos -> JSONL + Parquet optimizado para IA

# PASO 8 - Ver archivos JSONL + Parquet generados
docker compose exec transaction_api ls -lh tmp/

# PASO 9 - IA No Bloqueante (Reto 3.3)
docker compose logs ai_api --tail 20

# PASO 10 - Observabilidad (Reto 3.4)
curl http://localhost:8000/metrics
docker compose logs transaction_api --tail 20
