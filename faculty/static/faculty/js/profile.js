document.addEventListener('DOMContentLoaded', () => {
    // --- Profile API Helpers ---

    // Retrieve the CSRF token required by profile update requests.
    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

    // Save one editable faculty profile field to the server.
    async function saveProfileField(field, value) {
        const body = new URLSearchParams({ field, value });
        const response = await fetch(window.location.pathname, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body,
        });
        if (!response.ok) {
            throw new Error('Unable to save profile changes.');
        }
        return response.json();
    }

    // --- Office Location Editing ---

    // Register controls for viewing and updating the faculty office location.
    const officeLocationGroup = document.getElementById('office-location-group');
    if (officeLocationGroup) {
        const locationText = document.getElementById('office-location-text');
        const locationInput = document.getElementById('office-location-input');
        const editBtn = document.getElementById('edit-office-btn');
        const saveBtn = document.getElementById('save-office-btn');

        editBtn.addEventListener('click', () => {
            locationText.classList.add('hidden');
            editBtn.classList.add('hidden');

            locationInput.classList.remove('hidden');
            saveBtn.classList.remove('hidden');
            locationInput.focus();
        });

        saveBtn.addEventListener('click', async () => {
            try {
                const newLocation = locationInput.value.trim();
                await saveProfileField('office_location', newLocation);
                locationText.textContent = newLocation || 'Not assigned';
                locationText.classList.remove('hidden');
                editBtn.classList.remove('hidden');
                locationInput.classList.add('hidden');
                saveBtn.classList.add('hidden');
            } catch (error) {
                window.alert(error.message);
            }
        });
    }

    // --- Biography Editing ---

    // Register controls for viewing and updating the faculty biography.
    const biographyGroup = document.getElementById('biography-group');
    if (biographyGroup) {
        const bioText = document.getElementById('biography-text');
        const bioInput = document.getElementById('biography-input');
        const editBtn = document.getElementById('edit-bio-btn');
        const saveBtn = document.getElementById('save-bio-btn');

        editBtn.addEventListener('click', () => {
            bioText.classList.add('hidden');
            editBtn.classList.add('hidden');

            bioInput.classList.remove('hidden');
            saveBtn.classList.remove('hidden');
            bioInput.focus();
        });

        saveBtn.addEventListener('click', async () => {
            try {
                const biography = bioInput.value.trim();
                await saveProfileField('biography', biography);
                bioText.textContent = biography || 'No biography added yet.';
                bioText.classList.remove('hidden');
                editBtn.classList.remove('hidden');
                bioInput.classList.add('hidden');
                saveBtn.classList.add('hidden');
            } catch (error) {
                window.alert(error.message);
            }
        });
    }

    // --- Google Calendar Integration ---
    const calendarStatus = document.getElementById('calendar-status');
    const connectBtn = document.getElementById('calendar-connect-btn');
    const disconnectBtn = document.getElementById('calendar-disconnect-btn');
    const syncToggle = document.getElementById('calendar-sync-toggle');
    const lastSync = document.getElementById('calendar-last-sync');
    const syncError = document.getElementById('calendar-sync-error');

    // Update the calendar connection controls to match the current connection state.
    function setCalendarConnected(isConnected) {
        if (isConnected) {
            calendarStatus.textContent = 'Connected';
            calendarStatus.className = 'status-connected';
            connectBtn.classList.add('hidden');
            disconnectBtn.classList.remove('hidden');
        } else {
            calendarStatus.textContent = 'Not Connected';
            calendarStatus.className = 'status-disconnected';
            connectBtn.classList.remove('hidden');
            disconnectBtn.classList.add('hidden');
            if (syncToggle) {
                syncToggle.checked = false;
                syncToggle.disabled = true;
            }
        }
    }

    if (connectBtn && disconnectBtn && calendarStatus) {
        connectBtn.addEventListener('click', () => {
            window.location.href = '/faculty/calendar/connect';
        });

        disconnectBtn.addEventListener('click', async () => {
            if (!confirm('Disconnect Google Calendar? FacSync copies will be removed, but your Google events will remain in Google Calendar.')) {
                return;
            }
            const response = await fetch('/faculty/calendar/disconnect/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
            });
            if (response.ok) {
                setCalendarConnected(false);
                if (lastSync) lastSync.textContent = 'Not synced yet';
            }
        });

        if (syncToggle) {
            syncToggle.addEventListener('change', async () => {
                const enabled = syncToggle.checked;
                syncToggle.disabled = true;
                if (syncError) {
                    syncError.textContent = '';
                    syncError.classList.add('hidden');
                }
                try {
                    const response = await fetch('/faculty/api/calendar/preference/', {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCsrfToken(),
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ sync_enabled: enabled }),
                    });
                    const data = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(data.error || 'Unable to update sync preference.');
                    if (data.last_synced_at && lastSync) {
                        lastSync.textContent = `Last synced ${new Date(data.last_synced_at).toLocaleString()}`;
                    }
                    if (data.error && syncError) {
                        syncError.textContent = data.error;
                        syncError.classList.remove('hidden');
                    }
                } catch (error) {
                    syncToggle.checked = !enabled;
                    if (syncError) {
                        syncError.textContent = error.message;
                        syncError.classList.remove('hidden');
                    }
                } finally {
                    syncToggle.disabled = false;
                }
            });
        }

        const isConnected = !disconnectBtn.classList.contains('hidden');
        setCalendarConnected(isConnected);
        if (syncToggle) syncToggle.disabled = !isConnected;
    }
});
