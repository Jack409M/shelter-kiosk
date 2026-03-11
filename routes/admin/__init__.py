from flask import Blueprint

admin = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin"
)

# Temporary bridge to the old monolith file
# This keeps the app working while we move routes out piece by piece
try:
    from .. import admin as legacy_admin
except Exception:
    legacy_admin = None

# Future route modules
from . import dashboard
from . import users
from . import audit
from . import system
