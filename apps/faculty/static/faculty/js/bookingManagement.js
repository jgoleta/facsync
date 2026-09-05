document.addEventListener('DOMContentLoaded', () => {
    const facultyFeedback = window.facultyFeedback;

    // --- Queue Helpers ---

    const queueList = document.getElementById('queueList');
    const queueCount = document.getElementById('queueCount');
    const refreshQueueBtn = document.getElementById('refreshQueueBtn');
    const walkInToggle = document.getElementById('walkInToggle');
    const walkInStatus = document.getElementById('walkInStatus');
    const availabilityLabel = document.getElementById('availabilityLabel');
    const availabilityDot = document.getElementById('availabilityDot');
    const queueCountLarge = document.getElementById('queueCountLarge');
    const lastUpdated = document.getElementById('lastUpdated');

    // Retrieve the CSRF token required by walk-in queue requests.
    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

    // Escape student-provided values before inserting them into queue markup.
    function escapeHtml(value) {
        return String(value || '').replace(/[&<>'"]/g, (character) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
        }[character]));
    }

    // --- Queue Rendering ---

    // Render the current walk-in queue and its available actions.
    function renderQueue(queue) {
        queueList.innerHTML = '';
        queueCount.textContent = queue.length;

        if (!queue.length) {
            queueList.innerHTML = '<li class="queue-item empty-state"><p>There are no students in the queue.</p></li>';
            return;
        }

        queue.forEach((student) => {
            const called = student.status === 'called';
            const item = document.createElement('li');
            item.className = 'queue-item';
            // Use explicit actions so notify, complete, and remove stay unambiguous.
            item.innerHTML = `
                <div class="queue-summary">
                    <p class="student-name">${escapeHtml(student.student_name)}</p>
                    <p class="student-meta">Position ${student.position} · Queued ${new Date(student.joined_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</p>
                    <p class="student-college">College: ${escapeHtml(student.student_college || 'Not assigned')}</p>
                    ${student.student_message ? `<p class="student-note">${escapeHtml(student.student_message)}</p>` : ''}
                    <div class="student-status"><span class="status-badge status-${called ? 'called' : 'pending'}">${called ? 'Notified' : 'Waiting'}</span></div>
                </div>
                <div class="queue-item-actions">
                    <button type="button" class="btn-notify" data-id="${escapeHtml(student.queue_id)}" data-action="notify" ${called ? 'disabled' : ''}>${called ? 'Student Notified' : 'Notify Student'}</button>
                    <button type="button" class="btn-mark-complete" data-id="${escapeHtml(student.queue_id)}" data-action="complete">Mark Complete</button>
                    <button type="button" class="btn-remove" data-id="${escapeHtml(student.queue_id)}" data-action="remove">Remove</button>
                </div>
            `;
            queueList.appendChild(item);
        });
    }

    // --- Queue API and Availability ---

    // Load the walk-in queue and refresh the availability summary.
    async function loadQueue(showLoading = false) {
        if (showLoading) facultyFeedback?.showLoading('Loading walk-in queue...');
        try {
            const response = await fetch('/faculty/api/walk-ins/');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Unable to load the queue.');
            const queue = data.queue || [];
            const isOpen = data.walk_ins_enabled;
            availabilityLabel.textContent = isOpen ? 'Accepting walk-ins' : 'Not accepting walk-ins';
            availabilityDot.className = `availability-dot ${isOpen ? 'is-open' : 'is-closed'}`;
            queueCountLarge.textContent = queue.length;
            walkInStatus.textContent = isOpen
                ? 'Students may join the queue.'
                : 'New walk-in requests are paused.';
            lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
            renderQueue(queue);
        } catch (error) {
            availabilityLabel.textContent = 'Status unavailable';
            availabilityDot.className = 'availability-dot is-checking';
            walkInStatus.textContent = error.message;
            lastUpdated.textContent = 'Unable to refresh';
            queueList.innerHTML = '<li class="queue-item empty-state"><p>Unable to load the queue.</p></li>';
            if (showLoading) facultyFeedback?.showToast(error.message, true);
        } finally {
            if (showLoading) facultyFeedback?.hideLoading();
        }
    }

    // Save whether new students may join the walk-in queue.
    if (walkInToggle) {
        walkInToggle.addEventListener('change', async () => {
            const enabled = walkInToggle.checked;
            walkInToggle.disabled = true;
            facultyFeedback?.showLoading('Updating walk-in availability...');
            try {
                const response = await fetch('/faculty/api/walk-ins/preference/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ enabled }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.error || 'Unable to update walk-in availability.');
                walkInToggle.checked = data.walk_ins_enabled;
                await loadQueue();
                facultyFeedback?.showToast('Walk-in availability updated successfully.');
            } catch (error) {
                walkInToggle.checked = !enabled;
                walkInStatus.textContent = error.message;
                facultyFeedback?.showToast(error.message, true);
            } finally {
                walkInToggle.disabled = false;
                facultyFeedback?.hideLoading();
            }
        });
    }

    // Apply an action such as notify, complete, or remove to a queue entry.
    async function updateQueue(queueId, action) {
        facultyFeedback?.showLoading('Updating queue entry...');
        try {
            const response = await fetch(`/faculty/api/walk-ins/${encodeURIComponent(queueId)}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ action }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Unable to update the queue entry.');
            await loadQueue();
        } finally {
            facultyFeedback?.hideLoading();
        }
    }

    // Handle queue actions using one delegated click listener.
    queueList.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-id]');
        if (!button) return;
        button.disabled = true;
        try {
            await updateQueue(button.dataset.id, button.dataset.action);
            facultyFeedback?.showToast('Walk-in queue updated successfully.');
        } catch (error) {
            walkInStatus.textContent = error.message;
            facultyFeedback?.showToast(error.message, true);
        } finally {
            button.disabled = false;
        }
    });

    refreshQueueBtn.addEventListener('click', () => loadQueue(true));
    loadQueue(true);
    window.setInterval(loadQueue, 10000);
});
