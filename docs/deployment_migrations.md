mkdir -p docs

cat > docs/deployment_migrations.md <<'MD'
# Deployment Migration Rules

## Required environment variable

AUTO_APPLY_MIGRATIONS

## Values

1 = app applies migrations automatically at startup  
0 = app refuses to start if schema is behind  

## Development

Set:

AUTO_APPLY_MIGRATIONS=1

## Production (recommended)

Set:

AUTO_APPLY_MIGRATIONS=0

Then run:

python scripts/apply_migrations.py

Then start app.

## Failure behavior

If AUTO_APPLY_MIGRATIONS=0 and schema is behind:

- app will not start
- error will be logged
- deployment fails safely

## Rule

Never deploy code that requires new schema without either:

1. running migrations first  
or  
2. enabling AUTO_APPLY_MIGRATIONS temporarily  

## Safe sequence

1. deploy code  
2. run migrations  
3. verify  
4. switch AUTO_APPLY_MIGRATIONS back to 0  

MD
