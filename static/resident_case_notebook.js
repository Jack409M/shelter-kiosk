(function () {
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

  window.showResidentNotebookTab = showResidentNotebookTab;

  function initCaseNotePanels() {
    var lane = document.getElementById("case-note-scroll-lane");
    var tiles = Array.prototype.slice.call(document.querySelectorAll(".case-note-tile"));
    var panels = Array.prototype.slice.call(document.querySelectorAll(".case-note-panel"));
    var printBox = document.getElementById("print-selected-note");

    if (!tiles.length || !panels.length) {
      return;
    }

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

    var newestTile = tiles[tiles.length - 1];
    showPanel(
      newestTile.getAttribute("data-note-target"),
      newestTile.getAttribute("data-print-target")
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    initCaseNotePanels();
  });
})();
