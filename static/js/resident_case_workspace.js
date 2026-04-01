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
  var fields = Array.prototype.slice.call(
    form.querySelectorAll("input[name], textarea[name], select[name]")
  );
  var saveButtons = Array.prototype.slice.call(
    document.querySelectorAll('button[form="meeting-workspace-form"], input[form="meeting-workspace-form"]')
  );
  var saveMessageEl = document.querySelector(".cmx-draft");
  var saveTimer = null;
  var lastSavedAt = null;

  if (justSaved) {
    localStorage.removeItem(storageKey);
  }

  function setSaveMessage(text) {
    if (!saveMessageEl) {
      return;
    }
    saveMessageEl.textContent = text;
  }

  function buildPayload() {
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

    return payload;
  }

  function saveDraft() {
    try {
      var payload = buildPayload();
      localStorage.setItem(storageKey, JSON.stringify(payload));
      lastSavedAt = new Date();

      setSaveMessage(
        "Draft protected while working" +
          (lastSavedAt ? " • Saved " + lastSavedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "")
      );
    } catch (err) {
      console.warn("Could not save meeting draft", err);
      setSaveMessage("Draft protection had a problem on this browser");
    }
  }

  function queueSave() {
    setSaveMessage("Saving draft...");
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(saveDraft, 300);
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

      setSaveMessage("Draft restored for this resident");
    } catch (err) {
      console.warn("Could not load meeting draft", err);
      setSaveMessage("Draft found but could not be restored");
    }
  }

  fields.forEach(function(field) {
    field.addEventListener("input", queueSave);
    field.addEventListener("change", queueSave);
    field.addEventListener("blur", saveDraft);
  });

  saveButtons.forEach(function(button) {
    button.addEventListener("click", saveDraft);
  });

  form.addEventListener("submit", function() {
    saveDraft();
  });

  window.addEventListener("beforeunload", function() {
    saveDraft();
  });

  loadDraft();

  if (!justSaved && !localStorage.getItem(storageKey)) {
    setSaveMessage("Draft protection active");
  }
}

function setupWriterExpansion() {
  var cards = Array.prototype.slice.call(document.querySelectorAll(".cmx-writing-card"));
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

    textarea.addEventListener("click", function() {
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

function setupMeetingHistory() {
  var tiles = Array.prototype.slice.call(document.querySelectorAll(".case-note-tile"));
  var printContainer = document.getElementById("print-selected-note");
  var modal = document.getElementById("case-note-modal");
  var modalBody = document.getElementById("case-note-modal-body");
  var modalSubtitle = document.getElementById("case-note-modal-subtitle");
  var closeButtons = Array.prototype.slice.call(document.querySelectorAll("[data-case-note-close]"));

  if (!tiles.length || !modal || !modalBody) {
    return;
  }

  function closeModal() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    modalBody.innerHTML = "";
    if (modalSubtitle) {
      modalSubtitle.textContent = "";
    }

    tiles.forEach(function(tile) {
      tile.classList.remove("is-active");
    });
  }

  function openTile(tile) {
    if (!tile) {
      return;
    }

    var targetId = tile.getAttribute("data-note-target");
    var printId = tile.getAttribute("data-print-target");
    var panel = targetId ? document.getElementById(targetId) : null;
    var printTemplate = printId ? document.getElementById(printId) : null;

    tiles.forEach(function(item) {
      item.classList.remove("is-active");
    });

    tile.classList.add("is-active");

    if (panel) {
      modalBody.innerHTML = panel.innerHTML;

      var createdEl = modalBody.querySelector(".case-note-created");
      if (modalSubtitle && createdEl) {
        modalSubtitle.textContent = createdEl.textContent;
        createdEl.remove();
      } else if (modalSubtitle) {
        modalSubtitle.textContent = "";
      }

      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
    }

    if (printContainer) {
      printContainer.innerHTML = printTemplate ? printTemplate.innerHTML : "";
    }
  }

  tiles.forEach(function(tile) {
    tile.addEventListener("click", function() {
      openTile(tile);
    });
  });

  closeButtons.forEach(function(button) {
    button.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", function(event) {
    if (event.key === "Escape" && modal.classList.contains("is-open")) {
      closeModal();
    }
  });
}

document.addEventListener("DOMContentLoaded", function() {
  toggleEmploymentProfileFields();
  bindQuickChildServiceAction();
  setupMeetingDraft();
  setupWriterExpansion();
  setupMeetingHistory();
});
