import os
import re
from database.db_mysql import get_connection

def _clean_sql(sql: str) -> str:
    # remove block comments /* ... */
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    # remove line comments starting with --
    sql = re.sub(r"--.*?$", "", sql, flags=re.M)
    return sql

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "mysql_schema_v2.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = _clean_sql(f.read())

    conn = get_connection()
    cursor = conn.cursor()

    for statement in sql.split(";"):
        stmt = statement.strip()
        if stmt:
            cursor.execute(stmt)

    conn.commit()
    cursor.close()
    conn.close()
    print("  ok  MySQL DB initialised (schema from schema.sql)")

if __name__ == "__main__":
    init_db()