import sqlite3

from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="Customer360 API",
    version="1.0.0",
)

DATABASE = "customer360.db"


@app.get("/")
def root():
    return {
        "application": "Customer360 Platform",
        "status": "running",
    }


@app.get("/customers")
def get_customers():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    rows = connection.execute(
        """
        SELECT *
        FROM customer360
        ORDER BY total_spend DESC
        """
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


@app.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    row = connection.execute(
        """
        SELECT *
        FROM customer360
        WHERE customer_id = ?
        """,
        (customer_id,),
    ).fetchone()

    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    return dict(row)
