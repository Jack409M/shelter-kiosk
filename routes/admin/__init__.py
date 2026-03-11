from flask import Blueprint

# Admin Blueprint
# All admin routes will register under /admin
admin = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin"
)

# Import route modules so they attach to the blueprint
# Each module will contain @admin.route() endpoints
from . import dashboard
from . import users
from . import audit
from . import system
