# Database Migration Workflow

This project is moving from startup schema repair only toward explicit tracked database migrations.

## Current model

Right now the app uses both systems together.

Startup flow is:

1. connect to database
2. apply pending tracked migrations
3. run legacy schema initialization as temporary compatibility glue
4. continue app startup

This bridge approach is intentional.

It lets us introduce real migration tracking without breaking the current schema safety net.

## Migration files

Tracked migrations live in:

`db/migrations/`

Each migration file must define:

- `VERSION`
- `NAME`
- `apply(kind)`

Example shape:

```python
VERSION = 2
NAME = "add_example_table"

def apply(kind: str) -> None:
    ...
