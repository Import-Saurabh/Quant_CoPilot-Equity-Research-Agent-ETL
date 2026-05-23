"""
database/db_mysql.py – MySQL connection (PyMySQL)
Reads credentials from environment variables.
"""
import os
import pymysql

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Avinash18")
DB_NAME = os.getenv("DB_NAME", "ai_hedge_fund")
DB_PORT = int(os.getenv("DB_PORT", "3306"))

def get_connection():
    conn = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,   # optional: returns rows as dict
        autocommit=False,
    )
    return conn