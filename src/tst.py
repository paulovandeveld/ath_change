import pandas as pd

file_path = "/home/paulo/athchange/src/data/klines/1INCHUSDT.parquet"

# Verifica se o arquivo existe antes de carregar
try:
    df = pd.read_parquet(file_path)
    print("Colunas do arquivo Parquet:", df.columns)
    print("Primeiras linhas:\n", df.head())
except Exception as e:
    print("Erro ao carregar o arquivo Parquet:", e)
