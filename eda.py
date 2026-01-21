import pandas as pd
import numpy as np
import glob
import json


files = glob.glob("data/*.json")   # adjust as needed

dfs = []

for f in files:
    with open(f, "r") as fp:
        obj = json.load(fp)
        df = pd.DataFrame(obj["data"])   # only the "data" list
        dfs.append(df)

# Combine all pages into one DataFrame
full_df = pd.concat(dfs, ignore_index=True)

print(full_df.head())
print(full_df.shape)

