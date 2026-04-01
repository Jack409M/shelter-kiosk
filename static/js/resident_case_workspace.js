function toggleEmploymentProfileFields() {
  var statusField = document.getElementById("employment_status_current");
  var unemployedSection = document.getElementById("employment_fields_unemployed");

  if (!statusField || !unemployedSection) {
    return;
  }

  unemployedSection.style.display = statusField.value === "unemployed" ? "block" : "none";
}

function bindQuickChildServiceAction() {
  var select = document.getElementById("quick_child_id");
  var form = document.getElementById("quick-child-service-form");
  var serviceSelect = document.getElementById("quick_child_service_type");
  var otherWrap = document.getElementById("quick_child_service_other_wrap");
  var otherInput = document.getElementById("quick_child_service_other");
  var childServiceBaseAction = window.RESIDENT_CASE_CHILD_SERVICE_BASE_ACTION || "";

  if (select && form && childServiceBaseAction) {
    function updateAction() {
      var childId = select.value || "0";
      form.action = childServiceBaseAction.replace("/0/services", "/" + childId + "/services");
    }

    select.addEventListener("change", updateAction);
    updateAction();
  }

  if (serviceSelect && otherWrap && otherInput) {
    function toggleOtherService() {
      if (serviceSelect.value === "Other") {
        otherWrap.style.display = "block";
      } else {
        otherWrap.style.display = "none";
        otherInput.value = "";
      }
    }

    serviceSelect.addEventListener("change", toggleOtherService);
    toggleOtherService();
  }
}

function setupMeetingDraft() {
  var form = document.getElementById("meeting-workspace-form");
  if (!form) {
    return;
  }

  var residentId = window.RESIDENT_CASE_RESIDENT_ID || "";
  var justSaved = Boolean(window.RESIDENT_CASE_NOTE_SAVED);
  var storageKey = "cm_meeting_draft_" + residentId;
  var fields = form.querySelectorAll("input[name], textarea[name], select[name]");

  if (justSaved) {
    localStorage.removeItem(storageKey);
  }

  function saveDraft() {
    var payload = {};
    fields.forEach(function(field) {
      if (!field.name) {
        return;
      }

      if (field.type === "checkbox") {
        if (!payload[field.name]) {
          payload[field.name] = [];
        }
        if (field.checked) {
          payload[field.name].push(field.value);
        }
        return;
      }

      payload[field.name] = field.value;
    });

    localStorage.setItem(storageKey, JSON.stringify(payload));
  }

  function loadDraft() {
    if (justSaved) {
      return;
    }

    var raw = localStorage.getItem(storageKey);
    if (!raw) {
      return;
    }

    try {
      var payload = JSON.parse(raw);

      fields.forEach(function(field) {
        if (!field.name || !(field.name in payload)) {
          return;
        }

        if (field.type === "checkbox") {
          var values = payload[field.name] || [];
          field.checked = Array.isArray(values) && values.indexOf(field.value) !== -1;
          return;
        }

        if (field.value === "" || field.tagName === "TEXTAREA" || field.tagName === "SELECT") {
          field.value = payload[field.name];
        }
      });
    } catch (err) {
      console.warn("Could not load meeting draft", err);
    }
  }

  fields.forEach(function(field) {
    field.addEventListener("input", saveDraft);
    field.addEventListener("change", saveDraft);
  });

  form.addEventListener("submit", saveDraft);
  loadDraft();
}

function setupWriterExpansion() {
  var cards = document.querySelectorAll(".cmx-writing-card");
  if (!cards.length) {
    return;
  }

  function clearActive() {
    cards.forEach(function(card) {
      card.classList.remove("is-active-writer");
    });
  }

  cards.forEach(function(card) {
    var textarea = card.querySelector("textarea");
    if (!textarea) {
      return;
    }

    textarea.addEventListener("focus", function() {
      clearActive();
      card.classList.add("is-active-writer");
    });

    textarea.addEventListener("blur", function() {
      if (!textarea.value.trim()) {
        card.classList.remove("is-active-writer");
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", function() {
  toggleEmploymentProfileFields();
  bindQuickChildServiceAction();
  setupMeetingDraft();
  setupWriterExpansion();
});
