import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

import requests
from binance.client import Client
from binance.helpers import round_step_size
from binance.exceptions import BinanceAPIException
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import btalib as bta
import config
import ast
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import sys
import time as t

# Conexão com o banco de dados SQLite
DB_PATH = "historical_high.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Criação da tabela de operações
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,  -- 'BUY' ou 'SELL'
            amount_usd REAL NOT NULL,
            open_price REAL NOT NULL,
            open_date TEXT NOT NULL,
            duration TEXT NOT NULL,  -- '24h' ou '7d'
            status TEXT NOT NULL DEFAULT 'OPEN'  -- 'OPEN' ou 'CLOSED'
        )
    """)
    conn.commit()
    conn.close()

def populate_step_sizes(): 
    try:
        info = cliente.get_exchange_info()

        for symbol_info in info['symbols']:
                for symbol_filter in symbol_info['filters']:
                    if symbol_filter['filterType'] == 'LOT_SIZE':
                        step_sizes[symbol_info['symbol']] = float(symbol_filter['stepSize'])
    # Symbol not found
        return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def get_step_size(symbol):
    return step_sizes.get(symbol, None)

def get_rounded_price(symbol, price):
    return round_step_size(price, get_step_size(symbol))

def register_operation(symbol, side, amount_usd, open_price, duration):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO operations (symbol, side, amount_usd, open_price, open_date, duration, status)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
    """, (symbol, side, amount_usd, open_price, datetime.now().isoformat(), duration))
    conn.commit()
    conn.close()

def get_open_operations(duration):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""SELECT * FROM operations WHERE duration = ? AND status = 'OPEN'
                   """, (duration,))
    operations = cursor.fetchall()
    conn.close()
    return operations

def get_posicoes():
    retries = 1
    success = False
    while not success:
        try:
            posicoes = cliente.futures_account()['positions']
            success = True
        except Exception as e:
            wait = retries * 15
            print ('Error! Waiting %s secs and re-trying...', wait)
            sys.stdout.flush()
            t.sleep(wait)
            retries += 1
    return posicoes

def create_order(ativo, stack, preço):
    qty = get_rounded_price(ativo, preço/stack)
    try:
        cliente.create_order(
                symbol = ativo,
                type = 'LIMIT',
                side = 'BUY',
                quantity = qty,
                timeInForce = 'GTC',
                price = preço
            )
    except BinanceAPIException as err: 
        print('Erro: ', err)

def close_operation(symbol):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE operations
        SET status = 'CLOSED'
        WHERE symbol = ? AND status = 'OPEN'
    """, (symbol,))
    conn.commit()
    conn.close()

def fetch_open_price(symbol):
    df = get_klines_spot(symbol, '1d', limit=2)
    if df.empty:
        df = get_klines(symbol, '1d', limit=2)
    df['open'] = df['open'].astype(float)
    open = df['open'].iloc[-1]  
    print('Preço de abertura de ', symbol, ' é de US$ ', open)
    return open # Valor fixo de teste, substitua pelo preço real

# Atualizando o config.py dinamicamente
def atualizar_config(arquivo_config, variaveis):
    with open(arquivo_config, 'r') as file:
        linhas = file.readlines()

    for i, linha in enumerate(linhas):
        for var_name, nova_lista in variaveis.items():
            if linha.lstrip().startswith(var_name):
                indentacao = linha[:len(linha) - len(linha.lstrip())]  # Preserva a indentação
                nova_linha = f"{indentacao}{var_name} = {nova_lista}\n"
                linhas[i] = nova_linha

    # Sobrescrever o arquivo com as novas variáveis
    with open(arquivo_config, 'w') as file:
        file.writelines(linhas)

def get_klines_spot(symbol, interval, limit=10):
    base_url = "https://api.binance.com/api/v1/klines"
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    response = requests.get(base_url, params=params)
    klines = response.json()
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def get_klines(symbol, interval, limit=10):
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    response = requests.get(base_url, params=params)
    klines = response.json()
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def get_klines_date(symbol, interval, day, limit=15):
    end_time = datetime(day.year, day.month, day.day, 0, 0)
    start_time = end_time - timedelta(days=50)
    
    # Convert start and end time to milliseconds
    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

    base_url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        'symbol': symbol,
        'interval': interval,
        'startTime': start_time_ms,
        'endTime': end_time_ms,
        'limit': 100  # Adjust limit as needed
    }
    response = requests.get(base_url, params=params)
    klines = response.json()
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def rma(data, length):
    alpha = 1.0 / length
    result = np.zeros_like(data, dtype=float)

    result[0] = data[0]

    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]

    return result

def calculate_rsi_for_day(symbol, interval, day):
    
    df = get_klines_date(symbol, interval, day, limit=100)
    df['close'] = df['close'].astype(float)
    df['RSI'] = bta.rsi(df['close'],period=14).df
    rsi = df['RSI'][-1]
    
    return rsi

def calculate_sma(data, period):
    return data.rolling(window=period).mean()

def calc_bb(data, period, std_dev, band="upper"):
    """
    Calcula as Bandas de Bollinger.
    
    Args:
        data (pd.Series): Série de preços ou dados.
        period (int): Período para a média móvel simples.
        std_dev (float): Multiplicador do desvio padrão.
        band (str): "upper" para a banda superior, "lower" para a banda inferior.
        
    Returns:
        pd.Series: Matriz com os valores calculados da banda.
    """
    sma = data.rolling(window=period).mean()
    std = data.rolling(window=period).std()
    
    if band == "upper":
        return sma + (std * std_dev)
    elif band == "lower":
        return sma - (std * std_dev)
    else:
        raise ValueError("Parâmetro 'band' deve ser 'upper' ou 'lower'.")

def check_trend(sma_1, sma_2):
    return sma_1 > sma_2

def check_trend_S(sma_1, sma_2):
    return sma_1 < sma_2

def get_last_closed_candle_rsi(symbol):
    df = get_klines(symbol, '1d', limit=21)
    df['close'] = df['close'].astype(float)
    df['RSI'] = bta.rsi(df['close'],period=14).df
    return df['RSI']  # Return DataFrame containing RSI values

def get_binance_futures_symbols():
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        symbols = [item['symbol'] for item in data['symbols'] if item['contractType'] == 'PERPETUAL' and item['symbol'].endswith('USDT')]
        return symbols
    else:
        print('Failed to fetch data from Binance API.')
        return []

def timestamp_to_text(date):
    """Converte um valor timestamp ou datetime para o formato 'yyyy-mm-dd'."""
    if isinstance(date, datetime):  # Se for um objeto datetime
        return date.strftime('%Y-%m-%d')
    elif isinstance(date, (int, float)):  # Se for timestamp
        return datetime.fromtimestamp(date).strftime('%Y-%m-%d')
    else:
        raise ValueError("O parâmetro 'date' deve ser um objeto datetime ou um timestamp.")

def get_historical_high(symbol, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT max_high, ath_date FROM historical_high WHERE symbol = ?", (symbol,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0], pd.to_datetime(result[1])
    return None, None

def update_historical_highs(symbol, high, date, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO historical_high (symbol, max_high, ath_date, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(symbol) DO UPDATE SET
        max_high = MAX(max_high, excluded.max_high),
        updated_at = CURRENT_TIMESTAMP
    """, (symbol, high, date))
    conn.commit()
    conn.close()

def update_if_new_high(symbol, high, date, db_path):
    current_high, _ = get_historical_high(symbol, db_path)
    if high > current_high:
        dt = timestamp_to_text(date)
        print("dt to new ath -- ", dt)
        update_historical_highs(symbol, high, dt, db_path)
        return True
    return False

exclude_symbols = ['SRMUSDT', 'HNTUSDT', 'TOMOUSDT', 'CVCUSDT', 'BTSUSDT', 'SCUSDT', 'RAYUSDT', 'FTTUSDT', 'COCOSUSDT', 'DGBUSDT', 'BLUEBIRDUSDT', 'FOOTBALLUSDT', 
                   'CFXUSDT', 'STRAXUSDT', 'CTKUSDT', 'ANTUSDT', 'STPTUSDT', 'SNTUSDT', 'MBLUSDT', 'RADUSDT', 'CVXUSDT', 'IDEXUSDT', 'SLPUSDT', 'GLMRUSDT', 'MDTUSDT', 
                   'AUDIOUSDT', 'OCEANUSDT', 'AGIXUSDT', 'WAVESUSDT', 'USDCUSDT', 'LOOMUSDT', 'XEMUSDT']
futures_symbols = get_binance_futures_symbols()
futures_symbols = [item for item in futures_symbols if item not in exclude_symbols]
#print(futures_symbols)
under_50 = []
under_55 = []
bull_trend = []
symbol_data = {}
rsi_data = []

for symbol in futures_symbols:
    try:
        df = get_klines(symbol, '1d', limit=205)
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['RSI'] = bta.rsi(df['close'], period = 14).df
        df['res'] = (df['close'] - df['open']) / df['open']
        df['volume'] = df['volume'].astype(float)
        max_high, ath_date = get_historical_high(symbol, DB_PATH)
        new_high = float(df['high'].iloc[-2])
        new_date = df.index[-2]
        if update_if_new_high(symbol, new_high, new_date, DB_PATH):
            print(f"New all-time high for {symbol}: {new_high}")
            max_high = new_high
            ath_date = new_date
        days_since_ath = (df.index[-2] - ath_date).days if ath_date else None
        df['Max_High'] = max_high
        df['Diff_ATH%'] = (df['close'] - df['Max_High']) / df['Max_High']
        df['Days_Since_ATH'] = days_since_ath
        rsi_data.append({
            'symbol': symbol,
            'RSI': df['RSI'].iloc[-2]
        })

        if True:
            sma_rsi = calculate_sma(df['RSI'], 14)
            sma_7 = calculate_sma(df['close'], 7)
            sma_20 = calculate_sma(df['close'], 20)
            sma_50 = calculate_sma(df['close'], 50)
            sma_200 = calculate_sma(df['close'], 200)
            sma_100 = calculate_sma(df['close'], 100)
            flag_7 = check_trend(sma_7.iloc[-2], sma_7.iloc[-3])
            flag_20 = check_trend(sma_20.iloc[-2], sma_20.iloc[-3])
            flag_50 = check_trend(sma_50.iloc[-2], sma_50.iloc[-3])
            flag_100 = check_trend(sma_100.iloc[-2], sma_100.iloc[-3])
            flag_200 = check_trend(sma_200.iloc[-2], sma_200.iloc[-3])
            flag_S_7 = check_trend_S(sma_7.iloc[-2], sma_7.iloc[-3])
            flag_S_20 = check_trend_S(sma_20.iloc[-2], sma_20.iloc[-3])
            flag_S_50 = check_trend_S(sma_50.iloc[-2], sma_50.iloc[-3])
            flag_S_100 = check_trend_S(sma_100.iloc[-2], sma_100.iloc[-3])
            flag_S_200 = check_trend_S(sma_200.iloc[-2], sma_200.iloc[-3])
            upper_10 = calc_bb(df['close'], period=10, std_dev=2, band="upper")
            lower_10 = calc_bb(df['close'], period=10, std_dev=2, band="lower")
            upper_20 = calc_bb(df['close'], period=20, std_dev=2, band="upper")
            lower_20 = calc_bb(df['close'], period=20, std_dev=2, band="lower")
            upper_50 = calc_bb(df['close'], period=50, std_dev=2, band="upper")
            lower_50 = calc_bb(df['close'], period=50, std_dev=2, band="lower")
            flag_dir_mas = sma_50.iloc[-2] > sma_100.iloc[-2] and sma_100.iloc[-2] > sma_200.iloc[-2]
            flag_dir_S_mas = sma_50.iloc[-2] < sma_100.iloc[-2] and sma_100.iloc[-2] < sma_200.iloc[-2]
            diff_ath = (df['close'].iloc[-2] - max_high) / max_high
            
            symbol_data[symbol] = {
                'RSI': float(df['RSI'].iloc[-2]),
                'Diff_ATH%': diff_ath,
                'Days_Since_ATH': days_since_ath,
                'SMA_RSI': sma_rsi.iloc[-2],
                'SMA_7': flag_7,
                'SMA_20': flag_20,
                'SMA_50': flag_50,
                'SMA_100': flag_100,
                'SMA_200': flag_200,
                'SMA_S_7': flag_S_7,
                'SMA_S_20': flag_S_20,
                'SMA_S_50': flag_S_50,
                'SMA_S_100': flag_S_100,
                'SMA_S_200': flag_S_200,
                'DIR_MAS': flag_dir_mas,
                'DIR_S_MAS': flag_dir_S_mas,
                'Close': df['res'].iloc[-2]
            }

            # Check if all conditions are met
            '''if rsi_values.iloc[-2] < 52 and check_trend(sma_50.iloc[-2], sma_50.iloc[-3]) and check_trend(sma_100.iloc[-2], sma_100.iloc[-3] and per_vol > 0.7):
                #under_50.append(symbol)
                #print(f"{symbol}: Last Closed Candle RSI = {rsi_values.iloc[-2]:.2f}, Last Closed Candle SMA_RSI = {sma_rsi.iloc[-2]:.2f}")
                ok = ok
            if rsi_values.iloc[-2] < 57 and check_trend(sma_50.iloc[-2], sma_50.iloc[-3]) and check_trend(sma_100.iloc[-2], sma_100.iloc[-3] and
                                                                                                            per_vol > 0.5 and per_vol < 1.3):
                #under_55.append(symbol) 
                #print(f"{symbol}: Last Closed Candle RSI = {rsi_values.iloc[-2]:.2f}, Last Closed Candle SMA_RSI = {sma_rsi.iloc[-2]:.2f}")
                ok = ok
            if (rsi_values.iloc[-2] > 70 and sma_rsi.iloc[-2] < 70 and check_trend(sma_50.iloc[-2], sma_50.iloc[-3]) and check_trend(sma_100.iloc[-2], sma_100.iloc[-3]) and
                    check_trend(sma_200.iloc[-2], sma_200.iloc[-3]) and df['res'].iloc[-2] < 0.03 and check_trend(sma_50.iloc[-2], sma_100.iloc[-2]) and
                    check_trend(sma_100.iloc[-2], sma_200.iloc[-2]) and per_vol > 0.5 and per_vol < 1.3):
                #bull_trend.append(symbol)
                #print(f"{symbol}: Last Closed Candle RSI = {rsi_values.iloc[-2]:.2f}, Last Closed Candle SMA_RSI = {sma_rsi.iloc[-2]:.2f}, Last Closed Candle Res = {df['res'].iloc[-2]:.4f}")
                ok = ok'''

    except Exception as e:
        print(f"Error fetching RSI for {symbol}: {e}")

all_data_df = pd.DataFrame(rsi_data)
all_data_df['RSI_Rank'] = all_data_df['RSI'].rank(ascending=False, method='dense')

# Atualizar o symbol_data com o RSI_Rank
for symbol in symbol_data.keys():
    symbol_data[symbol]['RSI_Rank'] = all_data_df.loc[all_data_df['symbol'] == symbol, 'RSI_Rank'].values[0]


LISTA_L_15_ST1 = []
LISTA_L_15_ST2 = []
LISTA_L_5_ST1 = []
LISTA_L_5_ST2 = []

LISTA_S_15 = []
LISTA_S_5 = []
LISTA_D1_W = []
LISTA_D1_D = []

LISTA_D1_L1 = []
LISTA_D1_L2 = []
LISTA_D1_L3 = []
LISTA_D1_L4 = []
LISTA_D1_L5 = []

LISTA_D1_N1 = []
LISTA_D1_N2 = []
LISTA_D1_N3 = []

# Sort the symbol data dictionary based on RSI values and print the top 10 symbols
sorted_symbols_top5 = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)[:5]
for symbol, data in sorted_symbols_top5:
    if float(data['Close']) < 0.09 and float(data['RSI']) < 80 and data['SMA_50'] == True:
        LISTA_L_15_ST1.append(symbol)
    if float(data['Close']) < 0.09 and float(data['RSI'] )< 80 and float(data['SMA_RSI']) < 70 and data['SMA_50'] == True and data['SMA_200'] == True:
        LISTA_L_15_ST2.append(symbol)
    if data['Close'] > -0.08 and data['Close'] < 0.06 and data['RSI'] < 65 and data['SMA_50'] == True:
        LISTA_L_5_ST1.append(symbol)

print(LISTA_L_15_ST1)
print(LISTA_L_15_ST2)
print(LISTA_L_5_ST1)

sorted_symbols_top10 = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)[:10]
for symbol, data in sorted_symbols_top10:
    if data['Close'] > -0.08 and data['Close'] < 0.06 and data['RSI'] > 65 and data['SMA_50'] == True and data['SMA_100'] == True and data['SMA_200'] == True and data['DIR_MAS'] == True:
        LISTA_L_5_ST2.append(symbol)

print(LISTA_L_5_ST2)

sorted_symbols_top60 = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)[30:60]
for symbol, data in sorted_symbols_top60:
    if data['Close'] < -0.03 and data['RSI'] > 25 and data['RSI'] < 40 and data['SMA_S_50'] == True and data['SMA_S_100'] == True and data['DIR_S_MAS'] == True:
        LISTA_S_15.append(symbol)

print(LISTA_S_15)
    
sorted_symbols_top30 = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)[10:30]
for symbol, data in sorted_symbols_top30:
    if data['RSI'] > 25 and data['RSI'] < 40 and data['SMA_S_50'] == True and data['SMA_S_100'] == True:
        LISTA_S_5.append(symbol)

print(LISTA_S_5)    

qty_items = int(len(symbol_data.items()) /  10) 
#print("qtd totoal de moedas    ----    ", qty_items)
sorted_symbols_daily = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)[:qty_items]
for symbol, data in sorted_symbols_daily:
    #print(f"Symbol: {symbol}, RSI: {data['RSI']}, SMA_RSI: {data['SMA_RSI']}, SMA_50: {data['SMA_50']}, SMA_100: {data['SMA_100']},  Close: {data['Close']}")

    if data['RSI'] > 80 and float(data['SMA_RSI']) < 75 and (data['RSI'] - float(data['SMA_RSI'])) > 15 and data['SMA_S_50'] == True and data['Close'] > 0.03 and data['Close'] < 0.6:
        LISTA_D1_W.append(symbol)

    elif data['RSI'] > 80 and float(data['SMA_RSI']) < 75 and (data['RSI'] - float(data['SMA_RSI'])) > 0 and (data['RSI'] - float(data['SMA_RSI'])) < 20 and data['SMA_S_50'] == True and data['Close'] > 0.03 and data['Close'] < 0.6:
        LISTA_D1_D.append(symbol)
print("Lista para deixar comprado durante a semana")
print(LISTA_D1_W) 
print("Lista para compra de 24h - Apenas Top 5 RSI")
print(LISTA_D1_D)    

qty_items_all = int(len(symbol_data.items())) 
sorted_symbols_daily_all = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)
for symbol, data in sorted_symbols_daily_all:
    rsi_quartil = data['RSI_Rank'] / qty_items_all
    #if data['RSI'] > 30:
        #print(f"Symbol: {symbol}\t RSI: {data['RSI']:.2f}\t SMA_RSI: {data['SMA_RSI']:.2f}\t RSI_Rank: {data['RSI_Rank']:.0f}\t RSI_Q: {rsi_quartil:.2f}\t Diff_ATH: {data['Diff_ATH%']:.2f}\t Days_Since_ATH: {data['Days_Since_ATH']}\t flag 7 {data['SMA_7'] }\t flag 20 {data['SMA_20'] }\t flag 50 {data['SMA_50'] }\t flag 100 {data['SMA_100'] }\t flag 200 {data['SMA_200'] }\t")

    if data['RSI'] > 65 and data['RSI'] < 95 and float(data['SMA_RSI']) < 75 and float(data['SMA_RSI']) > 60:
        LISTA_D1_L1.append(symbol)

    if data['RSI'] > 65 and data['RSI'] < 95 and rsi_quartil > 0.06 and rsi_quartil < 0.45:
        LISTA_D1_L2.append(symbol)

    if data['RSI'] > 65 and data['RSI'] < 95 and (float(data['SMA_RSI']) > 75 or float(data['SMA_RSI']) < 60) and data['Diff_ATH%'] > -0.4:
        LISTA_D1_L4.append(symbol)

    if data['RSI'] > 60 and data['Days_Since_ATH'] < 5:
        LISTA_D1_L5.append(symbol)

    if data['RSI'] > 30 and data['RSI'] < 65 and data['SMA_7'] == True and data['SMA_20'] == True \
        and data['SMA_50'] == True and data['SMA_100'] == True and data['SMA_200'] == False:
        LISTA_D1_N1.append(symbol)

    if data['RSI'] > 30 and data['RSI'] < 65 and data['Diff_ATH%'] > -0.08:
        LISTA_D1_N3.append(symbol)

print("\n---------------------------------------------------------")
LISTA_D1_L3 = list(set(LISTA_D1_L1) & set(LISTA_D1_L2))
print("Lista L1 -- 95>RSI>60 -- MA_RSI")
print(LISTA_D1_L1)   
print("Lista L2 -- 95>RSI>60 -- RSI_Quartil")
print(LISTA_D1_L2)   
print("Lista L3 -- Junção L1 e L2")
print(LISTA_D1_L3)   
print("Lista L4 -- 95>RSI>60 -- ATH%<-40")
print(LISTA_D1_L4)   
print("Lista L5 -- RSI>60 -- ATH<5")
print(LISTA_D1_L5)   
print("---------------------------------------------------------\n")
print("Lista N1 -- 65>RSI>30 -- SMA")
print(LISTA_D1_N1)   
print("Lista N3 -- 65>RSI>30 -- ATH%<-8")
print(LISTA_D1_N3)   
print("---------------------------------------------------------\n\n")


# Dicionário com as variáveis que você quer atualizar
symbols_daytrade = {
    'RSI_L_15_ST1': LISTA_L_15_ST1,
    'RSI_L_15_ST2': LISTA_L_15_ST2,
    'RSI_L_5_ST1': LISTA_L_5_ST1,
    'RSI_L_5_ST2': LISTA_L_5_ST2,
    'LISTA_D1_D': LISTA_D1_D,
    'RSI_S_5': [],
    'RSI_S_15': [],
}

# Atualiza o arquivo config.py
atualizar_config('/home/paulo/multitradeBot/config.py', symbols_daytrade)

amount_24h = 7
amount_7d = 30

# Inicializar banco de dados
init_db()
cliente = Client(config.API_KEY, config.API_SECRET)

# Initialize a global dictionary to store tick sizes.
step_sizes = dict()
# Call this function at the beginning of your code to populate the tick_sizes dictionary.
populate_step_sizes()

print("BINANCE futures!!")
# Filtrar moedas de interesse
sym_daytrade = [item for lista in symbols_daytrade.values() for item in lista]
print('Moedas para trade 24h hoje: ', set(sym_daytrade))
abrir_posicao = []  # Símbolos na lista filtered_24h mas não no dataframe
pos_aberta = [] 

posicoes = get_posicoes()
posicoes = pd.DataFrame.from_dict(posicoes)
posicoes = posicoes[(posicoes.positionAmt.astype(float) != 0)]
posicoes = posicoes[["symbol", "positionSide", "positionAmt", "unrealizedProfit", "isolatedWallet"]]
symbols_df = posicoes['symbol'].tolist()
abrir_posicao = [symbol for symbol in sym_daytrade if symbol not in symbols_df]
pos_aberta = [symbol for symbol in symbols_df if symbol not in sym_daytrade]
nao_fechar = [symbol for symbol in symbols_df if symbol in sym_daytrade]


print('Moedas com posição aberta: ', symbols_df)
print('Moedas com posição a abrir na Binance: ', abrir_posicao)
print('Moedas com posição a fechar na Binance: ', pos_aberta)
print('Moedas para trade semanal - Mercado SPOT: ', LISTA_D1_W)
print('Moedas para não fechar no futuros: ', nao_fechar)

symbols_swingtrade = {
    'sym_daytrade': set(abrir_posicao), #alterar depois para evitar fechar operação quando tem que abrir outra no mesmo dia.
    'sym_naofechar': nao_fechar,
    'LISTA_D1_D': LISTA_D1_D,
    'LISTA_D1_W': LISTA_D1_W,
    'LISTA_D1_L1': LISTA_D1_L1,
    'LISTA_D1_L2': LISTA_D1_L2,
    'LISTA_D1_L4': LISTA_D1_L4,
    'LISTA_D1_L5': LISTA_D1_L5,
    'LISTA_D1_N1': LISTA_D1_N1,
    'LISTA_D1_N3': LISTA_D1_N3
}

atualizar_config('/home/paulo/multitradeBot/setups.py', symbols_swingtrade)


# Processar lista de 24h
'''for symbol in fechar_posicao:
    close_operation(symbol)
    
for symbol in abrir_posicao:
    price = fetch_open_price(symbol) - 500  # Substituir pela chamada real
    #register_operation(symbol, "BUY", amount_24h, price, "24h")
    create_order(symbol, amount_24h, price)
    print("Ordem criada para ", symbol)'''

                
