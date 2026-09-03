document.addEventListener('DOMContentLoaded', () => {
    const facultyFeedback = window.facultyFeedback;
    // --- Status Controls ---

    const statusButtons = document.querySelectorAll('.status-btn');
    const updateStatusButton = document.getElementById('updateStatusBtn');
    const statusMessage = document.getElementById('statusMessage');
    const statusExpiresAt = document.getElementById('statusExpiresAt');
    const liveStatusIndicator = document.getElementById('liveStatusIndicator');
    const liveStatusIcon = document.getElementById('liveStatusIcon');
    const liveStatusLabel = document.getElementById('liveStatusLabel');
    const liveStatusNote = document.getElementById('liveStatusNote');
    const statusFeedback = document.getElementById('statusFeedback');
    const updateStatusLabel = document.getElementById('updateStatusLabel');
    const statusModeLabel = document.getElementById('statusModeLabel');
    const useCalendarStatusBtn = document.getElementById('useCalendarStatusBtn');
    const refreshConsultationsButton = document.getElementById('refreshConsultations');
    const completedModal = document.getElementById('completedConsultationsModal');
    const openCompletedModalButton = document.getElementById('openCompletedConsultations');
    const closeCompletedModalButton = document.getElementById('closeCompletedConsultations');
    const statusIcons = {
        available: '✓',
        busy: '◷',
        virtual: '⌁',
        'on-leave': '☕',
        unavailable: '×',
    };
    let selectedStatus = document.querySelector('.status-btn.active')?.dataset.status || 'available';

    if (statusExpiresAt?.dataset.currentExpiry) {
        const expiry = new Date(statusExpiresAt.dataset.currentExpiry);
        const localExpiry = new Date(expiry.getTime() - expiry.getTimezoneOffset() * 60000);
        statusExpiresAt.value = localExpiry.toISOString().slice(0, 16);
        if (statusModeLabel) {
            statusModeLabel.textContent = `Manual override is active until ${expiry.toLocaleString([], {
                dateStyle: 'medium', timeStyle: 'short',
            })}`;
        }
    }

    // Retrieve the CSRF token required by dashboard API requests.
    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

    // Convert the API status value into the value used by the status buttons.
    function statusButtonValue(status) {
        return status === 'virtual_only' ? 'virtual' : status === 'on_leave' ? 'on-leave' : status;
    }

    // Update the dashboard status controls with the latest API response.
    function updateStatusPresentation(data) {
        const buttonStatus = statusButtonValue(data.status);
        statusButtons.forEach((button) => {
            const active = button.dataset.status === buttonStatus;
            button.classList.toggle('active', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        selectedStatus = buttonStatus;
        liveStatusIndicator.className = `status-indicator ${data.status_css_class}`;
        if (liveStatusIcon) liveStatusIcon.textContent = statusIcons[buttonStatus];
        liveStatusLabel.textContent = data.label;
        liveStatusNote.textContent = data.note || 'No status note set.';
        if (statusModeLabel) {
            const expiryLabel = data.expires_at
                ? ` until ${new Date(data.expires_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}`
                : '';
            statusModeLabel.textContent = data.manual_override
                ? `Manual override is active${expiryLabel}`
                : 'Status follows your calendar';
        }
        if (statusExpiresAt && !data.expires_at) statusExpiresAt.value = '';
        if (useCalendarStatusBtn) useCalendarStatusBtn.classList.toggle('hidden', !data.manual_override);
    }

    // Track which status the faculty member selected before saving it.
    statusButtons.forEach((button) => {
        button.addEventListener('click', () => {
            statusButtons.forEach((item) => item.classList.remove('active'));
            button.classList.add('active');
            statusButtons.forEach((item) => item.setAttribute('aria-pressed', item === button ? 'true' : 'false'));
            selectedStatus = button.dataset.status;
        });
    });

    // Save a manually selected faculty status and its note.
    if (updateStatusButton) {
        updateStatusButton.addEventListener('click', async () => {
            updateStatusButton.disabled = true;
            updateStatusButton.classList.add('is-saving');
            facultyFeedback?.showLoading('Updating your status...');
            if (updateStatusLabel) updateStatusLabel.textContent = 'Saving...';
            statusFeedback.className = 'status-feedback';
            statusFeedback.textContent = '';
            try {
                const response = await fetch('/faculty/api/status/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        status: selectedStatus,
                        note: statusMessage?.value || '',
                        manual_override: true,
                        expires_at: statusExpiresAt?.value
                            ? new Date(statusExpiresAt.value).toISOString()
                            : null,
                    }),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Unable to update status.');

                updateStatusPresentation(data);
                statusFeedback.className = 'status-feedback';
                statusFeedback.textContent = '';
                if (updateStatusLabel) updateStatusLabel.textContent = 'Updated';
                window.setTimeout(() => { if (updateStatusLabel) updateStatusLabel.textContent = 'Update status'; }, 1500);
            } catch (error) {
                statusFeedback.className = 'status-feedback error';
                statusFeedback.textContent = error.message;
                facultyFeedback?.showToast(error.message, true);
                if (updateStatusLabel) updateStatusLabel.textContent = 'Update status';
            } finally {
                updateStatusButton.disabled = false;
                updateStatusButton.classList.remove('is-saving');
                facultyFeedback?.hideLoading();
            }
        });
    }

    // Return status control to the values calculated from the faculty calendar.
    if (useCalendarStatusBtn) {
        useCalendarStatusBtn.addEventListener('click', async () => {
            useCalendarStatusBtn.disabled = true;
            facultyFeedback?.showLoading('Restoring calendar status...');
            try {
                const response = await fetch('/faculty/api/status/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        note: statusMessage?.value || '',
                        manual_override: false,
                        expires_at: null,
                    }),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Unable to restore calendar status.');
                updateStatusPresentation(data);
                statusFeedback.className = 'status-feedback';
                statusFeedback.textContent = '';
            } catch (error) {
                statusFeedback.className = 'status-feedback error';
                statusFeedback.textContent = error.message;
                facultyFeedback?.showToast(error.message, true);
            } finally {
                useCalendarStatusBtn.disabled = false;
                facultyFeedback?.hideLoading();
            }
        });
    }

    if (liveStatusIcon) liveStatusIcon.textContent = statusIcons[selectedStatus];

    refreshConsultationsButton?.addEventListener('click', () => {
        refreshConsultationsButton.disabled = true;
        refreshConsultationsButton.classList.add('is-refreshing');
        facultyFeedback?.showLoading('Refreshing consultation requests...');
        window.location.reload();
    });

    // Show completed consultation history without leaving the dashboard.
    function setCompletedModalOpen(isOpen) {
        if (!completedModal) return;
        completedModal.classList.toggle('hidden', !isOpen);
        document.body.style.overflow = isOpen ? 'hidden' : '';
        if (isOpen) closeCompletedModalButton?.focus();
        else openCompletedModalButton?.focus();
    }

    openCompletedModalButton?.addEventListener('click', () => setCompletedModalOpen(true));
    closeCompletedModalButton?.addEventListener('click', () => setCompletedModalOpen(false));
    completedModal?.addEventListener('click', (event) => {
        if (event.target === completedModal) setCompletedModalOpen(false);
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !completedModal?.classList.contains('hidden')) {
            setCompletedModalOpen(false);
        }
    });

    document.querySelectorAll('[data-delete-completed]').forEach((button) => {
        button.addEventListener('click', async () => {
            const item = button.closest('.completed-consultation-item');
            const requestId = item?.dataset.requestId;
            if (!requestId || !window.confirm('Delete this completed consultation permanently?')) return;

            button.disabled = true;
            facultyFeedback?.showLoading('Deleting completed consultation...');
            try {
                const response = await fetch(`/faculty/api/consultations/${encodeURIComponent(requestId)}/`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() },
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.error || 'Unable to delete the consultation.');

                item.remove();
                const remaining = document.querySelectorAll('.completed-consultation-item').length;
                if (openCompletedModalButton) openCompletedModalButton.textContent = `Completed (${remaining})`;
                if (remaining === 0) {
                    document.querySelector('.completed-consultation-list')?.insertAdjacentHTML(
                        'beforeend',
                        '<li class="completed-empty-state">No completed consultations yet.</li>',
                    );
                }
                facultyFeedback?.showToast('Completed consultation deleted.');
            } catch (error) {
                button.disabled = false;
                facultyFeedback?.showToast(error.message, true);
            } finally {
                facultyFeedback?.hideLoading();
            }
        });
    });

    // --- Consultation Request Filtering and Actions ---

    // Filter visible consultation requests by their current status.
    const consultationStatusFilter = document.getElementById('consultationStatusFilter');
    const requestItems = document.querySelectorAll('.request-item');

    if (consultationStatusFilter && requestItems.length > 0) {
        consultationStatusFilter.addEventListener('change', () => {
            const filter = consultationStatusFilter.value;
            requestItems.forEach((item) => {
                if (filter === 'all' || item.dataset.status === filter) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }

    // Submit the faculty decision for an individual consultation request.
    requestItems.forEach((item) => {
        item.querySelectorAll('[data-action]').forEach((button) => {
            button.addEventListener('click', async () => {
                const requestId = item.dataset.requestId;
                const note = item.querySelector('textarea')?.value || '';
                if (!requestId) return;

                button.disabled = true;
                facultyFeedback?.showLoading('Updating consultation request...');
                try {
                    // Persist the faculty decision, then reload the real request list.
                    const response = await fetch(`/faculty/api/consultations/${encodeURIComponent(requestId)}/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCsrfToken(),
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ status: button.dataset.action, faculty_note: note }),
                    });
                    const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.error || 'Unable to update the consultation request.');
                    if (['completed', 'declined'].includes(data.status)) {
                        item.remove();
                    }
                    facultyFeedback?.showToast('Consultation request updated successfully.');
                    window.setTimeout(() => window.location.reload(), 800);
                } catch (error) {
                    button.disabled = false;
                    facultyFeedback?.showToast(error.message, true);
                } finally {
                    facultyFeedback?.hideLoading();
                }
            });
        });
    });
    console.log('Faculty dashboard script loaded.');
});
