"""SQL used by migrations to make ledger tables append-only."""


def append_only_sql(table: str) -> tuple[str, str]:
    """Return (forward, reverse) SQL installing a trigger that rejects UPDATE
    and DELETE on `table`.

    TRUNCATE is not blocked here because the test runner uses it to reset the
    database between transactional tests. In production, run the application
    as a database role that does not own the tables (see docs/DEPLOYMENT.md),
    so it cannot TRUNCATE or drop the trigger either."""
    fn = f"{table}_append_only"
    forward = f"""
    CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'restrict_violation';
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER {fn}_row BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {fn}();
    """
    reverse = f"""
    DROP TRIGGER IF EXISTS {fn}_row ON {table};
    DROP FUNCTION IF EXISTS {fn}();
    """
    return forward, reverse
