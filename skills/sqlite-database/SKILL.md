---
name: sqlite-database
description: Design schemas and write safe SQL, especially SQLite for local apps. Use for databases, queries and data storage.
triggers: sql, sqlite, database, query
---
# SQLite / SQL
- SQLite is built into Python (`sqlite3`) and fits most phone/local apps: single file, no server.
- Schema: primary key on every table, `NOT NULL` and `UNIQUE` where valid, foreign keys (`PRAGMA foreign_keys = ON`), `created_at` timestamps.
- ALWAYS use parameterized queries (`cur.execute("... WHERE id = ?", (id,))`); never format user input into SQL.
- Index columns used in WHERE/JOIN; check with `EXPLAIN QUERY PLAN`.
- Wrap multi-step writes in a transaction; use migrations (a `schema_version` table) when the schema changes.
- Back up the .db file before destructive changes.
