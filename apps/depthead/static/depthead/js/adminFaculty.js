        const addFacultyBtn = document.getElementById('addFacultyBtn');
        const facultyModal = document.getElementById('facultyModal');
        const closeFacultyModal = document.getElementById('closeFacultyModal');
        const facultyForm = document.getElementById('facultyForm');
        const crudLoadingModal = document.getElementById('crudLoadingModal');
        const crudLoadingMessage = document.getElementById('crudLoadingMessage');
        const removeFacultyConfirmModal = document.getElementById('removeFacultyConfirmModal');
        const removeFacultyName = document.getElementById('removeFacultyName');
        const closeRemoveFacultyConfirm = document.getElementById('closeRemoveFacultyConfirm');
        const confirmRemoveFaculty = document.getElementById('confirmRemoveFaculty');
        const scheduleTemplateModal = document.getElementById('scheduleTemplateModal');
        const openScheduleTemplateModal = document.getElementById('openScheduleTemplateModal');
        const closeScheduleTemplateModal = document.getElementById('closeScheduleTemplateModal');
        const cancelScheduleTemplate = document.getElementById('cancelScheduleTemplate');
        const resetScheduleTemplate = document.getElementById('resetScheduleTemplate');
        const scheduleTemplateFields = document.getElementById('scheduleTemplateFields');
        const scheduleTemplateColumns = document.getElementById('scheduleTemplateColumns');
        const addScheduleTemplateAttribute = document.getElementById('addScheduleTemplateAttribute');
        const scheduleTemplateForm = scheduleTemplateModal?.querySelector('form');
        const requiredTemplateAttributes = new Set([
            'OFFERING_ID', 'SUBJ_CODE', 'SECTION', 'SUBJECT_TITLE',
            'DAYFROM', 'DAYTO', 'TIMEFROM', 'TIMETO',
        ]);
        let pendingRemoveForm = null;

        function closeScheduleTemplateModalFn() {
            if (scheduleTemplateModal) scheduleTemplateModal.classList.add('hidden');
        }

        if (openScheduleTemplateModal) {
            openScheduleTemplateModal.addEventListener('click', () => {
                scheduleTemplateModal.classList.remove('hidden');
            });
        }
        if (closeScheduleTemplateModal) closeScheduleTemplateModal.addEventListener('click', closeScheduleTemplateModalFn);
        if (cancelScheduleTemplate) cancelScheduleTemplate.addEventListener('click', closeScheduleTemplateModalFn);
        if (resetScheduleTemplate) {
            resetScheduleTemplate.addEventListener('click', () => {
                const defaults = [
                    ['OFFERING_ID', 'OFFERING_ID'], ['SUBJ_CODE', 'SUBJ_CODE'],
                    ['SECTION', 'SECTION'], ['SUBJECT_TITLE', 'SUBJECT_TITLE'],
                    ['UNITS', 'UNITS'], ['LECTURE', 'LECTURE'], ['LAB', 'LAB'],
                    ['RECURRING_DAY', 'RECURRING_DAY'], ['DAYFROM', 'DAYFROM'],
                    ['DAYTO', 'DAYTO'], ['TIMEFROM', 'TIMEFROM'], ['TIMETO', 'TIMETO'],
                    ['ROOM', 'ROOM'],
                ];
                scheduleTemplateFields.innerHTML = '';
                defaults.forEach(([key, label]) => addTemplateAttributeRow(key, label));
                syncScheduleTemplateColumns();
            });
        }

        function addTemplateAttributeRow(key, label) {
            const row = document.createElement('div');
            row.className = 'modal-form-group schedule-template-attribute';
            row.dataset.key = key;
            row.innerHTML = `<label><span class="schedule-template-attribute-label">${label}</span><span class="schedule-template-field-key">${key}</span></label><div class="schedule-template-input-row"><input type="text" class="schedule-template-attribute-input" value="${label}" maxlength="64" required><button type="button" class="schedule-template-remove">Remove</button></div>`;
            scheduleTemplateFields.appendChild(row);
            return row;
        }

        function syncScheduleTemplateColumns() {
            if (!scheduleTemplateFields || !scheduleTemplateColumns) return;
            const columns = [...scheduleTemplateFields.querySelectorAll('.schedule-template-attribute')]
                .map((row) => ({
                    key: row.dataset.key,
                    label: row.querySelector('.schedule-template-attribute-input')?.value.trim() || '',
                }));
            scheduleTemplateColumns.value = JSON.stringify(columns);
        }

        function removeScheduleTemplateAttribute(row) {
            if (requiredTemplateAttributes.has(row.dataset.key)) {
                showCrudToast('Required schedule attributes cannot be deleted.', true);
                return;
            }
            row.remove();
            syncScheduleTemplateColumns();
        }

        scheduleTemplateFields?.addEventListener('click', (event) => {
            const button = event.target.closest('.schedule-template-remove');
            if (button) removeScheduleTemplateAttribute(button.closest('.schedule-template-attribute'));
        });
        scheduleTemplateFields?.addEventListener('input', (event) => {
            if (!event.target.classList.contains('schedule-template-attribute-input')) return;
            const label = event.target.closest('.schedule-template-attribute')?.querySelector('.schedule-template-attribute-label');
            if (label) label.textContent = event.target.value || 'Unnamed attribute';
        });

        addScheduleTemplateAttribute?.addEventListener('click', () => {
            const used = new Set([...scheduleTemplateFields.querySelectorAll('.schedule-template-attribute')]
                .map((row) => row.dataset.key));
            let index = 1;
            let key = `CUSTOM_ATTRIBUTE_${index}`;
            while (used.has(key)) key = `CUSTOM_ATTRIBUTE_${++index}`;
            addTemplateAttributeRow(key, 'New attribute');
            scheduleTemplateFields.lastElementChild.querySelector('input').focus();
        });

        scheduleTemplateForm?.addEventListener('submit', syncScheduleTemplateColumns);
        if (scheduleTemplateModal) {
            scheduleTemplateModal.addEventListener('click', (event) => {
                if (event.target === scheduleTemplateModal) closeScheduleTemplateModalFn();
            });
        }

        function setCrudLoading(isLoading, message = 'Processing request...') {
            if (!crudLoadingModal) return;
            if (crudLoadingMessage) crudLoadingMessage.textContent = message;
            crudLoadingModal.classList.toggle('show', isLoading);
            document.body.setAttribute('aria-busy', isLoading ? 'true' : 'false');
        }

        function closeRemoveFacultyConfirmation() {
            if (removeFacultyConfirmModal) removeFacultyConfirmModal.classList.add('hidden');
            pendingRemoveForm = null;
        }

        function openFacultyModal() {
            facultyModal.classList.remove('hidden');
        }

        function closeFacultyModalFn() {
            facultyModal.classList.add('hidden');
            facultyForm.reset();
        }

        addFacultyBtn.addEventListener('click', openFacultyModal);
        closeFacultyModal.addEventListener('click', closeFacultyModalFn);
        facultyModal.addEventListener('click', (event) => {
            if (event.target === facultyModal) {
                closeFacultyModalFn();
            }
        });

        facultyForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const submitButton = facultyForm.querySelector('button[type="submit"]');
            if (submitButton) submitButton.disabled = true;
            setCrudLoading(true, 'Sending faculty invitation...');

            try {
                const response = await fetch(facultyForm.action, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: new FormData(facultyForm),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    throw new Error(data.error || 'Unable to create the faculty invitation.');
                }

                closeFacultyModalFn();
                showCrudToast(data.message || 'Faculty invitation created.');
                window.setTimeout(() => window.location.reload(), 1100);
            } catch (error) {
                setCrudLoading(false);
                showCrudToast(error.message || 'Unable to create the faculty invitation.', true);
                if (submitButton) submitButton.disabled = false;
            }
        });

        document.querySelectorAll('.remove-faculty-trigger').forEach((button) => {
            button.addEventListener('click', (event) => {
                event.preventDefault();
                pendingRemoveForm = button.closest('.remove-faculty-form');
                if (removeFacultyName) {
                    removeFacultyName.textContent = button.dataset.facultyName || 'this faculty member';
                }
                if (removeFacultyConfirmModal) removeFacultyConfirmModal.classList.remove('hidden');
            });
        });

        if (closeRemoveFacultyConfirm) closeRemoveFacultyConfirm.addEventListener('click', closeRemoveFacultyConfirmation);
        if (removeFacultyConfirmModal) {
            removeFacultyConfirmModal.addEventListener('click', (event) => {
                if (event.target === removeFacultyConfirmModal) closeRemoveFacultyConfirmation();
            });
        }
        if (confirmRemoveFaculty) {
            confirmRemoveFaculty.addEventListener('click', () => {
                if (!pendingRemoveForm) return;
                const form = pendingRemoveForm;
                closeRemoveFacultyConfirmation();
                form.requestSubmit();
            });
        }

const scheduleFileInput = document.getElementById('facultyScheduleFile');
const schedulePreviewModal = document.getElementById('facultySchedulePreviewModal');
const schedulePreviewClose = document.getElementById('closeFacultySchedulePreview');
const schedulePreviewFaculty = document.getElementById('facultySchedulePreviewFaculty');
const scheduleUploadStatus = document.getElementById('facultyScheduleUploadStatus');
const schedulePreviewEmpty = document.getElementById('facultySchedulePreviewEmpty');
const schedulePreviewTable = document.getElementById('facultySchedulePreviewTable');
const schedulePreviewHead = document.getElementById('facultySchedulePreviewHead');
const schedulePreviewBody = document.getElementById('facultySchedulePreviewBody');
const schedulePreviewSearch = document.getElementById('facultySchedulePreviewSearch');
const schedulePreviewCount = document.getElementById('facultySchedulePreviewCount');
const deleteUploadedScheduleButton = document.getElementById('deleteFacultyUploadedSchedule');
let schedulePreviewRows = [];
let schedulePreviewColumns = [];
let selectedFacultyId = '';
let selectedFacultyUploadUrl = '';
let selectedFacultyPreviewUrl = '';
let selectedFacultyDeleteUrl = '';

function getCsrfToken() {
    const pageToken = document.querySelector('#deptheadCsrfToken input[name="csrfmiddlewaretoken"]');
    if (pageToken && pageToken.value) return pageToken.value;
    const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
    return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
}

function showCrudToast(message, isError = false) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = `toast${isError ? ' error' : ''}`;
    toast.setAttribute('role', isError ? 'alert' : 'status');
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    window.setTimeout(() => {
        toast.classList.remove('show');
        window.setTimeout(() => toast.remove(), 250);
    }, 3200);
}

function showEmailFailureNote() {
    const toast = document.querySelector('.toast:not(.error)');
    if (!toast) return;

    const note = document.createElement('small');
    note.className = 'email-failure-note';
    note.textContent = 'Note: confirmation email could not be sent.';
    toast.appendChild(note);
}

document.querySelectorAll('.crud-action-form').forEach((form) => {
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (form.dataset.processing === 'true') return;
        form.dataset.processing = 'true';

        const submitButton = form.querySelector('button[type="submit"]');
        const formToken = form.querySelector('[name="csrfmiddlewaretoken"]');
        if (submitButton) submitButton.disabled = true;
        setCrudLoading(true, 'Updating faculty account...');

        try {
            const response = await fetch(form.action, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': formToken ? formToken.value : getCsrfToken(),
                },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Unable to complete the request.');
            }

            showCrudToast(data.message || 'Request completed successfully.');
            const emailFailed = data.email_sent === false;
            if (emailFailed) {
                showEmailFailureNote();
            }
            window.setTimeout(() => window.location.reload(), emailFailed ? 3000 : 1100);
        } catch (error) {
            setCrudLoading(false);
            showCrudToast(error.message || 'Unable to complete the request.', true);
            form.dataset.processing = 'false';
            if (submitButton) submitButton.disabled = false;
        }
    });
});

function setScheduleUploadStatus(message, isError = false) {
    if (!scheduleUploadStatus) return;
    scheduleUploadStatus.textContent = message;
    scheduleUploadStatus.className = `calendar-sync-status${isError ? ' error' : ''}`;
}

function closeSchedulePreview() {
    if (schedulePreviewModal) schedulePreviewModal.classList.add('hidden');
}

function renderSchedulePreview(rows) {
    if (!schedulePreviewBody || !schedulePreviewTable || !schedulePreviewEmpty || !schedulePreviewHead) return;
    schedulePreviewHead.innerHTML = '';
    schedulePreviewColumns.forEach((column) => {
        const th = document.createElement('th');
        th.textContent = column.label;
        schedulePreviewHead.appendChild(th);
    });
    const uploaderHeader = document.createElement('th');
    uploaderHeader.textContent = 'Uploader';
    schedulePreviewHead.appendChild(uploaderHeader);
    schedulePreviewBody.innerHTML = '';
    rows.forEach((row) => {
        const tr = document.createElement('tr');
        schedulePreviewColumns.map((column) => row[column.key] || '').concat(
            row.uploader_label || 'Uploader unknown',
        ).forEach((value) => {
            const td = document.createElement('td');
            td.textContent = value;
            tr.appendChild(td);
        });
        schedulePreviewBody.appendChild(tr);
    });
    schedulePreviewEmpty.classList.toggle('hidden', rows.length > 0);
    schedulePreviewTable.classList.toggle('hidden', rows.length === 0);
    if (schedulePreviewCount) schedulePreviewCount.textContent = `${rows.length} row${rows.length === 1 ? '' : 's'}`;
    if (deleteUploadedScheduleButton) deleteUploadedScheduleButton.disabled = rows.length === 0;
}

schedulePreviewSearch?.addEventListener('input', () => {
    const query = schedulePreviewSearch.value.trim().toLowerCase();
    renderSchedulePreview(schedulePreviewRows.filter((row) => Object.values(row)
        .some((value) => String(value ?? '').toLowerCase().includes(query))));
});

function selectFacultySchedule(button) {
    selectedFacultyId = button.dataset.facultyId || '';
    selectedFacultyUploadUrl = button.dataset.uploadUrl || '';
    selectedFacultyPreviewUrl = button.dataset.previewUrl || '';
    selectedFacultyDeleteUrl = button.dataset.deleteUrl || '';
    if (schedulePreviewFaculty) {
        schedulePreviewFaculty.textContent = `Uploaded schedule for ${button.dataset.facultyName || 'selected faculty'}`;
    }
}

async function viewFacultySchedulePreview(button) {
    selectFacultySchedule(button);
    if (schedulePreviewModal) schedulePreviewModal.classList.remove('hidden');
    renderSchedulePreview([]);
    schedulePreviewRows = [];
    setScheduleUploadStatus('Loading uploaded schedule...');
    setCrudLoading(true, 'Loading uploaded schedule...');
    try {
        const response = await fetch(selectedFacultyPreviewUrl, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Unable to load the uploaded schedule.');
        schedulePreviewColumns = data.template_columns || [];
        schedulePreviewRows = data.preview || [];
        if (schedulePreviewSearch) schedulePreviewSearch.value = '';
        renderSchedulePreview(schedulePreviewRows);
        setScheduleUploadStatus(
            data.preview && data.preview.length
                ? `${data.preview.length} uploaded schedule row(s).`
                : 'No uploaded schedule found for this faculty member.',
        );
    } catch (error) {
        setScheduleUploadStatus(error.message, true);
    } finally {
        setCrudLoading(false);
    }
}

document.querySelectorAll('.upload-faculty-schedule-btn').forEach((button) => {
    button.addEventListener('click', () => {
        selectFacultySchedule(button);
        if (schedulePreviewFaculty) {
            schedulePreviewFaculty.textContent = `Upload schedule for ${button.dataset.facultyName || 'selected faculty'}`;
        }
        renderSchedulePreview([]);
        setScheduleUploadStatus('');
        if (scheduleFileInput) {
            scheduleFileInput.value = '';
            scheduleFileInput.click();
        }
    });
});

document.querySelectorAll('.view-faculty-schedule-preview-btn').forEach((button) => {
    button.addEventListener('click', () => viewFacultySchedulePreview(button));
});

if (deleteUploadedScheduleButton) {
    deleteUploadedScheduleButton.addEventListener('click', async () => {
        if (!selectedFacultyDeleteUrl || deleteUploadedScheduleButton.disabled) return;
        if (!window.confirm('Delete the uploaded schedule for this faculty member? This will not remove consultation events.')) return;

        deleteUploadedScheduleButton.disabled = true;
        setCrudLoading(true, 'Deleting uploaded schedule...');
        try {
            const response = await fetch(selectedFacultyDeleteUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCsrfToken(),
                },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Unable to delete the uploaded schedule.');
            }
            renderSchedulePreview([]);
            setScheduleUploadStatus(data.message || 'Uploaded schedule deleted.');
            showCrudToast(data.message || 'Uploaded schedule deleted.');
        } catch (error) {
            showCrudToast(error.message || 'Unable to delete the uploaded schedule.', true);
            deleteUploadedScheduleButton.disabled = false;
        } finally {
            setCrudLoading(false);
        }
    });
}

if (schedulePreviewClose) schedulePreviewClose.addEventListener('click', closeSchedulePreview);
if (schedulePreviewModal) {
    schedulePreviewModal.addEventListener('click', (event) => {
        if (event.target === schedulePreviewModal) closeSchedulePreview();
    });
}

if (scheduleFileInput) {
    scheduleFileInput.addEventListener('change', async () => {
        const file = scheduleFileInput.files[0];
        if (!file || !selectedFacultyId || !selectedFacultyUploadUrl) {
            setScheduleUploadStatus('Unable to identify the selected faculty member.', true);
            return;
        }
        if (schedulePreviewModal) schedulePreviewModal.classList.remove('hidden');
        if (!file.name.toLowerCase().endsWith('.csv')) {
            setScheduleUploadStatus('Please choose a .csv file.', true);
            return;
        }
        const syncToGoogle = window.confirm(
            "Do you want this schedule to also be reflected in this faculty's Google Calendar?",
        );
        const formData = new FormData();
        formData.append('file', file);
        formData.append('sync_to_google', syncToGoogle ? 'true' : 'false');
        setScheduleUploadStatus('Validating and saving schedule...');
        setCrudLoading(true, 'Uploading faculty schedule...');
        try {
            const response = await fetch(
                selectedFacultyUploadUrl,
                {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() },
                    body: formData,
                },
            );
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const details = (data.errors || [data.error || 'Unable to upload schedule.']).join(' ');
                throw new Error(details);
            }
            schedulePreviewColumns = data.template_columns || schedulePreviewColumns;
            schedulePreviewRows = data.preview || [];
            renderSchedulePreview(schedulePreviewRows);
            const calendarSync = data.calendar_sync || {};
            const syncMessage = calendarSync.status === 'synced'
                ? ` ${calendarSync.synced_count} event(s) also synced to Google Calendar.`
                : calendarSync.status === 'not_connected'
                    ? ` ${calendarSync.message || 'Google Calendar is not connected.'}`
                    : calendarSync.status === 'failed'
                        ? ` Google Calendar sync failed: ${calendarSync.message || 'Unable to sync.'}`
                        : '';
            setScheduleUploadStatus(
                `${data.message || 'Schedule uploaded successfully.'}${syncMessage}`,
                calendarSync.status === 'failed',
            );
        } catch (error) {
            setScheduleUploadStatus(error.message, true);
        } finally {
            setCrudLoading(false);
            scheduleFileInput.value = '';
        }
    });
}
