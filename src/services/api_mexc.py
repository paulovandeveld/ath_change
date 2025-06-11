import requests
import hmac
import hashlib
import time

class MexcAPI:
    BASE_URL = "https://api.mexc.com/api/v3"

    def __init__(self, api_key, api_secret, messenger=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.messenger = messenger

    def create_signature(self, query_string):
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def check_pair_exists(self, symbol):
        url = f"{self.BASE_URL}/exchangeInfo"
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Error accessing MEXC API: {response.status_code}")
            return False

        market_data = response.json()
        for market in market_data["symbols"]:
            if market["symbol"] == f"{symbol}USDT":
                return {
                    "exists": True,
                    "baseAssetPrecision": market["baseAssetPrecision"],
                    "quoteAssetPrecision": market["quoteAssetPrecision"]
                }
        return {"exists": False}

    def get_open_price(self, symbol):
        url = f"https://api.mexc.com/api/v3/klines"
        params = {
            "symbol": f"{symbol}USDT",
            "interval": "1d",  # Dados diários
            "limit": 1  # Apenas o último candle
        }
        
        response = requests.get(url, params=params)
        if response.status_code == 200:
            kline_data = response.json()
            return float(kline_data[0][1])  # O preço de abertura está na posição 1
        else:
            print(f"Erro ao recuperar preço de abertura para {symbol}: {response.status_code}")
            return None

    def place_limit_order(self, symbol, price, quantity, side):
        symbol = symbol + 'USDT'
        side = side
        order_type = "LIMIT"
        recv_window = 5000
        timestamp = int(time.time() * 1000)

        query_string = (
            f"symbol={symbol}&side={side}&type={order_type}"
            f"&quantity={quantity}&price={price}&recvWindow={recv_window}"
            f"&timestamp={timestamp}"
        )

        signature = self.create_signature(query_string)
        query_string += f"&signature={signature}"

        url = f"{self.BASE_URL}/order"
        headers = {"X-MEXC-APIKEY": self.api_key}

        response = requests.post(url, headers=headers, data=query_string)
        if response.status_code == 200:
            msg = f"Order placed successfully for {symbol} at price {price}!"
            print(msg)
            if self.messenger:  # Send Telegram message if messenger is provided
                self.messenger.send_message(msg)
            return response.json()
        else:
            error_msg = (
                f"Failed to place order for {symbol}. Error {response.status_code}: {response.json()}"
            )
            print(error_msg)
            if self.messenger:  # Send Telegram message if messenger is provided
                self.messenger.send_message(error_msg)
            return response.json()

    def fetch_trades(self):
        print("Loading trades history on exchange...")
        url = f"{self.BASE_URL}/myTrades"
        headers = {"X-MEXC-APIKEY": self.api_key}
        trades = []
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            raw_trades = response.json()

            # Transformando os dados conforme a estrutura do banco
            for trade in raw_trades:
                trades.append({
                    'symbol': trade['symbol'],
                    'side': 'BUY' if trade['isBuyer'] else 'SELL',
                    'quantity': float(trade['qty']),
                    'price': float(trade['price']),
                    'quoteQty': float(trade['quoteQty']),
                    'time': trade['time']
                })
            print(trades)
                
            self.messenger.send_message(f"Trades database updated successfully")
        except requests.exceptions.RequestException as e:
            self.messenger.send_message(f"Trades database update raises error: {e}")
        return trades