import sqlite3

class DatabaseManager:
    def __init__(self, db_name):
        self.db_name = db_name

    def save_to_sqlite(self, trades):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                side TEXT,
                quantity REAL,
                price REAL,
                quoteQty REAL,
                time INTEGER
            )
        ''')

        for trade in trades:
            cursor.execute('''
                INSERT INTO trades (symbol, side, quantity, price, quoteQty, time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (trade['symbol'], trade['side'], trade['qty'], trade['price'], trade['quoteQty'], trade['time']))

        conn.commit()
        conn.close()

    def create_aggregated_view(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE VIEW IF NOT EXISTS aggregated_results AS
            SELECT 
                symbol,
                SUM(CASE WHEN side = 'BUY' THEN price * quantity ELSE -price * quantity END) AS total_result,
                COUNT(CASE WHEN side = 'BUY' THEN 1 ELSE NULL END) AS total_buys,
                SUM(quantity) / COUNT(*) AS avg_quantity,
                AVG(price) AS avg_price
            FROM trades
            GROUP BY symbol
            ORDER BY total_result DESC
        ''')
        conn.commit()
        conn.close()
