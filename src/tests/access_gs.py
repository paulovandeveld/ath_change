from oauth2client.service_account import ServiceAccountCredentials
import gspread

def test_google_sheet_access():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "/home/paulo/multitradeBot/credentials.json", scope
    )
    client = gspread.authorize(credentials)

    try:
        spreadsheet = client.open_by_key("1ye88snPoiuwq3yywYpJJJ11408ShlSOA9syyyVOp_pk")
        worksheet = spreadsheet.get_worksheet(0)
        #worksheet.clear()
        print("Test access successful. Worksheet title:", worksheet.title)
    except Exception as e:
        print("Error during Google Sheets access test:", e)

if __name__ == "__main__":
    test_google_sheet_access()