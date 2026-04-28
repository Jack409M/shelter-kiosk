document.addEventListener('DOMContentLoaded', () => {
  const modeButtons = document.querySelectorAll('.cwr-mode-btn');
  const questionPanels = document.querySelectorAll('.cwr-panel');
  const questionPlaceholder = document.querySelector('.cwr-panel-placeholder');
  const noteForm = document.querySelector('.cwr-note-form');
  const noteFields = noteForm ? noteForm.querySelectorAll('input, textarea, select') : [];

  let noteFormDirty = false;
  let suppressBeforeUnload = false;

  function markNoteFormDirty() {
    noteFormDirty = true;
    if (noteForm) {
      noteForm.classList.add('has-unsaved-changes');
    }
  }

  function clearNoteFormDirty() {
    noteFormDirty = false;
    suppressBeforeUnload = true;
    if (noteForm) {
      noteForm.classList.remove('has-unsaved-changes');
    }
  }

  function confirmUnsavedNotes() {
    if (!noteFormDirty) {
      return true;
    }

    return window.confirm('You have unsaved meeting notes. Continue without saving those notes?');
  }

  function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }

  function setupNoteWritingExperience() {
    if (!noteForm) {
      return;
    }

    const status = document.createElement('div');
    status.className = 'cwr-note-save-status';
    status.setAttribute('aria-live', 'polite');
    status.textContent = 'No unsaved changes';

    const formHead = noteForm.querySelector('.cwr-form-head');
    if (formHead) {
      formHead.appendChild(status);
    }

    noteFields.forEach((field) => {
      field.addEventListener('input', () => {
        markNoteFormDirty();
        status.textContent = 'Unsaved meeting note changes';
      });
      field.addEventListener('change', () => {
        markNoteFormDirty();
        status.textContent = 'Unsaved meeting note changes';
      });
    });

    noteForm.addEventListener('submit', clearNoteFormDirty);

    noteForm.querySelectorAll('textarea').forEach((textarea) => {
      autoResizeTextarea(textarea);
      textarea.addEventListener('input', () => autoResizeTextarea(textarea));
      textarea.addEventListener('focus', () => openFocusEditor(textarea));
    });
  }

  function buildFocusEditor() {
    const overlay = document.createElement('div');
    overlay.className = 'cwr-focus-editor';
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="cwr-focus-backdrop" data-cwr-focus-close></div>
      <div class="cwr-focus-dialog" role="dialog" aria-modal="true" aria-labelledby="cwr-focus-title">
        <div class="cwr-focus-head">
          <div>
            <div class="cwr-focus-kicker">Meeting note editor</div>
            <h3 id="cwr-focus-title">Edit note</h3>
          </div>
          <button type="button" class="cwr-focus-close" data-cwr-focus-close>Close</button>
        </div>
        <textarea class="cwr-focus-textarea"></textarea>
        <div class="cwr-focus-actions">
          <button type="button" class="cwr-focus-secondary" data-cwr-focus-close>Done</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
  }

  const focusEditor = buildFocusEditor();
  const focusTitle = focusEditor.querySelector('#cwr-focus-title');
  const focusTextarea = focusEditor.querySelector('.cwr-focus-textarea');
  let activeSourceTextarea = null;

  function closeFocusEditor() {
    if (!activeSourceTextarea) {
      focusEditor.hidden = true;
      return;
    }

    activeSourceTextarea.value = focusTextarea.value;
    activeSourceTextarea.dispatchEvent(new Event('input', { bubbles: true }));
    autoResizeTextarea(activeSourceTextarea);
    focusEditor.hidden = true;
    activeSourceTextarea.focus();
    activeSourceTextarea = null;
  }

  function openFocusEditor(sourceTextarea) {
    activeSourceTextarea = sourceTextarea;
    const label = sourceTextarea.closest('label');
    const labelText = label ? label.childNodes[0].textContent.trim() : 'Edit note';
    focusTitle.textContent = labelText || 'Edit note';
    focusTextarea.value = sourceTextarea.value;
    focusEditor.hidden = false;
    window.requestAnimationFrame(() => focusTextarea.focus());
  }

  focusEditor.querySelectorAll('[data-cwr-focus-close]').forEach((control) => {
    control.addEventListener('click', closeFocusEditor);
  });

  focusTextarea.addEventListener('input', () => {
    if (activeSourceTextarea) {
      activeSourceTextarea.value = focusTextarea.value;
      activeSourceTextarea.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !focusEditor.hidden) {
      closeFocusEditor();
    }
  });

  function closeAllQuestionPanels() {
    questionPanels.forEach((item) => {
      item.hidden = true;
      item.classList.remove('is-open');
    });
  }

  modeButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!confirmUnsavedNotes()) {
        return;
      }

      const mode = btn.dataset.mode;

      modeButtons.forEach((item) => {
        item.classList.remove('is-active');
      });
      btn.classList.add('is-active');

      document.querySelectorAll('.cwr-mode').forEach((section) => {
        section.classList.remove('is-active');
      });

      const activeSection = document.getElementById('cwr-' + mode);
      if (activeSection) {
        activeSection.classList.add('is-active');
      }
    });
  });

  closeAllQuestionPanels();

  document.querySelectorAll('.cwr-question').forEach((question) => {
    const openPanel = (event) => {
      if (event) {
        event.preventDefault();
      }

      if (!confirmUnsavedNotes()) {
        return;
      }

      const panelName = question.dataset.panel;
      const panel = document.getElementById('cwr-panel-' + panelName);

      document.querySelectorAll('.cwr-question').forEach((item) => {
        item.classList.remove('is-active');
      });
      question.classList.add('is-active');

      closeAllQuestionPanels();

      if (questionPlaceholder) {
        questionPlaceholder.hidden = true;
        questionPlaceholder.classList.add('is-hidden');
      }

      if (panel) {
        panel.hidden = false;
        panel.classList.add('is-open');
      }
    };

    question.addEventListener('click', openPanel);
    question.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        openPanel(event);
      }
    });
  });

  setupNoteWritingExperience();

  window.addEventListener('beforeunload', (event) => {
    if (suppressBeforeUnload || !noteFormDirty) {
      return;
    }

    event.preventDefault();
    event.returnValue = '';
  });
});
