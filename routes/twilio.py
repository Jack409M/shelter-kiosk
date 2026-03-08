from flask import Blueprint, request, abort, current_app
from flask import Response
from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso
from flask import g
import os

from twilio.request_validator import RequestValidator

from app import (
    TWILIO_INBOUND_ENABLED,
    TWILIO_STATUS_ENABLED,
    TWILIO_AUTH_TOKEN,
    _client_ip,
    _rate_limited,
    init_db
)

twilio = Blueprint("twilio", __name__)
