document.addEventListener('DOMContentLoaded', () => {
    // --- Office Location Editing ---
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

        saveBtn.addEventListener('click', () => {
            const newLocation = locationInput.value;
            locationText.textContent = newLocation;

            locationText.classList.remove('hidden');
            editBtn.classList.remove('hidden');

            locationInput.classList.add('hidden');
            saveBtn.classList.add('hidden');

            // Here you would typically send the newLocation to a server
            console.log('New office location saved:', newLocation);
        });
    }

    // --- Biography Editing ---
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

        saveBtn.addEventListener('click', () => {
            bioText.textContent = bioInput.value;

            bioText.classList.remove('hidden');
            editBtn.classList.remove('hidden');

            bioInput.classList.add('hidden');
            saveBtn.classList.add('hidden');
        });
    }

    // --- Google Calendar Integration ---
    const calendarStatus = document.getElementById('calendar-status');
    const connectBtn = document.getElementById('calendar-connect-btn');
    const disconnectBtn = document.getElementById('calendar-disconnect-btn');

    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

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
        }
    }

    if (connectBtn && disconnectBtn && calendarStatus) {
        connectBtn.addEventListener('click', () => {
            window.location.href = '/faculty/calendar/connect/';
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
            }
        });

        const isConnected = !disconnectBtn.classList.contains('hidden');
        setCalendarConnected(isConnected);
    }
});
