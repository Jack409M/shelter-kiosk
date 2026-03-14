(function () {
  const modal = document.getElementById("dayModal");
  if (!modal) {
    return;
  }

  const modalTitle = document.getElementById("dayModalTitle");
  const modalSubtitle = document.getElementById("dayModalSubtitle");
  const modalBody = document.getElementById("dayModalBody");
  const closeButton = document.getElementById("dayModalClose");
  const cells = document.querySelectorAll(".month-cell.has-events");
  const eventsScript = document.getElementById("residentTimelineEvents");

  let eventsByDate = {};

  if (eventsScript) {
    try {
      eventsByDate = JSON.parse(eventsScript.textContent || "{}");
    } catch (error) {
      console.error("Failed to parse resident timeline event data.", error);
      eventsByDate = {};
    }
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function buildEventRow(event) {
    const detailHtml = event.detail
      ? '<div class="event-card-detail">' + escapeHtml(event.detail) + "</div>"
      : "";

    return `
      <div class="day-modal-row">
        <div class="day-modal-time">${escapeHtml(event.time || "All day")}</div>
        <div class="event-card ${escapeHtml(event.badge_class || "")}">
          <div class="event-card-title">${escapeHtml(event.title || "Activity")}</div>
          <div class="event-card-type">${escapeHtml(event.type_label || "Activity")}</div>
          ${detailHtml}
        </div>
      </div>
    `;
  }

  function openModal(dateIso, labelText) {
    const events = eventsByDate[dateIso] || [];

    modalTitle.textContent = labelText || "Day Details";
    modalSubtitle.textContent = events.length === 1 ? "1 item" : `${events.length} items`;

    if (events.length) {
      modalBody.innerHTML = events.map(buildEventRow).join("");
    } else {
      modalBody.innerHTML = '<div class="day-modal-empty">No activity recorded for this date.</div>';
    }

    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
  }

  function closeModal() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
  }

  cells.forEach(function (cell) {
    cell.addEventListener("click", function () {
      openModal(cell.dataset.modalDate, cell.dataset.modalLabel);
    });

    cell.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openModal(cell.dataset.modalDate, cell.dataset.modalLabel);
      }
    });
  });

  if (closeButton) {
    closeButton.addEventListener("click", closeModal);
  }

  modal.addEventListener("click", function (event) {
    if (event.target && event.target.dataset && event.target.dataset.closeModal === "true") {
      closeModal();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && modal.classList.contains("is-open")) {
      closeModal();
    }
  });
})();
