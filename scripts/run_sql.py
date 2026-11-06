"""Run a .sql file with DuckDB from the repo root and print the result."""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    q = Path(sys.argv[1]).read_text()
    con = duckdb.connect()
    con.execute(f"SET file_search_path='{ROOT}'")
    print(con.sql(q).df().to_string(index=False))
