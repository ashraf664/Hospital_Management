# Database migrations

`schema.sql` is the version 2 baseline schema and is applied transactionally to
new databases. `DatabaseInitializer` records the applied version in SQLite's
`user_version` pragma.

Future schema changes belong in numbered SQL files named
`NNNN_short_description.sql`, starting at version `0003`. Existing version 1
databases are upgraded by `0002_protect_core_rows_and_validate_emergency_timestamps.sql`.
Each migration is
applied in version order inside a transaction; version numbers must be
contiguous. Do not edit the baseline schema to represent changes to an already
initialized database.
