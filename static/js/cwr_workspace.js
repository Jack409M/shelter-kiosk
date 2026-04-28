document.addEventListener('DOMContentLoaded', () => {
  const modeButtons = document.querySelectorAll('.cwr-mode-btn');
  const questionPanels = document.querySelectorAll('.cwr-panel');
  const questionPlaceholder = document.querySelector('.cwr-panel-placeholder');
  const noteForm = document.querySelector('.cwr-note-form');
  const noteFields = noteForm ? noteForm.querySelectorAll('input, textarea, select') : [];
  const meetingDateField = noteForm ? noteForm.querySelector('input[name="meeting_date"]') : null;
  const noteEditByDate = window.CWR_NOTE_EDIT_BY_DATE || {};
  const residentId = window.RESIDENT_CASE_RESIDENT_ID || 'unknown';
  const noteFormDefaultAction = noteForm ? noteForm.getAttribute('action') : '';

  let noteFormDirty = false;
  let suppressBeforeUnload = false;
  let activeDraftDate = meetingDateField ? meetingDateField.value : '';
  let statusElement = null;

  function markNoteFormDirty() {
    noteFormDirty = true;
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

  function setStatus(message) {
    if (statusElement) {
      statusElement.textContent = message;
    }
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

  function clearMeetingTextFields() {
    if (!noteForm) {
      return;
    }

    noteForm.querySelectorAll('textarea').forEach((field) => {
      field.value = '';
      autoResizeTextarea(field);
    });
  }

  function loadDraftForDate(dateValue) {
    if (!noteForm || !dateValue) {
      return;
    }

    clearMeetingTextFields();

    let raw = null;
    try {
      raw = window.localStorage.getItem(draftKeyForDate(dateValue));
    } catch (error) {
      console.warn('Unable to load CWR meeting draft', error);
    }

    if (!raw) {
      noteFormDirty = false;
      noteForm.classList.remove('has-unsaved-changes');
      setStatus('No unsaved changes');
      return;
    }

    try {
      const payload = JSON.parse(raw);
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
      noteFormDirty = true;
      noteForm.classList.add('has-unsaved-changes');
      setStatus('Draft restored for selected date');
    } catch (error) {
      console.warn('Unable to parse CWR meeting draft', error);
    }
  }

  function updateNoteSaveModeForDate(dateValue) {
    if (!noteForm) {
      return;
    }

    const editUrl = noteEditByDate[dateValue];
    if (editUrl) {
      noteForm.setAttribute('action', editUrl);
      noteForm.classList.add('is-amending-note');
      setStatus('Saved note exists for this date. Save will amend that note.');
      return;
    }

    noteForm.setAttribute('action', noteFormDefaultAction);
    noteForm.classList.remove('is-amending-note');
    if (!noteFormDirty) {
      setStatus('No unsaved changes');
    }
  }

  function autoResizeTextarea(textarea) {
    const computed = window.getComputedStyle(textarea);
    const lineHeight = parseFloat(computed.lineHeight) || 20;
    const maxHeight = lineHeight * 20;

    textarea.style.height = 'auto';
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = nextHeight + 'px';
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
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
        if (activeDraftDate) {
          saveDraftForDate(activeDraftDate);
        }
        activeDraftDate = meetingDateField.value;
        loadDraftForDate(activeDraftDate);
        updateNoteSaveModeForDate(activeDraftDate);
      });

      updateNoteSaveModeForDate(meetingDateField.value);
    }

    noteForm.addEventListener('submit', () => {
      if (meetingDateField) {
        try {
          window.localStorage.removeItem(draftKeyForDate(meetingDateField.value));
        } catch (error) {
          console.warn('Unable to clear CWR meeting draft', error);
        }
      }
      clearNoteFormDirty();
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
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    };

    question.addEventListener('click', openPanel);
    question.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        openPanel(event);
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
