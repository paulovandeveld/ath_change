import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import numpy as np
from src.configs.credentials import Credentials

class GoogleSheetManager:

    def __init__(self, spreadsheet_key):
        self.scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        self.credentials = ServiceAccountCredentials.from_json_keyfile_name(
            Credentials.GOOGLE_SHEET_CREDENTIALS, self.scope
        )
        self.client = gspread.authorize(self.credentials)
        self.spreadsheet_key = spreadsheet_key

    def update_sheet(self, df):
        sheet = self.client.open_by_key(self.spreadsheet_key)
        worksheet = sheet.get_worksheet(0)  # First sheet
        
        # Replace NaN values with a placeholder
        df = df.replace({np.nan: 0})
        
        # Select relevant columns only
        columns = ["id", "name", "symbol", "market_cap_rank", "ath_change_percentage", "ath_date", "total_volume"]
        df = df[columns]
        
        data = [df.columns.tolist()] + df.values.tolist()

        try:
            worksheet.clear()
            worksheet.update("A1", data)
            print("Google Sheet updated successfully.")
        except Exception as e:
            print(f"Error updating Google Sheet: {e}")
            problematic_row = None
            for index, row in enumerate(data[1:], start=1):
                try:
                    worksheet.update(f"A{index + 1}", [row])
                except Exception as inner_e:
                    problematic_row = row
                    print(f"Error with row {index}: {inner_e}")
                    break

        time.sleep(2)  # Avoid hitting API limits