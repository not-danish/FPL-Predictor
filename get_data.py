import requests
import json
import time

url = "https://www.fpl-data.co.uk/_dash-update-component"

headers = {
    "Content-Type": "application/json"
}

for page in range(42):

    payload = {
        "output": "..stats-data-table.data...stats-data-table.columns...stats-data-table.style_data_conditional...div-price-pos-filt.style...stats-data-table.page_count...div-group-split.style..",
        
        "outputs": [
            {"id": "stats-data-table", "property": "data"},
            {"id": "stats-data-table", "property": "columns"},
            {"id": "stats-data-table", "property": "style_data_conditional"},
            {"id": "div-price-pos-filt", "property": "style"},
            {"id": "stats-data-table", "property": "page_count"},
            {"id": "div-group-split", "property": "style"}
        ],
        
        "inputs": [
            {"id": "input-year", "property": "value", "value": "2025_26"},
            {"id": "input-team-stats", "property": "value", "value": "0"},
            {"id": "input-position-team-stats", "property": "value", "value": [3,5,2,1,4]},
            {"id": "input-price-stats", "property": "value", "value": [0,16]},
            {"id": "input-gamweek-overall", "property": "value", "value": "GROUP"},
            {"id": "input-player-team", "property": "value", "value": "Player"},
            {"id": "input-player-stats", "property": "value", "value": "0"},
            {"id": "input-gameweek-stats", "property": "value", "value": [1,38]},
            {"id": "stats-data-table", "property": "page_current", "value": page},
            {"id": "stats-data-table", "property": "page_size", "value": 20},
            {"id": "stats-data-table", "property": "sort_by", 
             "value": [{"column_id": "xP", "direction": "asc"}]},
            {"id": "input-stat-types", "property": "value",
             "value": ["Info","Shooting","Assisting","Points","Possession"]},
            {"id": "input-homeaway-stats", "property": "value", "value": [True, False]}
        ],

        "changedPropIds": ["stats-data-table.page_current"],
        "parsedChangedPropsIds": ["stats-data-table.page_current"]
    }

    res = requests.post(url, headers=headers, json=payload)

    try:
        full_json = res.json()
    except:
        print(f"Page {page}: Failed response (status {res.status_code})")
        print("Response was:", res.text)
        break

    # Extract ONLY the table rows from the response
    try:
        table_rows = full_json["response"]["stats-data-table"]["data"]
    except KeyError:
        print(f"Page {page}: Missing expected data structure.")
        print(full_json)
        break

    # Save only the data list
    with open(f"data2526_{page+1}.json", "w") as f:
        json.dump(table_rows, f, indent=2)

    print(f"Saved page {page+1} (rows: {len(table_rows)})")
    time.sleep(0.3)

print("done")
