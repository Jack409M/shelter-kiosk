# Rent and Resident Portal Boundaries

This document locks the current architecture decisions for the rent system and resident phone home screen.

## Rent tracking blueprint

The rent tracking blueprint is registered in `routes/rent_tracking.py` and is split across four route modules.

| Module | Responsibility |
| --- | --- |
| `routes/rent_tracking_parts/rent_roll.py` | Rent roll overview, monthly rent posting control, posted status display |
| `routes/rent_tracking_parts/views.py` | Shared rent sheet helpers and resident rent setup route |
| `routes/rent_tracking_parts/resident_account.py` | Resident account, manual payment, manual charge, manual credit, ledger, and history routes |
| `routes/rent_tracking_parts/payment_station_views.py` | Standalone payment station workflow |

## Locked rent route ownership

The following ownership is intentional and should be preserved.

| Route | Owner |
| --- | --- |
| `GET /staff/rent/roll` | `rent_roll.py` |
| `POST /staff/rent/roll/generate-monthly-charges` | `rent_roll.py` |
| `GET /staff/rent/resident/<id>/config` | `views.py` |
| `POST /staff/rent/resident/<id>/config` | `views.py` |
| `GET /staff/rent/resident/<id>/account` | `resident_account.py` |
| `POST /staff/rent/resident/<id>/account/post-payment` | `resident_account.py` |
| `POST /staff/rent/resident/<id>/account/post-charge` | `resident_account.py` |
| `POST /staff/rent/resident/<id>/account/post-credit` | `resident_account.py` |
| `GET /staff/rent/resident/<id>/ledger` | `resident_account.py` |
| `GET /staff/rent/resident/<id>/history` | `resident_account.py` |
| `GET, POST /staff/rent/payment-station` | `payment_station_views.py` |

## Locked rent behavior

Opening a resident account must not create monthly rent charges or late fees. Account pages are read plus explicit manual transaction entry only.

Monthly rent posting is an explicit staff action from the rent roll page. The route is a POST action at `/staff/rent/roll/generate-monthly-charges`.

The rent roll page shows the current month posting state. Once rent has been posted for the month, the Generate Monthly Charges button is hidden and the page shows `Rent posted for <Month Year>`.

The backend monthly posting helper remains idempotent. Re-running the posting route should not duplicate the same resident sheet entry ledger source rows.

## Rent data model roles

| Table family | Role |
| --- | --- |
| `resident_rent_configs` | Current and historical rent setup, apartment assignment snapshot, exemption, and Level 8 adjustment values |
| `resident_rent_sheets` and `resident_rent_sheet_entries` | Monthly calculated snapshot and compliance/history source |
| `resident_rent_ledger_entries` | Financial ledger source for charges, payments, credits, balances, and audit trail |

Do not remove the sheet tables. They still support monthly snapshots, history, compliance, and ledger source linkage.

## Resident phone home screen

The resident phone home screen is served by `routes/resident_portal_parts/home.py` and rendered by `templates/resident_home.html`.

For residents below Level 5, the home screen may show Request Transportation.

For residents at Level 5 and higher, the Request Transportation button is hidden and the Daily Log button remains visible.

For residents at Level 5 and higher, the screen shows a small weekly summary line:

`W: <work hours> P: <productive hours> M: <meeting count>`

The weekly summary is best effort and must not break the resident home page if legacy or test databases are missing newer daily log columns.
