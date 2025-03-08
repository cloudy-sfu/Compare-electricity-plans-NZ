import sqlite3
import pandas as pd

# %% Get data.
c = sqlite3.connect("contact_energy.db")
meters = pd.read_sql_query("select ROWID, * from meter", c)
usage = pd.read_sql_query("select * from usage", c)
c.close()

# %%
pd.to_datetime(usage[['year', 'month', 'day', 'hour']])

# %%
meters_id_map = {}
for _, row in meters.iterrows():
    print(row['rowid'], row['account_number'], row['contract_id'])
