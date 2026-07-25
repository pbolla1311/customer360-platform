import sqlite3


from customer360.config import DATABASE_FILE

def get_connection() -> sqlite3.Connection:
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DATABASE_FILE)


def initialize_database() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customer360 (
            customer_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            city TEXT,
            state TEXT,
            signup_date TEXT,
            total_transactions INTEGER,
            total_spend REAL,
            average_transaction_value REAL,
            first_purchase_date TEXT,
            last_purchase_date TEXT,
            customer_segment TEXT
        )
        """
    )

    connection.commit()
    connection.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully.")
