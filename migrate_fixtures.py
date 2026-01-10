import argparse
import json
import logging
import sys

import pandas as pd
from sqlalchemy import create_engine, MetaData, TIMESTAMP, DateTime, Date

from postgresql_upsert import upsert_dataframe


def transform_fixture_to_df(json_group, table_obj):
    """
    Transforms a list of Django JSON records into a clean DataFrame
    ready for SQL insertion.
    """
    # 1. Determine Primary Key Name dynamically from the DB schema
    pk_cols = [c.name for c in table_obj.primary_key.columns]
    target_pk_name = pk_cols[0] if pk_cols else 'id'

    # Get valid column names from the actual DB table
    valid_columns = set(c.name for c in table_obj.columns)

    # 2. Flatten JSON Structure & Handle FK Renaming
    rows = []
    for entry in json_group:
        # Get raw fields from JSON
        raw_fields = entry.get('fields', {})
        cleaned_row = {}

        # Handle specific PK naming (Django fixture 'pk' -> DB PK column)
        if 'pk' in entry:
            cleaned_row[target_pk_name] = entry['pk']

        # Map JSON fields to DB columns
        for field_name, value in raw_fields.items():
            if field_name in valid_columns:
                # Direct match (e.g., "username" -> "username")
                cleaned_row[field_name] = value
            elif f"{field_name}_id" in valid_columns:
                # FK match (e.g., "meter" -> "meter_id")
                cleaned_row[f"{field_name}_id"] = value
            # else: Field exists in JSON but not in DB (e.g. ManyToMany list), ignore it.

        rows.append(cleaned_row)

    if not rows:
        return pd.DataFrame(), pk_cols

    df = pd.DataFrame(rows)

    # 3. Clean Data: Ensure only valid columns remain (double check)
    # This creates the intersection of columns found in JSON and DB
    cols_to_keep = [c for c in df.columns if c in valid_columns]
    df = df[cols_to_keep]

    # 4. Clean Data: Handle Dates
    # Convert ISO 8601 strings to Python datetime objects for SQLAlchemy
    for col in table_obj.columns:
        if col.name in df.columns and isinstance(col.type, (TIMESTAMP, DateTime, Date)):
            # Force conversion using pandas, handling timezone "Z" automatically
            df[col.name] = pd.to_datetime(df[col.name], format='ISO8601', errors='coerce')

    return df, pk_cols


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    stream=sys.stdout,
)
parser = argparse.ArgumentParser()
parser.add_argument("-I", "--input", required=True,
                    help="File path of *.json fixtures.")
cmd, _ = parser.parse_known_args()

logging.info(f"Connecting to database...")
with open("token.json", "r") as f:
    tokens = json.load(f)
assert tokens.get("neon_db"), "Database connection string is not provided."
engine = create_engine(tokens.get("neon_db"))

# Reflect DB schema to understand tables and FK dependencies
metadata = MetaData()
metadata.reflect(bind=engine)

logging.info(f"Loading fixture data from {cmd.input}...")
with open(cmd.input, 'r', encoding='utf-8') as f:
    raw_data = json.load(f)

# Group fixture data by Model
# Normalize keys: "auth.user" -> "auth_user"
grouped_data = {}
for entry in raw_data:
    # Heuristic: Django tables are usually app_model (lowercase)
    # We convert 'App.Model' -> 'app_model'
    normalized_model = entry['model'].replace('.', '_').lower()

    if normalized_model not in grouped_data:
        grouped_data[normalized_model] = []
    grouped_data[normalized_model].append(entry)

logging.info("Starting Bulk Upsert...")

# Iterate over tables in dependency order (parents before children)
# metadata.sorted_tables relies on Foreign Keys to sort correctly
processed_count = 0
for table in metadata.sorted_tables:
    table_name = table.name.lower()

    if table_name in grouped_data:
        records = grouped_data[table_name]
        count = len(records)

        # Transform JSON -> Validated DataFrame
        df, pk_cols = transform_fixture_to_df(records, table)

        if not df.empty:
            logging.info(f"Upserting {count} rows into '{table.name}'...")
            upsert_dataframe(engine, df, pk_cols, table.name)
            processed_count += 1
        else:
            logging.warning(f"Skipping '{table.name}': Data empty after cleaning.")

if processed_count == 0:
    logging.warning("No data was inserted.\n"
                    "This usually means the 'model' names in your JSON do not match your "
                    "Postgres table names.\n"
                    f"Example expected table name: "
                    f"{list(grouped_data.keys())[0] if grouped_data else 'unknown'}")
