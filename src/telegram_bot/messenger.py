import requests
import urllib.parse
from src.configs.credentials import Credentials

class TelegramMessenger:

    def __init__(self):
        self.token = Credentials.TELEGRAM_BOT_TOKEN
        self.chat_id = Credentials.TELEGRAM_CHAT_ID
        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, msg):
        safe_string = urllib.parse.quote_plus(msg)
        full_url = f"{self.url}?chat_id={self.chat_id}&parse_mode=Markdown&text={safe_string}"
        response = requests.get(full_url)
        if response.status_code == 200:
            True
        else:
            print(f"Failed to send message: {response.status_code}")