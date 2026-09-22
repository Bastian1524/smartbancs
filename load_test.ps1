$jobs = @()
1..50 | ForEach-Object {
  $jobs += Start-Job -ScriptBlock {
    $body = '{"from":"ACC001","to":"ACC002","amount":1}'
    $key = [guid]::NewGuid().ToString()
    curl.exe -s -X POST http://localhost:8000/transfer -H "idempotency-key: $key" -H "Content-Type: application/json" --data-binary $body
  }
}
$jobs | Wait-Job | Receive-Job
docker compose exec db psql -U bancs -d smartbancs -c "SELECT id, balance, SUM(balance) OVER() as total FROM accounts;"
