import sys
import os

# Adiciona o diretório raiz ao PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Resolve the absolute path of the exclusion file
current_dir = os.path.dirname(os.path.abspath(__file__))
exclusion_file = os.path.join(current_dir, "configs/excluded_coins.json")
settings_file = os.path.join(current_dir, "configs/settings.json") 

### /src/main.py
from src.services.api_coingecko import CoinGeckoAPI
from src.services.api_mexc import MexcAPI
from src.services.utils import calculate_precision, format_dataframe, split_message, load_exclusion_lists, load_settings, is_excluded_coin, apply_symbol_corrections
from src.services.database import DatabaseManager
from src.strategies.rsi_analysis import RSIAnalyzer
from src.telegram_bot.messenger import TelegramMessenger
from src.sheets.google_sheet import GoogleSheetManager
from src.configs.credentials import Credentials

import pandas as pd


def main():
    # Initialize API clients and other services
    coingecko = CoinGeckoAPI()
    messenger = TelegramMessenger()
    mexc = MexcAPI(Credentials.MEXC_API_KEY, Credentials.MEXC_API_SECRET, messenger)
    db_trades = DatabaseManager("mexc_trades.db")
    rsi_analyzer = RSIAnalyzer(exclusion_file)
    
    #Key da planilha no Google Sheets
    sheet_manager = GoogleSheetManager(Credentials.SPREADSHEET_KEY) 

    # Fetch and process data from CoinGecko
    print("Fetching market data from CoinGecko...")
    all_coins_data = coingecko.fetch_all_coins(max_pages=5)
    
    # Filter relevant columns
    filtered_data = [
    {
        "id": coin["id"],
        "name": coin["name"],
        "symbol": coin["symbol"],
        "market_cap_rank": coin["market_cap_rank"],
        "ath_change_percentage": coin["ath_change_percentage"],
        "ath_date": coin["ath_date"],
        "total_volume": coin["total_volume"]  # Novo campo adicionado
    }
    for coin in all_coins_data
]

    # Convert to DataFrame and sort
    df = pd.DataFrame(filtered_data)
    df_sorted = df.sort_values(by="ath_change_percentage", ascending=False)
    
    # Update Google Sheets
    print("Updating Google Sheet...")
    sheet_manager.update_sheet(df_sorted)
    
    # Filter and sort data
    filtered_df = df[df["market_cap_rank"] <= 500]
    filtered_df = filtered_df.sort_values(by="ath_change_percentage", ascending=False)
    
    # Load exclusion lists
    exclusion_data = load_exclusion_lists(exclusion_file)
    
    # Filter coins based on exclusion criteria
    filtered_df = filtered_df[
        (~filtered_df.apply(lambda row: is_excluded_coin(row["name"], row["symbol"], exclusion_data), axis=1))
    ]
    
    filtered_df = apply_symbol_corrections(filtered_df, exclusion_data["symbol_corrections"])
    
    lowcap_df = df_sorted[
        (df_sorted["market_cap_rank"] >= 500) & (df_sorted["ath_change_percentage"] >= -20) & (df_sorted["total_volume"] >= 10000000) &
        (~df_sorted.apply(lambda row: is_excluded_coin(row["name"], row["symbol"], exclusion_data), axis=1))
    ]
    
    lowcap_df = apply_symbol_corrections(lowcap_df, exclusion_data["symbol_corrections"])

    # Format and send messages via Telegram
    formatted_data = format_dataframe(filtered_df.head(10))
    messages = split_message(formatted_data)
    for message in messages:
        messenger.send_message(message)
        
    formatted_lowcap_data = format_dataframe(lowcap_df)
    messages_lowcap = split_message(formatted_lowcap_data)
    for message in messages_lowcap:
        messenger.send_message(message)
        
    top_10_df = filtered_df.head(10)
    top_5_df = top_10_df.sort_values(by="market_cap_rank").head(5)
    top_5_df = top_5_df[~top_5_df['symbol'].isin(exclusion_data["mexc_exclude"])].reset_index(drop=True)     
    lowcap_df_close = ", ".join([symbol for symbol in exclusion_data["current_ath_lowcap"] if symbol not in lowcap_df['symbol'].tolist()])
    lowcap_df = lowcap_df[~lowcap_df['symbol'].isin(exclusion_data["current_ath_lowcap"])].reset_index(drop=True)
        
    settings = load_settings(settings_file)
    usd_amount = settings["usd_amount"]
    
    print("Moedas para abrir na MEXC pelo setup TOP 500: ", top_5_df["symbol"].tolist())
    print("Moedas para abrir na MEXC pelo setup low caps: ", lowcap_df["symbol"].tolist())
    
    messenger.send_message(f"Moedas lowcap para fechar: {lowcap_df_close}!")
    
    # Execute trading logic
    print("\nExecuting trading logic...")
    symbols = "; ".join(top_5_df["symbol"].tolist())
    messenger.send_message(f"Symbols: {symbols.upper()}")
    for _, row in top_5_df.iterrows():
        symbol = row["symbol"]
        if symbol in exclusion_data["current_ath"]:
            amount = usd_amount * 0.2
        else:
            amount = usd_amount 
            
        symbol = row["symbol"].upper()
        pair_info = mexc.check_pair_exists(symbol)
        if pair_info and pair_info["exists"]:
            print(f"\nPair {symbol}USDT found. Preparing to place order...")
            open_price = mexc.get_open_price(symbol)
            if open_price > 0:
                quantity = calculate_precision(amount, open_price, pair_info["baseAssetPrecision"])
                mexc.place_limit_order(symbol, open_price, quantity, "BUY")
            else:
                print(f"Open price for {symbol} could not be found.")
        else:
            print(f"\nPair {symbol}USDT not found on MEXC SPOT market.")
         
         
    print("\nExecuting trading logic for low caps...")
    symbols = ", ".join(lowcap_df["symbol"].tolist())
    messenger.send_message(f"Symbols Low Cap: {symbols.upper()}")   
    for _, row in lowcap_df.iterrows():
        symbol = row["symbol"].upper()
        pair_info = mexc.check_pair_exists(symbol)
        if pair_info and pair_info["exists"]:
            print(f"\nPair {symbol}USDT found. Preparing to place order...")
            open_price = mexc.get_open_price(symbol)
            if open_price > 0:
                quantity = calculate_precision(usd_amount/2, open_price, pair_info["baseAssetPrecision"])
                mexc.place_limit_order(symbol, open_price, quantity, "BUY")
            else:
                print(f"Open price for {symbol} could not be found.")
        else:
            print(f"\nPair {symbol}USDT not found on MEXC SPOT market.")
            
    
    # Executar a análise de RSI após a lógica principal
    print("Running RSI analysis...")
    rsi_data, symbol_data = rsi_analyzer.run_rsi_analysis()

    #Calculate RSI Rank and add it to symbol_data dict
    all_data_df = pd.DataFrame(rsi_data)
    all_data_df['RSI_Rank'] = all_data_df['RSI'].rank(ascending=False, method='dense')
    all_data_df['RSI_Rank_ASC'] = all_data_df['RSI'].rank(ascending=True, method='dense')
    for symbol in symbol_data.keys():
        symbol_data[symbol]['RSI_Rank'] = all_data_df.loc[all_data_df['symbol'] == symbol, 'RSI_Rank'].values[0]
        symbol_data[symbol]['RSI_Rank_ASC'] = all_data_df.loc[all_data_df['symbol'] == symbol, 'RSI_Rank_ASC'].values[0]
        
    print(f"RSI Analysis Completed. {len(rsi_data)} symbols analyzed.")
    
    # Opcional: Enviar os resultados para o Telegram
    messenger.send_message(f"RSI Analysis completed. {len(rsi_data)} symbols analyzed.")   

    #print(symbol_data)
    listas = rsi_analyzer.processar_symbols(symbol_data)
    for lista_nome, lista_conteudo in listas.items():
        print(f"{lista_nome}: {lista_conteudo}")
    #rsi_analyzer.atualizar_config('/home/paulo/multitradeBot/config.py', listas)
    rsi_analyzer.gerar_setups(listas)
    messenger.send_message(f"setups.py lists updated.")   
    
    
    #Trades Histórico
    #trades = mexc.fetch_trades()
    #db_trades.save_to_sqlite(trades)
    #db_trades.create_aggregated_view()

if __name__ == "__main__":
    main()

