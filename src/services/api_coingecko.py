import requests
import pandas as pd
import time

class CoinGeckoAPI:
    BASE_URL = "https://api.coingecko.com/api/v3/coins/markets"

    def __init__(self, currency="usd", order="market_cap_desc", per_page=250):
        self.params = {
            "vs_currency": currency,
            "order": order,
            "per_page": per_page,
            "sparkline": "false"
        }

    def fetch_all_coins(self, max_pages=5):
        all_coins_data = []
        for page in range(1, max_pages + 1):
            self.params["page"] = page
            print(f"Fetching page {page}...")
            response = requests.get(self.BASE_URL, params=self.params)
            if response.status_code == 200:
                page_data = response.json()
                if not page_data:
                    break
                all_coins_data.extend(page_data)
                time.sleep(2)  # Respect API rate limits
            else:
                print(f"Error accessing page {page}: {response.status_code}")
                break
        return all_coins_data