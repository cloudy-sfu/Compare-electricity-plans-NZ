from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import insert


def upsert_dataframe(engine, df, unique_key_columns, table_name, schema="public"):
    """
    Performs a bulk INSERT OR UPDATE of a pandas DataFrame to a Postgresql table.
    This function inserts rows from the DataFrame. If a row violates a unique
    constraint (specified by `unique_key_columns`), it updates the
    existing row with the new values from the DataFrame instead.
    """
    metadata = MetaData()
    metadata.reflect(bind=engine, schema=schema)
    table = metadata.tables[f"{schema}.{table_name}"]
    if df.empty: return
    # Convert DataFrame to a list of dictionaries for SQLAlchemy
    data_to_insert = df.to_dict(orient='records')
    # The initial INSERT statement
    stmt = insert(table).values(data_to_insert)
    # Dynamically create the 'set_' dictionary for the ON CONFLICT clause.
    # This dictionary maps columns to be updated to the new values from
    # the incoming data (referred to by 'stmt.excluded').
    # We update all columns that are NOT part of the unique key.
    update_cols = {
        col.name: col
        for col in stmt.excluded
        if col.name not in unique_key_columns
    }
    # Construct the final UPSERT statement with the ON CONFLICT clause
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=unique_key_columns,
        set_=update_cols
    )
    # Execute the statement within a transaction
    with engine.begin() as conn:
        conn.execute(upsert_stmt)
