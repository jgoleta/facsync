        const addFacultyBtn = document.getElementById('addFacultyBtn');
        const facultyModal = document.getElementById('facultyModal');
        const closeFacultyModal = document.getElementById('closeFacultyModal');
        const facultyForm = document.getElementById('facultyForm');
        const crudLoadingModal = document.getElementById('crudLoadingModal');
        const crudLoadingMessage = document.getElementById('crudLoadingMessage');

        function setCrudLoading(isLoading, message = 'Processing request...') {
            if (!crudLoadingModal) return;
            if (crudLoadingMessage) crudLoadingMessage.textContent = message;
            crudLoadingModal.classList.toggle('show', isLoading);
            document.body.setAttribute('aria-busy', isLoading ? 'true' : 'false');
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

const scheduleFileInput = document.getElementById('facultyScheduleFile');
const schedulePreviewModal = document.getElementById('facultySchedulePreviewModal');
const schedulePreviewClose = document.getElementById('closeFacultySchedulePreview');
const schedulePreviewFaculty = document.getElementById('facultySchedulePreviewFaculty');
const scheduleUploadStatus = document.getElementById('facultyScheduleUploadStatus');
const schedulePreviewEmpty = document.getElementById('facultySchedulePreviewEmpty');
const schedulePreviewTable = document.getElementById('facultySchedulePreviewTable');
const schedulePreviewBody = document.getElementById('facultySchedulePreviewBody');
const deleteUploadedScheduleButton = document.getElementById('deleteFacultyUploadedSchedule');
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
            window.setTimeout(() => window.location.reload(), 1100);
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
    scheduleUploadStatus.className = `faculty-schedule-upload-status${isError ? ' error' : ''}`;
}

function closeSchedulePreview() {
    if (schedulePreviewModal) schedulePreviewModal.classList.add('hidden');
}

function renderSchedulePreview(rows) {
    if (!schedulePreviewBody || !schedulePreviewTable || !schedulePreviewEmpty) return;
    schedulePreviewBody.innerHTML = '';
    rows.forEach((row) => {
        const tr = document.createElement('tr');
        [
            row.event_title,
            row.short_description || '—',
            row.room_location || '—',
            row.recurring_day || 'None',
            `${row.start_month || '—'}-${row.end_month || '—'}`,
            row.start_time || '—',
            row.end_time || '—',
            row.status_type || 'Busy',
        ].forEach((value) => {
            const td = document.createElement('td');
            td.textContent = value;
            tr.appendChild(td);
        });
        schedulePreviewBody.appendChild(tr);
    });
    schedulePreviewEmpty.classList.toggle('hidden', rows.length > 0);
    schedulePreviewTable.classList.toggle('hidden', rows.length === 0);
    if (deleteUploadedScheduleButton) deleteUploadedScheduleButton.disabled = rows.length === 0;
}

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
    setScheduleUploadStatus('Loading uploaded schedule...');
    setCrudLoading(true, 'Loading uploaded schedule...');
    try {
        const response = await fetch(selectedFacultyPreviewUrl, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Unable to load the uploaded schedule.');
        renderSchedulePreview(data.preview || []);
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
        const formData = new FormData();
        formData.append('file', file);
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
            renderSchedulePreview(data.preview || []);
            setScheduleUploadStatus(data.message || 'Schedule uploaded successfully.');
        } catch (error) {
            setScheduleUploadStatus(error.message, true);
        } finally {
            setCrudLoading(false);
            scheduleFileInput.value = '';
        }
    });
}
