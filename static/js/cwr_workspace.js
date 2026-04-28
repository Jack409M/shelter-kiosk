document.addEventListener('DOMContentLoaded', () => {
  const modeButtons = document.querySelectorAll('.cwr-mode-btn');
  const questionPanels = document.querySelectorAll('.cwr-panel');
  const questionPlaceholder = document.querySelector('.cwr-panel-placeholder');
  const noteForm = document.querySelector('.cwr-note-form');
  const noteFields = noteForm ? noteForm.querySelectorAll('input, textarea, select') : [];
  const meetingDateField = noteForm ? noteForm.querySelector('input[name="meeting_date"]') : null;
  const noteEditByDate = window.CWR_NOTE_EDIT_BY_DATE || {};
  const noteValuesByDate = window.CWR_NOTE_VALUES_BY_DATE || {};
  const residentId = window.RESIDENT_CASE_RESIDENT_ID || 'unknown';
  const noteFormDefaultAction = noteForm ? noteForm.getAttribute('action') : '';
  const noteSaveButton = noteForm ? noteForm.querySelector('button[type="submit"]') : null;
  const pageParams = new URLSearchParams(window.location.search);
  const requestedPanel = pageParams.get('active_panel') || '';

  let noteFormDirty = false;
  let suppressBeforeUnload = false;
  let activeDraftDate = meetingDateField ? meetingDateField.value : '';
  let statusElement = null;
  let activePanelName = '';

  function setStatus(message) {
    if (statusElement) {
      statusElement.textContent = message;
    }
  }

  function markNoteFormDirty() {
    noteFormDirty = true;
    suppressBeforeUnload = false;
    if (noteForm) {
      noteForm.classList.add('has-unsaved-changes');
    }
    setStatus('Unsaved meeting note changes');
  }

  function clearNoteFormDirty() {
    noteFormDirty = false;
    suppressBeforeUnload = true;
    if (noteForm) {
      noteForm.classList.remove('has-unsaved-changes');
    }
    setStatus('No unsaved changes');
  }

  function confirmUnsavedNotes() {
    if (!noteFormDirty) {
      return true;
    }

    return window.confirm('You have unsaved meeting notes. Continue without saving those notes?');
  }

  function draftKeyForDate(dateValue) {
    return 'cwr_meeting_draft_' + residentId + '_' + (dateValue || 'undated');
  }

  function draftFields() {
    if (!noteForm) {
      return [];
    }

    return Array.from(noteForm.querySelectorAll('input[name], textarea[name], select[name]')).filter((field) => {
      return field.name && field.name !== '_csrf_token';
    });
  }

  function saveDraftForDate(dateValue) {
    if (!noteForm || !dateValue) {
      return;
    }

    const payload = {};
    draftFields().forEach((field) => {
      if (field.type === 'checkbox') {
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

    try {
      window.localStorage.setItem(draftKeyForDate(dateValue), JSON.stringify(payload));
    } catch (error) {
      console.warn('Unable to save CWR meeting draft', error);
    }
  }

  function clearDraftForDate(dateValue) {
    if (!dateValue) {
      return;
    }

    try {
      window.localStorage.removeItem(draftKeyForDate(dateValue));
    } catch (error) {
      console.warn('Unable to clear CWR meeting draft', error);
    }
  }

  function clearMeetingTextFields() {
    if (!noteForm) {
      return;
    }

    noteForm.querySelectorAll('textarea').forEach((field) => {
      field.value = '';
      autoResizeTextarea(field);
    });
  }

  function applyPayloadToForm(payload, dirtyState) {
    if (!payload || !noteForm) {
      return;
    }

    draftFields().forEach((field) => {
      if (!(field.name in payload)) {
        return;
      }
      if (field.type === 'checkbox') {
        const values = payload[field.name] || [];
        field.checked = Array.isArray(values) && values.includes(field.value);
        return;
      }
      field.value = payload[field.name] || '';
      if (field.tagName === 'TEXTAREA') {
        autoResizeTextarea(field);
      }
    });

    noteFormDirty = dirtyState;
    noteForm.classList.toggle('has-unsaved-changes', dirtyState);
  }

  function setNewNoteMode(dateValue) {
    if (!noteForm) {
      return;
    }

    noteForm.setAttribute('action', noteFormDefaultAction);
    noteForm.classList.remove('is-amending-note');
    if (noteSaveButton) {
      noteSaveButton.textContent = 'Save Meeting Note';
    }
    if (!noteFormDirty) {
      setStatus(dateValue ? 'New meeting note for selected date' : 'No unsaved changes');
    }
  }

  function setAmendNoteMode(dateValue) {
    if (!noteForm) {
      return;
    }

    const editUrl = noteEditByDate[dateValue];
    if (!editUrl) {
      setNewNoteMode(dateValue);
      return;
    }

    noteForm.setAttribute('action', editUrl);
    noteForm.classList.add('is-amending-note');
    if (noteSaveButton) {
      noteSaveButton.textContent = 'Amend Meeting Note';
    }
    setStatus('Editing saved note for selected date. Save will amend this note.');
  }

  function loadNoteStateForDate(dateValue) {
    if (!noteForm || !dateValue) {
      return;
    }

    clearMeetingTextFields();

    if (noteValuesByDate[dateValue]) {
      applyPayloadToForm(noteValuesByDate[dateValue], false);
      setAmendNoteMode(dateValue);
      return;
    }

    let raw = null;
    try {
      raw = window.localStorage.getItem(draftKeyForDate(dateValue));
    } catch (error) {
      console.warn('Unable to load CWR meeting draft', error);
    }

    if (raw) {
      try {
        applyPayloadToForm(JSON.parse(raw), true);
        setNewNoteMode(dateValue);
        setStatus('Unsaved draft restored for selected date');
        return;
      } catch (error) {
        console.warn('Unable to parse CWR meeting draft', error);
      }
    }

    noteFormDirty = false;
    noteForm.classList.remove('has-unsaved-changes');
    setNewNoteMode(dateValue);
  }

  function autoResizeTextarea(textarea) {
    const computed = window.getComputedStyle(textarea);
    const lineHeight = parseFloat(computed.lineHeight) || 20;
    const maxHeight = lineHeight * 5;

    textarea.style.height = 'auto';
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = nextHeight + 'px';
    textarea.style.maxHeight = maxHeight + 'px';
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }

  function ensureHiddenField(form, name, value) {
    let field = form.querySelector('input[type="hidden"][name="' + name + '"]');
    if (!field) {
      field = document.createElement('input');
      field.type = 'hidden';
      field.name = name;
      form.appendChild(field);
    }
    field.value = value;
  }

  function updateActivePanelFields() {
    document.querySelectorAll('.cwr-page form').forEach((form) => {
      ensureHiddenField(form, 'redirect_to', 'cwr');
      ensureHiddenField(form, 'active_panel', activePanelName || '');
    });
  }

  function normalizeDuplicateProfileControls(form) {
    const visibleNames = new Set();

    form.querySelectorAll('input[name], textarea[name], select[name]').forEach((field) => {
      if (field.type !== 'hidden') {
        visibleNames.add(field.name);
      }
    });

    if (!visibleNames.size) {
      return;
    }

    form.querySelectorAll('input[type="hidden"][name]').forEach((field) => {
      if (visibleNames.has(field.name)) {
        field.disabled = true;
      }
    });
  }

  function setupCwrFormPosts() {
    document.querySelectorAll('.cwr-page form').forEach((form) => {
      ensureHiddenField(form, 'redirect_to', 'cwr');
      ensureHiddenField(form, 'active_panel', activePanelName || '');
      normalizeDuplicateProfileControls(form);
    });
  }

  function setupNoteWritingExperience() {
    if (!noteForm) {
      return;
    }

    statusElement = document.createElement('div');
    statusElement.className = 'cwr-note-save-status';
    statusElement.setAttribute('aria-live', 'polite');
    statusElement.textContent = 'No unsaved changes';

    const formHead = noteForm.querySelector('.cwr-form-head');
    if (formHead) {
      formHead.appendChild(statusElement);
    }

    noteFields.forEach((field) => {
      field.addEventListener('input', () => {
        markNoteFormDirty();
        if (meetingDateField) {
          saveDraftForDate(meetingDateField.value);
        }
      });
      field.addEventListener('change', () => {
        markNoteFormDirty();
        if (meetingDateField) {
          saveDraftForDate(meetingDateField.value);
        }
      });
    });

    if (meetingDateField) {
      meetingDateField.addEventListener('focus', () => {
        activeDraftDate = meetingDateField.value;
      });

      meetingDateField.addEventListener('change', () => {
        if (activeDraftDate && activeDraftDate !== meetingDateField.value) {
          saveDraftForDate(activeDraftDate);
        }
        activeDraftDate = meetingDateField.value;
        loadNoteStateForDate(activeDraftDate);
      });

      loadNoteStateForDate(meetingDateField.value);
    }

    noteForm.addEventListener('submit', () => {
      if (meetingDateField) {
        clearDraftForDate(meetingDateField.value);
      }
      clearNoteFormDirty();
      updateActivePanelFields();
    });

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
      item.setAttribute('hidden', 'hidden');
      item.classList.remove('is-open');
      item.style.display = 'none';
    });
  }

  function activateMode(mode) {
    modeButtons.forEach((item) => {
      item.classList.toggle('is-active', item.dataset.mode === mode);
    });

    document.querySelectorAll('.cwr-mode').forEach((section) => {
      section.classList.remove('is-active');
    });

    const activeSection = document.getElementById('cwr-' + mode);
    if (activeSection) {
      activeSection.classList.add('is-active');
    }
  }

  modeButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!confirmUnsavedNotes()) {
        return;
      }

      activateMode(btn.dataset.mode);
    });
  });

  closeAllQuestionPanels();

  function openQuestionPanel(question, event, requireConfirmation = true) {
    if (event) {
      event.preventDefault();
    }

    const panelName = question.dataset.panel;
    const panel = document.getElementById('cwr-panel-' + panelName);

    if (!panel) {
      return;
    }

    if (requireConfirmation && activePanelName && activePanelName !== panelName && !confirmUnsavedNotes()) {
      return;
    }

    activePanelName = panelName;
    updateActivePanelFields();

    document.querySelectorAll('.cwr-question').forEach((item) => {
      item.classList.remove('is-active');
      item.setAttribute('aria-expanded', 'false');
    });
    question.classList.add('is-active');
    question.setAttribute('aria-expanded', 'true');

    closeAllQuestionPanels();

    if (questionPlaceholder) {
      questionPlaceholder.hidden = true;
      questionPlaceholder.setAttribute('hidden', 'hidden');
      questionPlaceholder.classList.add('is-hidden');
    }

    panel.hidden = false;
    panel.removeAttribute('hidden');
    panel.classList.add('is-open');
    panel.style.display = 'block';
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  document.querySelectorAll('.cwr-question').forEach((question) => {
    question.setAttribute('role', 'button');
    question.setAttribute('aria-expanded', 'false');

    question.addEventListener('click', (event) => openQuestionPanel(question, event));
    question.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        openQuestionPanel(question, event);
      }
    });
  });

  document.querySelectorAll('form').forEach((form) => {
    if (form === noteForm) {
      return;
    }
    form.addEventListener('submit', (event) => {
      if (!confirmUnsavedNotes()) {
        event.preventDefault();
        return;
      }
      updateActivePanelFields();
      normalizeDuplicateProfileControls(form);
    });
  });

  setupCwrFormPosts();
  setupNoteWritingExperience();

  if (requestedPanel) {
    const question = document.querySelector('.cwr-question[data-panel="' + requestedPanel + '"]');
    if (question) {
      activateMode('meeting');
      openQuestionPanel(question, null, false);
    }
  }

  window.addEventListener('beforeunload', (event) => {
    if (suppressBeforeUnload || !noteFormDirty) {
      return;
    }

    event.preventDefault();
    event.returnValue = '';
  });
});
