#!/usr/bin/env python3
"""
Sync tools, functions, models config and system prompts into an OpenWebUI SQLite DB.
Reads from a JSON state file exported from a reference instance (e.g. docker local).

Usage:
  python3 scripts/sync_owui_state.py --state scripts/owui-state.json --db /path/to/webui.db
"""

import argparse
import json
import sqlite3
import time


def sync(state_path: str, db_path: str):
    with open(state_path) as f:
        state = json.load(f)

    db = sqlite3.connect(db_path)
    now = int(time.time())

    # 1. Tools
    tools = state.get("tools", [])
    for t in tools:
        existing = db.execute("SELECT id FROM tool WHERE id=?", (t["id"],)).fetchone()
        if existing:
            db.execute(
                "UPDATE tool SET name=?, content=?, specs=?, meta=?, valves=?, updated_at=? WHERE id=?",
                (t["name"], t["content"], json.dumps(t["specs"]),
                 json.dumps(t["meta"]), json.dumps(t["valves"]), now, t["id"]),
            )
        else:
            db.execute(
                "INSERT INTO tool (id, user_id, name, content, specs, meta, valves, created_at, updated_at) "
                "VALUES (?, '', ?, ?, ?, ?, ?, ?, ?)",
                (t["id"], t["name"], t["content"], json.dumps(t["specs"]),
                 json.dumps(t["meta"]), json.dumps(t["valves"]), now, now),
            )
    print(f"Synced {len(tools)} tools")

    # 2. Functions (filters)
    functions = state.get("functions", [])
    for f in functions:
        existing = db.execute("SELECT id FROM function WHERE id=?", (f["id"],)).fetchone()
        if existing:
            db.execute(
                "UPDATE function SET name=?, type=?, content=?, meta=?, valves=?, updated_at=? WHERE id=?",
                (f["name"], f["type"], f["content"],
                 json.dumps(f["meta"]), json.dumps(f["valves"]), now, f["id"]),
            )
        else:
            db.execute(
                "INSERT INTO function (id, user_id, name, type, content, meta, valves, is_active, is_global, created_at, updated_at) "
                "VALUES (?, '', ?, ?, ?, ?, ?, 1, 1, ?, ?)",
                (f["id"], f["name"], f["type"], f["content"],
                 json.dumps(f["meta"]), json.dumps(f["valves"]), now, now),
            )
    print(f"Synced {len(functions)} functions")

    # 3. Models (params + meta with toolIds)
    models = state.get("models", [])
    synced = 0
    for m in models:
        meta_str = json.dumps(m["meta"])
        params_str = json.dumps(m["params"])
        existing = db.execute("SELECT id FROM model WHERE id=?", (m["id"],)).fetchone()
        if existing:
            db.execute(
                "UPDATE model SET meta=?, params=?, updated_at=? WHERE id=?",
                (meta_str, params_str, now, m["id"]),
            )
        else:
            db.execute(
                "INSERT INTO model (id, user_id, base_model_id, name, meta, params, is_active, created_at, updated_at) "
                "VALUES (?, '', ?, ?, ?, ?, 1, ?, ?)",
                (m["id"], m["id"], m["id"], meta_str, params_str, now, now),
            )
        synced += 1
    print(f"Synced {synced} models")

    # 4. Config
    config = state.get("config", {})
    for config_id, data in config.items():
        existing = db.execute("SELECT id FROM config WHERE id=?", (config_id,)).fetchone()
        data_str = json.dumps(data)
        if existing:
            db.execute("UPDATE config SET data=? WHERE id=?", (data_str, config_id))
        else:
            db.execute("INSERT INTO config (id, data) VALUES (?, ?)", (config_id, data_str))
    print(f"Synced {len(config)} config entries")

    db.commit()
    db.close()
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, help="Path to JSON state file")
    parser.add_argument("--db", required=True, help="Path to webui.db")
    args = parser.parse_args()
    sync(args.state, args.db)
