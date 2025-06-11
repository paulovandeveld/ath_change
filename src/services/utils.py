import math
import json
import os

def calculate_precision(usd_amount, open_price, precision): 
    """
    Calculate the quantity of an asset based on the amount in USD, its open price, and the precision.
    """
    raw_quantity = usd_amount / open_price
    return round(raw_quantity, precision)

def format_dataframe(df):
    """
    Format a DataFrame into a string representation for messaging or logging.
    """
    formatted_rows = [
        f"Rank: {row['market_cap_rank']} - Symbol: {row['symbol']} - Name: {row['name']}"
        for _, row in df.iterrows()
    ]
    return "\n".join(formatted_rows)

def split_message(msg, chunk_size=4096):
    """
    Split a message into chunks if it exceeds the allowed size (default: 4096 characters).
    """
    return [msg[i:i + chunk_size] for i in range(0, len(msg), chunk_size)]
    
def load_exclusion_lists(file_path):
    """Load exclusion lists from a JSON file."""
    with open(file_path, 'r') as file:
        return json.load(file)
        
def load_settings(file_path):
    """Load general settings from a JSON file."""
    with open(file_path, 'r') as file:
        return json.load(file)
    
def is_excluded_coin(coin_name, coin_symbol, exclusion_data):
    """Check if a coin should be excluded based on exclusion lists."""
    stable_keywords = exclusion_data["stable_keywords"]
    wrapped_keywords = exclusion_data["wrapped_keywords"]
    manual_exclude = exclusion_data["manual_exclude"]

    if any(keyword in coin_name.lower() or keyword in coin_symbol.lower() for keyword in stable_keywords + wrapped_keywords):
        return True
    if coin_name.lower() in manual_exclude or coin_symbol.lower() in manual_exclude:
        return True
    return False

def apply_symbol_corrections(df, corrections):
    """Apply manual symbol corrections to a DataFrame."""
    for coin_id, corrected_symbol in corrections.items():
        df.loc[df['id'] == coin_id, 'symbol'] = corrected_symbol
    return df