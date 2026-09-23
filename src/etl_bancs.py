#Simula ETL de Bancs legacy hacia Data Lake para IA
import pandas as pd
from datetime import datetime
import json
import os

RAW_FILE = "data/raw_transacciones.csv"
CLEAN_FILE = "data/clean_transacciones.jsonl"

def etl():
    print("[ETL] Iniciando transformación Bancs -> IA")
    # Simula lote crudo con nulos y formatos raros
    df = pd.read_csv(RAW_FILE) if os.path.exists(RAW_FILE) else pd.DataFrame([
        {"id":"TX1","from":None,"to":"ACC002","amount":" 10.50 ","fecha":"2026/09/22"},
        {"id":"TX2","from":"ACC001","to":"ACC002","amount":None,"fecha":"22-09-2026"},
        {"id":"TX3","from":" ACC001 ","to":" ACC003 ","amount":"20","fecha":None},
    ])

    print(f"[ETL] Registros crudos: {len(df)}")
    # Limpieza
    df = df.dropna(subset=['from','to']) # elimina nulos críticos
    df['from'] = df['from'].astype(str).str.strip().str.upper()
    df['to'] = df['to'].astype(str).str.strip().str.upper()
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce').fillna(datetime.now())
    df['fecha'] = df['fecha'].dt.strftime('%Y-%m-%d')

    # Estructura optimizada para IA: JSONL + features
    os.makedirs("data", exist_ok=True)
    df.to_json(CLEAN_FILE, orient="records", lines=True)
    print(f"[ETL] Limpio -> {CLEAN_FILE}: {len(df)} registros listos para IA")
    return df

if __name__ == "__main__":
    etl()