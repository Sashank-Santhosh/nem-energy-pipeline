"""Tables the forecast jobs write (schema `forecasts`)."""


def ensure_tables(con) -> None:
    con.execute("create schema if not exists forecasts")
    con.execute("create table if not exists forecasts.daily (regionid varchar, issue_time timestamp,"
                " target_time timestamp, model_mw double, naive_mw double, created_at timestamp)")
    con.execute("create table if not exists forecasts.backtest (regionid varchar,"
                " issue_time timestamp, target_time timestamp, actual_mw double, model_mw double,"
                " naive_mw double, aemo_mw double)")
    con.execute("create table if not exists forecasts.backtest_meta (optimistic boolean,"
                " run_at timestamp, months integer)")
