        const addFacultyBtn = document.getElementById('addFacultyBtn');
        const facultyModal = document.getElementById('facultyModal');
        const closeFacultyModal = document.getElementById('closeFacultyModal');
        const facultyForm = document.getElementById('facultyForm');

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

        facultyForm.addEventListener('submit', (event) => {
            event.preventDefault();
            closeFacultyModalFn();
        });

const scheduleFileInput = document.getElementById('facultyScheduleFile');
const schedulePreviewModal = document.getElementById('facultySchedulePreviewModal');
const schedulePreviewClose = document.getElementById('closeFacultySchedulePreview');
const schedulePreviewFaculty = document.getElementById('facultySchedulePreviewFaculty');
const scheduleUploadStatus = document.getElementById('facultyScheduleUploadStatus');
const schedulePreviewEmpty = document.getElementById('facultySchedulePreviewEmpty');
const schedulePreviewTable = document.getElementById('facultySchedulePreviewTable');
const schedulePreviewBody = document.getElementById('facultySchedulePreviewBody');
let selectedFacultyId = '';
let selectedFacultyUploadUrl = '';

function getCsrfToken() {
    const pageToken = document.querySelector('#deptheadCsrfToken input[name="csrfmiddlewaretoken"]');
    if (pageToken && pageToken.value) return pageToken.value;
    const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
    return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
}

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
}

document.querySelectorAll('.upload-faculty-schedule-btn').forEach((button) => {
    button.addEventListener('click', () => {
        selectedFacultyId = button.dataset.facultyId || '';
        selectedFacultyUploadUrl = button.dataset.uploadUrl || '';
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
            scheduleFileInput.value = '';
        }
    });
}
