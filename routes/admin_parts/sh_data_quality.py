from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from routes.admin_parts.helpers import require_admin_role
from routes.case_management_parts.helpers import placeholder

_ACTIVE_RESIDENT_SQL = """
COALESCE(LOWER(TRIM(CAST(is_active AS TEXT))), '') IN ('1','true','t','yes')
"""

_UNCONFIRMED_DUPLICATE_NAME_SQL = """
NOT EXISTS (
 SELECT 1 FROM duplicate_name_reviews dnr
 WHERE dnr.first_name_key = LOWER(TRIM(first_name))
 AND dnr.last_name_key = LOWER(TRIM(last_name))
 AND dnr.status = 'verified_separate_people'
)
"""


def _count(sql, params=()):
 row = db_fetchone(sql, params) or {}
 return int(row.get("count") or 0)


def _rows(sql, params=()):
 return db_fetchall(sql, params) or []


def _duplicate_names_issue():
 where = f"{_ACTIVE_RESIDENT_SQL} AND {_UNCONFIRMED_DUPLICATE_NAME_SQL}"

 count = _count(
  f"""
  SELECT COUNT(*) AS count FROM (
   SELECT LOWER(TRIM(first_name)), LOWER(TRIM(last_name))
   FROM residents WHERE {where}
   GROUP BY 1,2 HAVING COUNT(*) > 1
  ) t
  """
 )

 rows = _rows(
  f"""
  SELECT MIN(id) AS id,
         LOWER(TRIM(first_name)) AS first_name,
         LOWER(TRIM(last_name)) AS last_name,
         COUNT(*) AS duplicate_count
  FROM residents
  WHERE {where}
  GROUP BY 1,2
  HAVING COUNT(*) > 1
  ORDER BY duplicate_count DESC
  LIMIT 25
  """
 )

 for r in rows:
  fn = quote(r["first_name"], safe="")
  ln = quote(r["last_name"], safe="")
  r["action_url"] = f"/staff/admin/system-health/data-quality/duplicates/{fn}/{ln}"
  r["action_label"] = "Review duplicate group"

 return {
  "key": "duplicate_active_names",
  "label": "Duplicate active resident names",
  "description": "Residents with same name",
  "severity": "warn",
  "count": count,
  "rows": rows,
  "fix_note": "Review group then decide same or not",
 }


def system_health_data_quality_view():
 if not require_admin_role():
  return redirect(url_for("attendance.staff_attendance"))

 issues = [_duplicate_names_issue()]

 return render_template(
  "sh_data_quality.html",
  title="Data Quality",
  issues=issues,
  total_issues=sum(i["count"] for i in issues),
  error_count=0,
  warning_count=sum(i["count"] for i in issues),
 )
