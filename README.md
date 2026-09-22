# SmartBancs - Mi proyecto para TCS

Hola, soy Sebastián. Este es mi proyecto de transferencias bancarias concurrentes.

Al principio parecía simple: hacer un POST que mueve plata de una cuenta a otra. Pero cuando me pidieron probar 30 transacciones al mismo tiempo, ahí se complicó todo.

### Qué fue lo que más me costó

1.  **Los deadlocks:** Cuando ACC001 le manda a ACC002 y al mismo tiempo ACC002 le manda a ACC001, la base se quedaba colgada. Lo solucioné ordenando los IDs siempre de menor a mayor antes de bloquearlos. Con eso nunca se bloquean al revés.

2.  **Que no se cobre doble:** Si el cliente reintenta por error de internet, no le puedo descontar dos veces. Puse una clave única `idempotency_key`. Si llega la misma key, le digo "ya está hecho" y no muevo nada.

3.  **Que no se pierda plata:** La suma de todas las cuentas siempre tiene que ser 20000. Por más que lance 30 a la vez, no se puede crear ni perder dinero. Eso lo probé con `test_concurrent.py`.

### Cómo probarlo (para el jurado)

Es super simple, todo está en Docker para que no tengan que instalar nada:

```bash
# 1. Clonar
git clone https://github.com/Bastian1524/smartbancs.git
cd smartbancs

# 2. Levantar todo
docker compose up --build -d

# Esperen unos 10 segundos a que prenda la base

# 3. Probar una transferencia
curl -X POST http://localhost:8000/transfer -H "idempotency-key: prueba-1" -H "Content-Type: application/json" -d '{"from":"ACC001","to":"ACC002","amount":10}'

# 4. La prueba que pide el proyecto: 30 al mismo tiempo
python test_concurrent.py

# 5. Ver que la plata se conserva
docker compose exec db psql -U bancs -d smartbancs -c "SELECT id, balance, SUM(balance) OVER() as total FROM accounts;"
