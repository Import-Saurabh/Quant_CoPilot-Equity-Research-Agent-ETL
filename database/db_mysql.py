"""
database/db_mysql.py – MySQL connection (PyMySQL)
Reads credentials from environment variables.
"""
import os
import pymysql

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "ai_hedge_fund")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_SSL = os.getenv("DB_SSL", "false").lower() == "true"

def get_connection():
    connect_args = {
        "host": DB_HOST,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": DB_NAME,
        "port": DB_PORT,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }
    
    # TiDB Serverless and some managed databases require SSL
    if DB_SSL or "tidbcloud" in DB_HOST:
        connect_args["ssl_verify_cert"] = True
        connect_args["ssl_verify_identity"] = True

    conn = pymysql.connect(**connect_args)
    return conn