"""Per-file load tracking so re-runs never duplicate data."""


def ensure_schema(con) -> None:
    con.execute("create schema if not exists raw")
    con.execute("create table if not exists raw.load_log"
                "(source varchar, url varchar, rows bigint, loaded_at timestamp)")
    con.execute("create table if not exists raw.load_errors"
                "(source varchar, url varchar, message varchar, failed_at timestamp)")


def already_loaded(con, url: str) -> bool:
    return con.execute("select count(*) from raw.load_log where url = ?", [url]).fetchone()[0] > 0


def mark_loaded(con, source: str, url: str, rows: int) -> None:
    con.execute("insert into raw.load_log values (?, ?, ?, now())", [source, url, rows])


def record_error(con, source: str, url: str, message: str) -> None:
    con.execute("insert into raw.load_errors values (?, ?, ?, now())", [source, url, message[:2000]])


def append(con, table: str, df) -> int:
    """Append a DataFrame by column name, creating the table or new VARCHAR columns as needed."""
    if df.empty:
        return 0
    con.register("_incoming", df)
    try:
        con.execute(f"create table if not exists {table} as select * from _incoming limit 0")
        schema, name = table.split(".")
        existing = {r[0] for r in con.execute(
            "select column_name from information_schema.columns "
            "where table_schema = ? and table_name = ?", [schema, name]).fetchall()}
        for col in df.columns:
            if col not in existing:
                con.execute(f'alter table {table} add column "{col}" varchar')
        con.execute(f"insert into {table} by name select * from _incoming")
    finally:
        con.unregister("_incoming")
    return len(df)
