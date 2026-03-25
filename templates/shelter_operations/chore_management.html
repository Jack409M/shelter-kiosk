{% extends "layout.html" %}

{% block content %}

<h1>Chore Management</h1>

<div class="card" style="margin-bottom:20px;">
  <h2>Add New Chore</h2>

  <form method="post">
    <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">

    <div style="margin-bottom:10px;">
      <label>Chore Name</label><br>
      <input type="text" name="name" style="width:300px;" required>
    </div>

    <div style="margin-bottom:10px;">
      <label>Description (optional)</label><br>
      <input type="text" name="description" style="width:400px;">
    </div>

    <button type="submit">Add Chore</button>
  </form>
</div>

<div class="card">
  <h2>Current Chores</h2>

  {% if chores %}
    <table class="table-compact">
      <thead>
        <tr>
          <th>Name</th>
          <th>Description</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for c in chores %}
        <tr>
          <td>{{ c.name }}</td>
          <td>{{ c.description or "—" }}</td>
          <td>
            {% if c.active %}
              Active
            {% else %}
              Inactive
            {% endif %}
          </td>
          <td>
            <form method="post" action="{{ url_for('shelter_operations.toggle_chore', chore_id=c.id) }}">
              <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
              <button type="submit">
                {% if c.active %}
                  Deactivate
                {% else %}
                  Activate
                {% endif %}
              </button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p>No chores created yet.</p>
  {% endif %}

</div>

{% endblock %}
