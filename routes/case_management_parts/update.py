
{% extends "layout.html" %}

{% block content %}

{% set resident_id = resident["id"] %}
{% set first_name = resident["first_name"] %}
{% set last_name = resident["last_name"] %}
{% set resident_code = resident["resident_code"] %}
{% set shelter = resident["shelter"] %}
{% set resident_active = resident["is_active"] %}

{% if enrollment %}
  {% set enrollment_program_status = enrollment["program_status"] %}
  {% set enrollment_entry_date = enrollment["entry_date"] %}
  {% set enrollment_exit_date = enrollment["exit_date"] %}
{% else %}
  {% set enrollment_program_status = "" %}
  {% set enrollment_entry_date = "" %}
  {% set enrollment_exit_date = "" %}
{% endif %}

{% set intake_grit_score = intake_assessment["grit_score"] if intake_assessment else none %}

{% if exit_assessment %}
  {% set exit_date_graduated = exit_assessment["date_graduated"] %}
  {% set exit_date_exit_dwc = exit_assessment["date_exit_dwc"] %}
  {% set exit_category = exit_assessment["exit_category"] %}
  {% set exit_reason = exit_assessment["exit_reason"] %}
  {% set exit_graduate_dwc = exit_assessment["graduate_dwc"] %}
  {% set exit_leave_ama = exit_assessment["leave_ama"] %}
  {% set exit_leave_ama_destination = exit_assessment["leave_ama_destination"] %}
  {% set exit_income_at_exit = exit_assessment["income_at_exit"] %}
  {% set exit_education_at_exit = exit_assessment["education_at_exit"] %}
{% else %}
  {% set exit_date_graduated = none %}
  {% set exit_date_exit_dwc = none %}
  {% set exit_category = none %}
  {% set exit_reason = none %}
  {% set exit_graduate_dwc = none %}
  {% set exit_leave_ama = none %}
  {% set exit_leave_ama_destination = none %}
  {% set exit_income_at_exit = none %}
  {% set exit_education_at_exit = none %}
{% endif %}

<h1>Case Management</h1>

<div style="display:grid; grid-template-columns:repeat(2, minmax(280px, 1fr)); gap:12px;" class="case-header-strip">
  <div class="card case-header-print">
    <h2>{{ first_name }} {{ last_name }}</h2>

    <p>
      <strong>Resident Code:</strong> {{ resident_code or "—" }}<br>
      <strong>Shelter:</strong> {{ shelter | shelter if shelter else "—" }}<br>
      <strong>Status:</strong> {{ "Active" if resident_active else "Inactive" }}
    </p>

    <a class="btn no-print" href="{{ url_for('case_management.index') }}">
      Back to Case List
    </a>

    <a class="btn no-print" href="{{ url_for('case_management.intake_edit', resident_id=resident_id) }}">
      Edit Intake
    </a>
  </div>

  <div class="card case-header-print">
    <h2>Program Information</h2>

    <p>
      <strong>Program Status:</strong> {{ enrollment_program_status|replace("_", " ")|title if enrollment_program_status else "Not enrolled" }}<br>
      <strong>Enrollment ID:</strong> {{ enrollment_id or "—" }}<br>
      <strong>Entry Date:</strong> {{ enrollment_entry_date or "—" }}<br>
      <strong>Exit Date:</strong> {{ enrollment_exit_date or "—" }}
    </p>
  </div>
</div>

{% if not enrollment_id %}
  <div class="card no-print">
    <h2>Start Program Enrollment</h2>

    <form method="post" action="{{ url_for('case_management.create_enrollment', resident_id=resident_id) }}">
      <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">

      <label><strong>Program Entry Date</strong></label>
      <input type="date" name="entry_date" required>

      <div style="margin-top:10px;">
        <button type="submit">Start Enrollment</button>
      </div>
    </form>
  </div>
{% else %}

  <style>
    .case-note-tile.is-active {
      border-color: #555 !important;
      box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.08);
    }

    .print-only-note {
      display: none;
    }

    .case-note-text-block {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
    }

    .notebook-tabs {
      display: flex;
      gap: 8px;
      margin: 12px 0;
      flex-wrap: wrap;
    }

    .notebook-tab-btn {
      background: #f3f4f6 !important;
      color: #111111 !important;
      border: 1px solid #d1d5db !important;
    }

    .notebook-tab-btn:visited,
    .notebook-tab-btn:hover,
    .notebook-tab-btn:focus,
    .notebook-tab-btn:active {
      color: #111111 !important;
    }

    .notebook-tab-btn.is-active,
    .notebook-tab-btn.is-active:visited,
    .notebook-tab-btn.is-active:hover,
    .notebook-tab-btn.is-active:focus,
    .notebook-tab-btn.is-active:active {
      background: #1e3a8a !important;
      color: #ffffff !important;
      border-color: #1e3a8a !important;
      box-shadow: 0 0 0 2px rgba(30, 58, 138, 0.25) !important;
      font-weight: 700 !important;
      -webkit-text-fill-color: #ffffff !important;
    }

    button.notebook-tab-btn.is-active,
    button.notebook-tab-btn.is-active span {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }

    .needs-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
      margin-top: 10px;
    }

    .need-card {
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 12px;
      background: #fafafa;
    }

    @media print {
      body {
        background: #fff !important;
      }

      .no-print,
      .notebook-tabs,
      #case-note-scroll-lane,
      .case-note-tile,
      .print-hide,
      h1,
      .case-note-panel,
      .progress-notes-heading,
      .progress-notes-empty {
        display: none !important;
      }

      .case-header-strip {
        display: grid !important;
        grid-template-columns: 1fr 1fr !important;
        gap: 8px !important;
        margin-bottom: 6px !important;
      }

      .case-header-print {
        display: block !important;
        border: 1px solid #ccc !important;
        padding: 8px !important;
        box-shadow: none !important;
      }

      .case-header-print h2 {
        margin: 0 0 4px 0 !important;
        font-size: 1.05em !important;
      }

      .case-header-print p {
        margin: 0 !important;
        line-height: 1.2 !important;
        font-size: 0.92em !important;
      }

      .print-only-note {
        display: block !important;
        margin-top: 6px !important;
      }

      .print-only-note .card {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        box-shadow: none !important;
      }

      .case-note-text-block {
        white-space: pre-wrap !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
      }
    }
  </style>

  <div class="notebook-tabs no-print">
    <button
      type="button"
      class="btn notebook-tab-btn is-active"
      data-tab-target="resident-file-tab"
      onclick="showResidentNotebookTab('resident-file-tab', this)"
    >
      Resident File
    </button>
    <button
      type="button"
      class="btn notebook-tab-btn"
      data-tab-target="children-tab"
      onclick="showResidentNotebookTab('children-tab', this)"
    >
      Children
    </button>
    <button
      type="button"
      class="btn notebook-tab-btn"
      data-tab-target="progress-notes-tab"
      onclick="showResidentNotebookTab('progress-notes-tab', this)"
    >
      Progress Notes
    </button>
  </div>

  <div id="resident-file-tab" class="resident-notebook-tab">
    <div class="card no-print">
      <h2>Monthly Case Manager Meeting</h2>

      <form method="post" action="{{ url_for('case_management.add_case_note', resident_id=resident_id) }}">
        <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">

        <label><strong>Meeting Date</strong></label>
        <input type="date" name="meeting_date" required>

        <h3 style="margin-top:16px;">Open Needs</h3>

        {% if open_needs %}
          <div class="needs-grid">
            {% for need in open_needs %}
              {% set need_key = need["need_key"] %}
              {% set need_label = need["need_label"] %}
              {% set source_value = need["source_value"] %}
              <div class="need-card">
                <div><strong>{{ need_label }}</strong></div>
                {% if source_value %}
                  <div style="margin-top:4px; font-size:0.9em; color:#666;">
                    Intake trigger: {{ source_value }}
                  </div>
                {% endif %}

                <label style="margin-top:10px;"><strong>Status</strong></label>
                <select name="need_status_{{ need_key }}">
                  <option value="">Leave Open</option>
                  <option value="addressed">Addressed</option>
                  <option value="not_applicable">Not Applicable</option>
                </select>

                <label style="margin-top:10px;"><strong>Resolution Note</strong></label>
                <textarea
                  name="need_note_{{ need_key }}"
                  rows="2"
                  placeholder="Optional note about this need"
                ></textarea>
              </div>
            {% endfor %}
          </div>
        {% else %}
          <p style="margin-top:8px; color:#666;">No open intake driven needs.</p>
        {% endif %}

        <label><strong>Notes</strong></label>
        <textarea name="notes" rows="3"></textarea>

        <label><strong>Progress Notes</strong></label>
        <textarea name="progress_notes" rows="3"></textarea>

        <label><strong>Action Items</strong></label>
        <textarea name="action_items" rows="3"></textarea>

        <label><strong>Updated Grit</strong></label>
        <input type="number" name="updated_grit" min="0" max="100" style="width:70px;" inputmode="numeric">

        <label><strong>Parenting Class Completed</strong></label>
        <label style="display:flex; gap:10px; margin-top:4px;">
          <input type="radio" name="parenting_class_completed" value="yes"> Yes
          <input type="radio" name="parenting_class_completed" value="no"> No
        </label>

        <label><strong>Warrants or Fines Paid</strong></label>
        <label style="display:flex; gap:10px; margin-top:4px;">
          <input type="radio" name="warrants_or_fines_paid" value="yes"> Yes
          <input type="radio" name="warrants_or_fines_paid" value="no"> No
        </label>

        <hr>

        <h3>Services Provided</h3>

        <div style="display:grid; grid-template-columns:repeat(4, minmax(160px, 1fr)); gap:10px; align-items:start; margin-top:10px;">
          <div>
            <label style="display:flex; gap:6px; margin:0;">
              <input type="checkbox" name="service_type" value="Counseling" style="margin-top:3px;">
              <span>Counseling</span>
            </label>
            <textarea
              name="service_notes_Counseling"
              rows="2"
              style="width:100%; margin-top:4px; white-space:pre-wrap; overflow-wrap:break-word;"
              placeholder="Counseling notes"
            ></textarea>
          </div>

          <div>
            <label style="display:flex; gap:6px; margin:0;">
              <input type="checkbox" name="service_type" value="Dental" style="margin-top:3px;">
              <span>Dental</span>
            </label>
            <textarea
              name="service_notes_Dental"
              rows="2"
              style="width:100%; margin-top:4px; white-space:pre-wrap; overflow-wrap:break-word;"
              placeholder="Dental notes"
            ></textarea>
          </div>

          <div>
            <label style="display:flex; gap:6px; margin:0;">
              <input type="checkbox" name="service_type" value="Vision" style="margin-top:3px;">
              <span>Vision</span>
            </label>
            <textarea
              name="service_notes_Vision"
              rows="2"
              style="width:100%; margin-top:4px; white-space:pre-wrap; overflow-wrap:break-word;"
              placeholder="Vision notes"
            ></textarea>
          </div>

          <div>
            <label style="display:flex; gap:6px; margin:0;">
              <input type="checkbox" name="service_type" value="Parenting Support" style="margin-top:3px;">
              <span>Parenting Support</span>
            </label>
            <textarea
              name="service_notes_Parenting Support"
              rows="2"
              style="width:100%; margin-top:4px; white-space:pre-wrap; overflow-wrap:break-word;"
              placeholder="Parenting support notes"
            ></textarea>
          </div>

          <div>
            <label style="display:flex; gap:6px; margin:0;">
              <input type="checkbox" name="service_type" value="Legal Assistance" style="margin-top:3px;">
              <span>Legal Assistance</span>
            </label>
            <textarea
              name="service_notes_Legal Assistance"
              rows="2"
              style="width:100%; margin-top:4px; white-space:pre-wrap; overflow-wrap:break-word;"
              placeholder="Legal assistance notes"
            ></textarea>
          </div>

          <div>
            <label style="display:flex; gap:6px; margin:0;">
              <input type="checkbox" name="service_type" value="Transportation" style="margin-top:3px;">
              <span>Transportation</span>
            </label>
            <textarea
              name="service_notes_Transportation"
              rows="2"
              style="width:100%; margin-top:4px; white-space:pre-wrap; overflow-wrap:break-word;"
              placeholder="Transportation notes"
            ></textarea>
          </div>

          <div>
            <label style="display:flex; gap:6px; margin:0;">
              <input type="checkbox" name="service_type" value="Other" style="margin-top:3px;">
              <span>Other</span>
            </label>
            <textarea
              name="service_notes_Other"
              rows="2"
              style="width:100%; margin-top:4px; white-space:pre-wrap; overflow-wrap:break-word;"
              placeholder="Other service notes"
            ></textarea>
          </div>
        </div>

        <div style="margin-top:10px;">
          <button type="submit">Save Monthly Update</button>
        </div>
      </form>
    </div>

    <div class="card no-print">
      <h2>Follow Up</h2>

      <p>
        <a class="btn" href="{{ url_for('case_management.followup_form', resident_id=resident_id, followup_type='6_month') }}">
          6 Month Follow Up
        </a>

        <a class="btn" href="{{ url_for('case_management.followup_form', resident_id=resident_id, followup_type='1_year') }}">
          1 Year Follow Up
        </a>
      </p>

      <hr>

      <h3>6 Month</h3>
      {% if followup_6_month %}
        <p>
          <strong>Date:</strong> {{ followup_6_month.followup_date or "—" }}<br>
          <strong>Income:</strong> {{ followup_6_month.income_at_followup if followup_6_month.income_at_followup is not none else "—" }}<br>
          <strong>Sober:</strong>
          {% if followup_6_month.sober_at_followup is none %}
            —
          {% else %}
            {{ "Yes" if followup_6_month.sober_at_followup else "No" }}
          {% endif %}
        </p>
      {% else %}
        <p>No 6 month follow up recorded.</p>
      {% endif %}

      <h3>1 Year</h3>
      {% if followup_1_year %}
        <p>
          <strong>Date:</strong> {{ followup_1_year.followup_date or "—" }}<br>
          <strong>Income:</strong> {{ followup_1_year.income_at_followup if followup_1_year.income_at_followup is not none else "—" }}<br>
          <strong>Sober:</strong>
          {% if followup_1_year.sober_at_followup is none %}
            —
          {% else %}
            {{ "Yes" if followup_1_year.sober_at_followup else "No" }}
          {% endif %}
        </p>
      {% else %}
        <p>No 1 year follow up recorded.</p>
      {% endif %}
    </div>

    <div class="card no-print">
      <h2>Exit Assessment</h2>

      <a class="btn" href="{{ url_for('case_management.exit_assessment', resident_id=resident_id) }}">
        {% if enrollment_exit_date %}
          View or Edit Exit Assessment
        {% else %}
          Complete Exit Assessment
        {% endif %}
      </a>
    </div>

    {% if exit_assessment %}
      <div class="card no-print">
        <h2>Exit Summary</h2>

        <p>
          <strong>Exit Category:</strong> {{ exit_category or "—" }}<br>
          <strong>Exit Reason:</strong> {{ exit_reason or "—" }}<br>
          <strong>Date Exit:</strong> {{ exit_date_exit_dwc or "—" }}<br>
          <strong>Monthly Income at Exit:</strong> {{ exit_income_at_exit if exit_income_at_exit is not none else "—" }}<br>
          <strong>Education at Exit:</strong> {{ exit_education_at_exit or "—" }}<br>

          <strong>Leave Amarillo:</strong>
          {% if exit_leave_ama is none %}
            —
          {% else %}
            {{ "Yes" if exit_leave_ama else "No" }}
          {% endif %}

          {% if exit_leave_ama %}
            <br>
            <strong>Destination City:</strong>
            {{ exit_leave_ama_destination or "Unknown" }}
          {% endif %}
        </p>
      </div>
    {% endif %}
  </div>

  <div id="children-tab" class="resident-notebook-tab" style="display:none;">
    <div class="card no-print">
      <h2>Family</h2>

      {% if children is defined and children %}
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Birth Year</th>
              <th>Relationship</th>
              <th>Living Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {% for child in children %}
              {% set child_name = child["child_name"] %}
              {% set child_birth_year = child["birth_year"] %}
              {% set child_relationship = child["relationship"] %}
              {% set child_living_status = child["living_status"] %}
              {% set child_id = child["id"] %}
              <tr>
                <td>{{ child_name or "—" }}</td>
                <td>{{ child_birth_year or "—" }}</td>
                <td>{{ child.relationship_display or "—" }}</td>
                <td>{{ child.living_status_display or "—" }}</td>
                <td>
                  <a class="btn btn-sm" href="{{ url_for('case_management.child_services', child_id=child_id) }}">
                    Services
                  </a>
                </td>
              </tr>
              <tr>
                <td colspan="5">
                  {% if child.services %}
                    <div style="font-size:0.9em; color:#555;">
                      {% for s in child.services %}
                        <div>
                          <strong>{{ s.service_date_display }}</strong> —
                          {{ s.service_type_display }}
                          {% if s.quantity_display and s.quantity_display != "—" %}
                            ({{ s.quantity_display }})
                          {% endif %}
                          {% if s.outcome_display and s.outcome_display != "—" %}
                            — {{ s.outcome_display }}
                          {% endif %}
                          {% if s.notes %}
                            <div style="margin-left:10px; color:#555;">
                              {{ s.notes }}
                            </div>
                          {% endif %}
                        </div>
                      {% endfor %}
                    </div>
                  {% else %}
                    <div style="font-size:0.9em; color:#999;">
                      No services recorded
                    </div>
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      {% else %}
        <p>No children recorded.</p>
      {% endif %}
    </div>
  </div>

  <div id="progress-notes-tab" class="resident-notebook-tab" style="display:none;">
    <h2 class="progress-notes-heading">Progress Notes</h2>

    {% if notes %}
      <div
        id="case-note-scroll-lane"
        class="no-print"
        style="display:flex; gap:10px; overflow-x:auto; padding:4px 2px 10px 2px; scroll-behavior:smooth;"
      >
        {% for note in notes %}
          {% set note_id = note["id"] %}
          {% set note_meeting_date = note["meeting_date"] %}
          {% set note_services = note["services"] %}

          <button
            type="button"
            class="case-note-tile"
            data-note-target="case-note-panel-{{ note_id }}"
            data-print-target="print-case-note-{{ note_id }}"
            style="flex:0 0 15.5%; min-width:170px; max-width:220px; border:1px solid #ddd; border-radius:8px; background:#fff; padding:10px; cursor:pointer; text-align:center;"
          >
            <div><strong>{{ note_meeting_date or "—" }}</strong></div>
            {% if note_services %}
              <div style="margin-top:4px; font-size:0.82em; color:#666;">
                {{ note_services|length }} svc
              </div>
            {% endif %}
          </button>
        {% endfor %}
      </div>

      <div class="print-note-panel">
        {% for note in notes %}
          {% set note_id = note["id"] %}
          {% set note_meeting_date = note["meeting_date"] %}
          {% set note_notes = note["notes"] %}
          {% set note_progress_notes = note["progress_notes"] %}
          {% set note_action_items = note["action_items"] %}
          {% set note_updated_grit = note["updated_grit"] %}
          {% set note_parenting_class_completed = note["parenting_class_completed"] %}
          {% set note_warrants_or_fines_paid = note["warrants_or_fines_paid"] %}
          {% set note_created_at = note["created_at"] %}
          {% set note_services = note["services"] %}

          <div
            id="case-note-panel-{{ note_id }}"
            class="card case-note-panel"
            style="display:none; margin-top:10px;"
          >
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
              <div>
                <h3 style="margin-bottom:6px;">Progress Notes {{ note_meeting_date or "—" }}</h3>
                <div style="font-size:0.95em; color:#666;">
                  Created: {{ note_created_at | app_pretty_dt if note_created_at else "—" }}
                </div>
              </div>

              {% if note_id %}
                <div class="print-hide" style="display:flex; gap:8px; align-items:center;">
                  <button type="button" class="btn" onclick="window.print()">
                    Print
                  </button>
                  <a class="btn" href="{{ url_for('case_management.edit_case_note', resident_id=resident_id, update_id=note_id) }}">
                    Edit Note
                  </a>
                </div>
              {% endif %}
            </div>

            {% if note_notes %}
              <div style="margin-top:14px;">
                <strong>Notes:</strong><br>
                <div class="case-note-text-block">{{ note_notes }}</div>
              </div>
            {% endif %}

            {% if note_progress_notes %}
              <div style="margin-top:14px;">
                <strong>Progress Notes:</strong><br>
                <div class="case-note-text-block">{{ note_progress_notes }}</div>
              </div>
            {% endif %}

            {% if note_action_items %}
              <div style="margin-top:14px;">
                <strong>Action Items:</strong><br>
                <div class="case-note-text-block">{{ note_action_items }}</div>
              </div>
            {% endif %}

            {% if note_updated_grit is not none or note_parenting_class_completed is not none or note_warrants_or_fines_paid is not none %}
              <div style="margin-top:14px;">
                <strong>Structured Progress:</strong>
                <span style="margin-left:10px;">
                  {% if note_updated_grit is not none %}
                    Grit: {{ note_updated_grit }}
                  {% endif %}

                  {% if note_parenting_class_completed is not none %}
                    {% if note_updated_grit is not none %}&nbsp;&nbsp;|&nbsp;&nbsp;{% endif %}
                    Parenting: {{ "Yes" if note_parenting_class_completed else "No" }}
                  {% endif %}

                  {% if note_warrants_or_fines_paid is not none %}
                    {% if note_updated_grit is not none or note_parenting_class_completed is not none %}&nbsp;&nbsp;|&nbsp;&nbsp;{% endif %}
                    Warrants: {{ "Yes" if note_warrants_or_fines_paid else "No" }}
                  {% endif %}
                </span>
              </div>
            {% endif %}

            {% if note_services %}
              <div style="margin-top:14px;">
                <strong>Services Provided:</strong>

                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-top:10px;">
                  {% for service in note_services %}
                    {% set service_type = service["service_type"] %}
                    {% set service_date = service["service_date"] %}
                    {% set service_notes_value = service["notes"] %}

                    <div style="padding:10px; border:1px solid #ddd; border-radius:6px;">
                      <div><strong>{{ service_type or "—" }}</strong></div>
                      <div style="margin-top:4px; font-size:0.88em; color:#666;">
                        {{ service_date or "—" }}
                      </div>

                      {% if service_notes_value %}
                        <div style="margin-top:8px;" class="case-note-text-block">
                          {{ service_notes_value }}
                        </div>
                      {% endif %}
                    </div>
                  {% endfor %}
                </div>
              </div>
            {% endif %}
          </div>

          <template id="print-case-note-{{ note_id }}">
            <div class="card">
              <div>
                <h3 style="margin-bottom:6px;">Progress Notes {{ note_meeting_date or "—" }}</h3>
                <div style="font-size:0.95em; color:#666;">
                  Created: {{ note_created_at | app_pretty_dt if note_created_at else "—" }}
                </div>
              </div>

              {% if note_notes %}
                <div style="margin-top:14px;">
                  <strong>Notes:</strong><br>
                  <div class="case-note-text-block">{{ note_notes }}</div>
                </div>
              {% endif %}

              {% if note_progress_notes %}
                <div style="margin-top:14px;">
                  <strong>Progress Notes:</strong><br>
                  <div class="case-note-text-block">{{ note_progress_notes }}</div>
                </div>
              {% endif %}

              {% if note_action_items %}
                <div style="margin-top:14px;">
                  <strong>Action Items:</strong><br>
                  <div class="case-note-text-block">{{ note_action_items }}</div>
                </div>
              {% endif %}

              {% if note_services %}
                <div style="margin-top:14px;">
                  <strong>Services Provided:</strong>

                  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-top:10px;">
                    {% for service in note_services %}
                      {% set service_type = service["service_type"] %}
                      {% set service_date = service["service_date"] %}
                      {% set service_notes_value = service["notes"] %}

                      <div style="padding:10px; border:1px solid #ddd; border-radius:6px;">
                        <div><strong>{{ service_type or "—" }}</strong></div>
                        <div style="margin-top:4px; font-size:0.88em; color:#666;">
                          {{ service_date or "—" }}
                        </div>

                        {% if service_notes_value %}
                          <div style="margin-top:8px;" class="case-note-text-block">
                            {{ service_notes_value }}
                          </div>
                        {% endif %}
                      </div>
                    {% endfor %}
                  </div>
                </div>
              {% endif %}
            </div>
          </template>
        {% endfor %}
      </div>

      <div id="print-selected-note" class="print-only-note"></div>

      <script>
        (function () {
          var lane = document.getElementById("case-note-scroll-lane");
          var tiles = Array.prototype.slice.call(document.querySelectorAll(".case-note-tile"));
          var panels = Array.prototype.slice.call(document.querySelectorAll(".case-note-panel"));
          var printBox = document.getElementById("print-selected-note");

          function showPanel(panelId, printId) {
            panels.forEach(function (panel) {
              panel.style.display = panel.id === panelId ? "block" : "none";
            });

            tiles.forEach(function (tile) {
              if (tile.getAttribute("data-note-target") === panelId) {
                tile.classList.add("is-active");
              } else {
                tile.classList.remove("is-active");
              }
            });

            if (printBox && printId) {
              var tpl = document.getElementById(printId);
              if (tpl) {
                printBox.innerHTML = tpl.innerHTML;
              }
            }
          }

          tiles.forEach(function (tile) {
            tile.addEventListener("click", function () {
              showPanel(
                tile.getAttribute("data-note-target"),
                tile.getAttribute("data-print-target")
              );
            });
          });

          if (lane) {
            lane.scrollLeft = lane.scrollWidth;
          }

          if (tiles.length > 0) {
            var newestTile = tiles[tiles.length - 1];
            showPanel(
              newestTile.getAttribute("data-note-target"),
              newestTile.getAttribute("data-print-target")
            );
          }
        })();
      </script>
    {% else %}
      <p class="progress-notes-empty">No monthly meetings recorded.</p>
    {% endif %}
  </div>

  <script>
    function showResidentNotebookTab(tabId, btnEl) {
      var tabs = document.querySelectorAll(".resident-notebook-tab");
      tabs.forEach(function (tab) {
        tab.style.display = "none";
      });

      var buttons = document.querySelectorAll(".notebook-tab-btn");
      buttons.forEach(function (button) {
        button.classList.remove("is-active");
      });

      var target = document.getElementById(tabId);
      if (target) {
        target.style.display = "block";
      }

      if (btnEl) {
        btnEl.classList.add("is-active");
      }
    }
  </script>

{% endif %}

{% endblock %}
