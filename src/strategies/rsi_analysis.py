import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

from src.services.utils import load_exclusion_lists
from src.configs.credentials import Credentials
from datetime import datetime, timedelta
from ta.volatility import BollingerBands
import pandas as pd
import sqlite3
import time
import os
import requests
import btalib as bta

DATA_DIR = "/home/paulo/athchange/src/data/klines"

class RSIAnalyzer:
    def __init__(self, exclusion_file):
        self.exclusion_data = load_exclusion_lists(exclusion_file)
        self.exclude_symbols = set(self.exclusion_data.get("fut_binance_exclude", []))  # Usando somente a lista da Binance Futures
        self.db_path = os.path.join(os.path.dirname(__file__), "../data/historical_high.db")

    def save_klines(self, symbol, df):
        """Salva os klines localmente em Parquet."""
        os.makedirs(DATA_DIR, exist_ok=True)
        file_path = f"{DATA_DIR}/{symbol}.parquet"

        if df.index.name == 'timestamp':  
            df = df.reset_index()  # Garante que timestamp seja uma coluna antes de salvar

        print(df.head())
        df.to_parquet(file_path, index=False)  # Salva sem índice oculto

    def load_klines(self, symbol):
        """Carrega os klines salvos localmente, se existirem."""
        file_path = f"{DATA_DIR}/{symbol}.parquet"
        try:
            df = pd.read_parquet(file_path)
            #print(df.head())
            df['timestamp'] = pd.to_datetime(df['timestamp'])  # Converte para datetime
            df.set_index('timestamp', inplace=True)  # Define como índice
            return df
        except FileNotFoundError:
            return None  # Retorna None se o arquivo não existir

    def get_binance_futures_symbols(self):
        url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            symbols = [item['symbol'] for item in data['symbols'] if item['contractType'] == 'PERPETUAL' and item['symbol'].endswith('USDT')]
            return symbols
        else:
            print('Failed to fetch data from Binance API.')
            return []

    def get_klines(self, symbol, interval, limit=10):
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

    def get_klines_cached(self, symbol, interval='1d', limit=205):
        """Busca klines da Binance e atualiza apenas os dados novos."""
        saved_df = self.load_klines(symbol)
        #print(saved_df.head())
        
        if saved_df is not None and not saved_df.empty:
            last_timestamp = saved_df.index.max()
            new_df = self.get_klines(symbol, interval, limit)  # Pega os novos dados
            new_df = new_df[new_df.index > last_timestamp]  # Agora compara corretamente
            
            if not new_df.empty:
                updated_df = pd.concat([saved_df, new_df], ignore_index=True)
                self.save_klines(symbol, updated_df)
                return updated_df
            return saved_df  # Se não houver novos dados, retorna os já salvos
        else:
            df = self.get_klines(symbol, interval, limit)  # Primeira vez, pega tudo
            #print(df.columns)
            self.save_klines(symbol, df)
            return df

    def calculate_rsi(self, df, period=14):
        """Cálculo simplificado do RSI."""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        return df

    def calculate_sma(self, data, period):
        return data.rolling(window=period).mean()

    def check_trend(self, sma_1, sma_2):
        return sma_1 > sma_2

    def check_trend_S(self, sma_1, sma_2):
        return sma_1 < sma_2

    def calculate_close_percentage(self, series, window):
        """Calculate the percentage of prior closes lower than the current close."""
        result = []
        for i in range(len(series)):
            if i < window:
                past_window = series[:i]
                current_close = series[i]
                higher_days = (past_window < current_close).sum()
                pct = higher_days / window
            else:
                past_window = series[i - window:i]
                current_close = series[i]
                pct = (past_window < current_close).sum() / window
            result.append(round(pct, 4))
        return result

    def calc_bb(self, data, period, std_dev, band="upper"):
        sma = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        
        if band == "upper":
            return sma + (std * std_dev)
        elif band == "lower":
            return sma - (std * std_dev)
        else:
            raise ValueError("Parâmetro 'band' deve ser 'upper' ou 'lower'.")

    def register_new_high(self, symbol):
        """Registra um novo símbolo no banco de dados com base no maior valor histórico."""
        df = self.get_klines(symbol, '1d', limit=60)
        print(df)
        max_high_row = df.loc[df['high'].idxmax()]
        max_high = float(max_high_row['high'])
        ath_date = self.timestamp_to_text(max_high_row.name)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO historical_high (symbol, max_high, ath_date) VALUES (?, ?, ?)",
            (symbol, max_high, ath_date)
        )
        conn.commit()
        conn.close()
        
        print(f"Registered new symbol {symbol} with max_high: {max_high}")
        return max_high, ath_date

    def get_historical_high(self, symbol):
        """Consulta o banco de dados para recuperar o ATH."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT max_high, ath_date FROM historical_high WHERE symbol = ?", (symbol,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0], pd.to_datetime(result[1])
        return None, None

    def timestamp_to_text(self, date):
        """Converte um valor timestamp ou datetime para o formato 'yyyy-mm-dd'."""
        if isinstance(date, datetime):  # Se for um objeto datetime
            return date.strftime('%Y-%m-%d')
        elif isinstance(date, (int, float)):  # Se for timestamp
            return datetime.fromtimestamp(date).strftime('%Y-%m-%d')
        else:
            raise ValueError("O parâmetro 'date' deve ser um objeto datetime ou um timestamp.")

    def update_historical_highs(self, symbol, high, date):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historical_high (symbol, max_high, ath_date, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE 
            SET max_high = MAX(historical_high.max_high, excluded.max_high),
                ath_date = CASE 
                              WHEN excluded.max_high > historical_high.max_high THEN excluded.ath_date 
                              ELSE historical_high.ath_date 
                           END,
                updated_at = CURRENT_TIMESTAMP
        """, (symbol, high, date))
        conn.commit()
        conn.close()

    def update_if_new_high(self, symbol, new_high, new_date):
        """Atualiza o banco de dados se um novo ATH for encontrado."""
        current_high, ath_date = self.get_historical_high(symbol)
        
        #print(f"Symbol: {symbol}, new_high {new_high:.2f}, new_date {new_date}, current_high {current_high},  current_date {ath_date}!!!!")
        if current_high is None:
            current_high, ath_date = self.register_new_high(symbol)
            return True
            
        if new_high > current_high:
            dt = self.timestamp_to_text(new_date)
            #print(f"Atualizando high de {symbol} no valor de {new_high} e data {dt}")
            self.update_historical_highs(symbol, new_high, dt)
            return True
        return False
      
    def filter_symbols_based_on_conditions(self, symbol_data, top_n, conditions):
        """
        Função genérica para filtrar os símbolos baseados nas condições fornecidas.
        :param symbol_data: Dicionário com os dados dos símbolos
        :param top_n: Número de símbolos a ser considerado
        :param conditions: Lista de condições de filtragem a serem aplicadas
        :return: Lista com os símbolos que atendem às condições
        """
        sorted_symbols = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)[:top_n]
        filtered_symbols = []
        
        for symbol, data in sorted_symbols:
            if all(cond(data) for cond in conditions):
                filtered_symbols.append(symbol)
        
        return filtered_symbols
      
    def condition_l_15_st1(self, data):
        return float(data['Close']) < 0.09 and float(data['RSI']) < 80 and data['SMA_50'] == True

    def condition_l_15_st2(self, data):
        return float(data['Close']) < 0.09 and float(data['RSI']) < 80 and float(data['SMA_RSI']) < 70 and data['SMA_50'] == True and data['SMA_200'] == True

    def condition_l_5_st1(self, data):
        return data['Close'] > -0.08 and data['Close'] < 0.06 and data['RSI'] < 65 and data['SMA_50'] == True

    def condition_l_5_st2(self, data):
        return data['Close'] > -0.08 and data['Close'] < 0.06 and data['RSI'] > 65 and data['SMA_50'] == True and data['SMA_100'] == True and data['SMA_200'] == True and data['DIR_MAS'] == True

    def condition_s_15(self, data):
        return data['Close'] < -0.03 and data['RSI'] > 25 and data['RSI'] < 40 and data['SMA_S_50'] == True and data['SMA_S_100'] == True and data['DIR_S_MAS'] == True

    def condition_s_5(self, data):
        return data['RSI'] > 25 and data['RSI'] < 40 and data['SMA_S_50'] == True and data['SMA_S_100'] == True

    def condition_d1_w(self, data):
        return data['RSI'] > 80 and float(data['SMA_RSI']) < 75 and (data['RSI'] - float(data['SMA_RSI'])) > 15 and data['SMA_S_50'] == True and data['Close'] > 0.03 and data['Close'] < 0.6

    def condition_d1_d(self, data):
        return data['RSI'] > 80 and float(data['SMA_RSI']) < 75 and (data['RSI'] - float(data['SMA_RSI'])) > 0 and (data['RSI'] - float(data['SMA_RSI'])) < 20 and data['SMA_S_50'] == True and data['Close'] > 0.03 and data['Close'] < 0.6

    def condition_d1_l1(self, data):
        return data['RSI'] > 65 and data['RSI'] < 95 and float(data['SMA_RSI']) < 70 and float(data['SMA_RSI']) > 60
            
    def condition_d1_l2(self, data, rsi_quartil):
        return data['RSI'] > 65 and data['RSI'] < 75 and 0.06 < rsi_quartil < 0.45

    def condition_d1_l4(self, data):
        return data['RSI'] > 65 and data['RSI'] < 95 and ((float(data['SMA_RSI']) > 75 and  float(data['SMA_RSI']) < 80) or float(data['SMA_RSI']) < 60) and data['Diff_ATH%'] > -0.25

    def condition_d1_l5(self, data):
        return data['RSI'] > 70 and data['RSI'] < 90 and data['Days_Since_ATH'] < 5

    def condition_d1_n1(self, data):
        return (55 < data['RSI'] < 65 and all([data['SMA_7'], data['SMA_20'], data['SMA_50'], data['SMA_100']])
                and not data['SMA_200'])
                
    def condition_d1_n2_bb1(self, data):
        return data['RSI'] > 55 and data['RSI'] < 65 and all([data['BB10_INF'], data['BB20_BSUP'], data['BB50_SUP']])
        
    def condition_d1_n2_bb2(self, data):
        return data['RSI'] > 57 and data['RSI'] < 65 and all([data['BB10_TOP'], data['BB20_BSUP'], data['BB50_SUP']])
        
    def condition_d1_n2_bb3(self, data):
        return data['RSI'] > 30 and data['RSI'] < 65  and all([data['BB10_INF'], data['BB20_INF'], data['BB50_SUP']])

    def condition_d1_n3(self, data):
        return data['RSI'] > 60 and data['RSI'] < 65 and data['Diff_ATH%'] > -0.08

    def condition_d1_b1(self, data):
        return data['RSI'] < 28 and float(data['SMA_RSI']) > 30
        
    def condition_d1_b2(self, data):
        return data['RSI'] < 28 and all([data['BB10_BOT'], data['BB20_BOT'], data['BB50_BOT']])

    def condition_d1_b3(self, data, rsi_quartil_asc):
        return data['RSI'] < 28 and rsi_quartil_asc > 0.12
        
    def processar_symbols(self, symbol_data):
        qty_items_all = len(symbol_data)
        listas = {
            'L_15_ST1': [],
            'L_15_ST2': [],
            'L_5_ST1': [],
            'L_5_ST2': [],
            'S_15': [],
            'S_5': [],
            'D1_W': [],
            'D1_D': [],
            'D1_L1': [],
            'D1_L2': [],
            'D1_L4': [],
            'D1_L5': [],
            'D1_N1': [],
            'D1_N2_BB1': [],
            'D1_N2_BB2': [],
            'D1_N2_BB3': [],
            'D1_N3': [],
            'D1_B1': [],
            'D1_B2': [],
            'D1_B3': []
        }

        # Filtra símbolos e atualiza as listas
        listas['L_15_ST1'] = self.filter_symbols_based_on_conditions(symbol_data, 5, [self.condition_l_15_st1])
        listas['L_15_ST2'] = self.filter_symbols_based_on_conditions(symbol_data, 5, [self.condition_l_15_st2])
        listas['L_5_ST1'] = self.filter_symbols_based_on_conditions(symbol_data, 5, [self.condition_l_5_st1])
        listas['L_5_ST2'] = self.filter_symbols_based_on_conditions(symbol_data, 10, [self.condition_l_5_st2])
        listas['S_15'] = self.filter_symbols_based_on_conditions(symbol_data, 30, [self.condition_s_15])
        listas['S_5'] = self.filter_symbols_based_on_conditions(symbol_data, 20, [self.condition_s_5])
        listas['D1_W'] = self.filter_symbols_based_on_conditions(symbol_data, 20, [self.condition_d1_w])
        listas['D1_D'] = self.filter_symbols_based_on_conditions(symbol_data, 10, [self.condition_d1_d])
        
        sorted_symbols_daily_all = sorted(symbol_data.items(), key=lambda x: x[1]['RSI'], reverse=True)
        for symbol, data in sorted_symbols_daily_all:
            rsi_quartil = data['RSI_Rank'] / qty_items_all
            rsi_quartil_asc = data['RSI_Rank_ASC'] / qty_items_all
            #print(f"Symbol: {symbol}, rsi_quartil RSI: {rsi_quartil}")

            if self.condition_d1_l1(data):
                listas['D1_L1'].append(symbol)
            if self.condition_d1_l2(data, rsi_quartil):
                listas['D1_L2'].append(symbol)
            if self.condition_d1_l4(data):
                listas['D1_L4'].append(symbol)
            if self.condition_d1_l5(data):
                listas['D1_L5'].append(symbol)
            if self.condition_d1_n1(data):
                listas['D1_N1'].append(symbol)
            if self.condition_d1_n2_bb1(data):
                listas['D1_N2_BB1'].append(symbol)
            if self.condition_d1_n2_bb2(data):
                listas['D1_N2_BB2'].append(symbol)
            if self.condition_d1_n2_bb3(data):
                listas['D1_N2_BB3'].append(symbol)
            if self.condition_d1_n3(data):
                listas['D1_N3'].append(symbol)
            if self.condition_d1_b1(data):
                listas['D1_B1'].append(symbol)
            if self.condition_d1_b2(data):
                listas['D1_B2'].append(symbol)
            if self.condition_d1_b3(data, rsi_quartil_asc):
                listas['D1_B3'].append(symbol)


        return listas      
    
    def atualizar_config(self, arquivo_config, variaveis):
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
    
    def carregar_correcoes(self):
        """
        Carrega o mapeamento de correções de símbolos a partir de um arquivo JSON.
        """
        dados = self.exclusion_data
        return dados.get("binance_mexc_correction", {})  # Retorna apenas as correções de símbolos


    def corrigir_simbolos(self, symbols_dict):
        """
        Aplica as correções de símbolos em um dicionário de listas com base no mapeamento.
        """
        symbol_mapping = self.carregar_correcoes()
        corrected_symbols = {
            lista: [symbol_mapping.get(symbol, symbol) for symbol in symbols]
            for lista, symbols in symbols_dict.items()
        }
        return corrected_symbols
    
    def gerar_setups(self, listas):
        
        #symbol_mapping = self.carregar_correcoes(self.exclusion_data)
        symbols_swingtrade = {
            'LISTA_D1_D': listas['D1_D'],
            'LISTA_D1_W': listas['D1_W'],
            'LISTA_D1_L1': listas['D1_L1'],
            'LISTA_D1_L2': listas['D1_L2'],
            'LISTA_D1_L4': listas['D1_L4'],
            'LISTA_D1_L5': listas['D1_L5'],
            'LISTA_D1_N1': listas['D1_N1'],
            'LISTA_D1_N2_BB1': listas['D1_N2_BB1'],
            'LISTA_D1_N2_BB2': listas['D1_N2_BB2'],
            #'LISTA_D1_N2_BB3': listas['D1_N2_BB3'],
            'LISTA_D1_N3': listas['D1_N3'],
            'LISTA_D1_B1': listas['D1_B1'],
            'LISTA_D1_B2': listas['D1_B2'],
            'LISTA_D1_B3': listas['D1_B3'],
        }
        
        symbols_swingtrade_corrigido = self.corrigir_simbolos(symbols_swingtrade)

        self.atualizar_config('/mnt/e/Backup_Paulo/multitradeBot/setups.py', symbols_swingtrade_corrigido)
    
    def run_rsi_analysis(self):
        """Fluxo principal do cálculo de RSI e análise."""
        symbols = self.get_binance_futures_symbols()
        #symbols = ['XRPUSDT']
        filtered_symbols = [s for s in symbols if s not in self.exclude_symbols]

        rsi_data = []
        symbol_data = {}

        for symbol in filtered_symbols:
            #print(f"Symbol: {symbol}")
            df = self.get_klines(symbol, '1d', limit=205)
            #df = self.get_klines_cached(symbol, '1d', limit=205)

            
            if len(df) < 15:
                print(f"Symbol {symbol} possui menos de 15 klines. Interrompendo o loop.")
                break
            
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['volume'] = df['volume'].astype(float)    
            df['RSI'] = bta.rsi(df['close'], period = 14).df
            df['res'] = (df['close'] - df['open']) / df['open']

            # Recuperar histórico e calcular novos valores
            max_high, ath_date = self.get_historical_high(symbol)
            new_high = float(df['high'].iloc[-2])
            new_date = df.index[-2]

            if self.update_if_new_high(symbol, new_high, new_date):
                max_high, ath_date = new_high, new_date

            days_since_ath = (df.index[-2] - pd.to_datetime(ath_date)).days if ath_date else None
            df['Max_High'] = max_high
            df['Diff_ATH%'] = (df['close'] - max_high) / max_high
            df['Days_Since_ATH'] = days_since_ath
            
            bb_10 = BollingerBands(df['close'], window = 10, window_dev = 1.5)
            bb_20 = BollingerBands(df['close'], window = 20, window_dev = 2)
            bb_50 = BollingerBands(df['close'], window = 50, window_dev = 2.5)

            rsi_data.append({"symbol": symbol, "RSI": df['RSI'].iloc[-2]})
            
            sma_rsi = self.calculate_sma(df['RSI'], 14)
            sma_7 = self.calculate_sma(df['close'], 7)
            sma_10 = self.calculate_sma(df['close'], 10)
            sma_20 = self.calculate_sma(df['close'], 20)
            sma_50 = self.calculate_sma(df['close'], 50)
            sma_200 = self.calculate_sma(df['close'], 200)
            sma_100 = self.calculate_sma(df['close'], 100)
            flag_7 = self.check_trend(sma_7.iloc[-2], sma_7.iloc[-3])
            flag_20 = self.check_trend(sma_20.iloc[-2], sma_20.iloc[-3])
            flag_50 = self.check_trend(sma_50.iloc[-2], sma_50.iloc[-3])
            flag_100 = self.check_trend(sma_100.iloc[-2], sma_100.iloc[-3])
            flag_200 = self.check_trend(sma_200.iloc[-2], sma_200.iloc[-3])
            flag_S_7 = self.check_trend_S(sma_7.iloc[-2], sma_7.iloc[-3])
            flag_S_20 = self.check_trend_S(sma_20.iloc[-2], sma_20.iloc[-3])
            flag_S_50 = self.check_trend_S(sma_50.iloc[-2], sma_50.iloc[-3])
            flag_S_100 = self.check_trend_S(sma_100.iloc[-2], sma_100.iloc[-3])
            flag_S_200 = self.check_trend_S(sma_200.iloc[-2], sma_200.iloc[-3])
            upper_10 = bb_10.bollinger_hband()
            lower_10 = bb_10.bollinger_lband()
            upper_20 = bb_20.bollinger_hband()
            lower_20 = bb_20.bollinger_lband()
            upper_50 = bb_50.bollinger_hband()
            lower_50 = bb_50.bollinger_lband()
            flag_10bb_Asup = df['close'].iloc[-2] > upper_10.iloc[-2]
            flag_10bb_inf =  df['close'].iloc[-2]  < sma_10.iloc[-2] 
            flag_10bb_Ainf = df['close'].iloc[-2] < lower_10.iloc[-2]
            flag_20bb_Bsup = df['close'].iloc[-2] > sma_20.iloc[-2]  and df['close'].iloc[-2] < upper_20.iloc[-2]
            flag_20bb_inf = df['close'].iloc[-2]  < sma_20.iloc[-2] 
            flag_20bb_Ainf = df['close'].iloc[-2] < lower_20.iloc[-2]
            flag_50bb_sup = df['close'].iloc[-2]  > sma_50.iloc[-2]
            flag_50bb_Ainf = df['close'].iloc[-2] < lower_50.iloc[-2]
            flag_dir_mas = sma_50.iloc[-2] > sma_100.iloc[-2] and sma_100.iloc[-2] > sma_200.iloc[-2]
            flag_dir_S_mas = sma_50.iloc[-2] < sma_100.iloc[-2] and sma_100.iloc[-2] < sma_200.iloc[-2]
            diff_ath = (df['close'].iloc[-2] - max_high) / max_high

            # Volume based indicators
            vol_sma_7 = self.calculate_sma(df['volume'], 7)
            vol_sma_14 = self.calculate_sma(df['volume'], 14)
            vol_sma_20 = self.calculate_sma(df['volume'], 20)

            df['Volume_SMA7'] = vol_sma_7
            df['Volume_SMA14'] = vol_sma_14
            df['Volume_SMA20'] = vol_sma_20

            for periodo in [7, 14, 20]:
                df[f'Vol%_{periodo}'] = df['volume'] / df[f'Volume_SMA{periodo}']

            for periodo in [30, 90, 150]:
                df[f'Close%_{periodo}d'] = self.calculate_close_percentage(df['close'], periodo)

            volume_flag = all(df[f'Vol%_{p}'].iloc[-2] > 1 for p in [7, 14, 20])
            
            symbol_data[symbol] = {
                "RSI": df['RSI'].iloc[-2],
                "Diff_ATH%": df['Diff_ATH%'].iloc[-2],
                "Days_Since_ATH": days_since_ath,
                "SMA_RSI": sma_rsi.iloc[-2] if not pd.isna(sma_rsi.iloc[-2]) else float('inf'),
                "SMA_7": flag_7,
                "SMA_20": flag_20,
                "SMA_50": flag_50,
                "SMA_100": flag_100,
                "SMA_200": flag_200,
                "SMA_S_7": flag_S_7,
                "SMA_S_20": flag_S_20,
                "SMA_S_50": flag_S_50,
                "SMA_S_100": flag_S_100,
                "SMA_S_200": flag_S_200,
                "DIR_MAS": flag_dir_mas,
                "DIR_S_MAS": flag_dir_S_mas,
                "BB10_TOP": flag_10bb_Asup,
                "BB10_INF": flag_10bb_inf,
                "BB10_BOT": flag_10bb_Ainf,
                "BB20_BSUP": flag_20bb_Bsup,
                "BB20_INF": flag_20bb_inf,
                "BB20_BOT": flag_20bb_Ainf,
                "BB50_SUP": flag_50bb_sup,
                "BB50_BOT": flag_50bb_Ainf,
                "Vol%_7": df['Vol%_7'].iloc[-2],
                "Vol%_14": df['Vol%_14'].iloc[-2],
                "Vol%_20": df['Vol%_20'].iloc[-2],
                "VOLUME_FLAG": volume_flag,
                "Close%_30d": df['Close%_30d'].iloc[-2],
                "Close%_90d": df['Close%_90d'].iloc[-2],
                "Close%_150d": df['Close%_150d'].iloc[-2],
                "Close": df['res'].iloc[-2]
            }
            print(symbol, symbol_data[symbol]['RSI'])
         
        print("Final RSI Data:")
        '''for symbol, data in symbol_data.items():
            print(f"Symbol: {symbol}, Last RSI: {data['RSI']:.2f}")
        ''' 
        
        return rsi_data, symbol_data
