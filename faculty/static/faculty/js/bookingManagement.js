document.addEventListener('DOMContentLoaded', () => {
    const queueList = document.getElementById('queueList');
    const queueCount = document.getElementById('queueCount');
    const refreshQueueBtn = document.getElementById('refreshQueueBtn');
    const walkInToggle = document.getElementById('walkInToggle');
    const walkInStatus = document.getElementById('walkInStatus');
    const availabilityLabel = document.getElementById('availabilityLabel');
    const availabilityDot = document.getElementById('availabilityDot');
    const queueCountLarge = document.getElementById('queueCountLarge');
    const lastUpdated = document.getElementById('lastUpdated');

    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>'"]/g, (character) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
        }[character]));
    }

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
            item.innerHTML = `
                <div class="queue-summary">
                    <p class="student-name">${escapeHtml(student.student_name)}</p>
                    <p class="student-meta">Position ${student.position} · Queued ${new Date(student.joined_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</p>
                    ${student.student_message ? `<p class="student-note">${escapeHtml(student.student_message)}</p>` : ''}
                    <div class="student-status"><span class="status-badge status-${called ? 'called' : 'pending'}">${called ? 'Notified' : 'Waiting'}</span></div>
                </div>
                <div class="queue-item-actions">
                    <button type="button" class="btn-notify" data-id="${escapeHtml(student.queue_id)}" ${called ? 'disabled' : ''}>${called ? 'Student Notified' : 'Notify Student'}</button>
                    <button type="button" class="btn-mark-complete" data-id="${escapeHtml(student.queue_id)}">Mark Complete</button>
                </div>
            `;
            queueList.appendChild(item);
        });
    }

    async function loadQueue() {
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
        }
    }

    if (walkInToggle) {
        walkInToggle.addEventListener('change', async () => {
            const enabled = walkInToggle.checked;
            walkInToggle.disabled = true;
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
            } catch (error) {
                walkInToggle.checked = !enabled;
                walkInStatus.textContent = error.message;
            } finally {
                walkInToggle.disabled = false;
            }
        });
    }

    async function updateQueue(queueId, action) {
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
    }

    queueList.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-id]');
        if (!button) return;
        button.disabled = true;
        try {
            await updateQueue(button.dataset.id, button.classList.contains('btn-notify') ? 'notify' : 'complete');
        } catch (error) {
            walkInStatus.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });

    refreshQueueBtn.addEventListener('click', loadQueue);
    loadQueue();
    window.setInterval(loadQueue, 10000);
});
