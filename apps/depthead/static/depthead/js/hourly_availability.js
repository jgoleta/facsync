(() => {
    const card = document.getElementById('hourly-availability');
    if (!card) return;
    let pending = false;
    async function refresh() {
        if (document.hidden || pending) return;
        pending = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch(card.dataset.url, {
                credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
            });
            if (!response.ok || response.redirected) throw new Error('Refresh failed');
            const data = await response.json();
            card.querySelector('[data-hourly-content]').hidden = !data.is_working_hours;
            card.querySelector('[data-hourly-closed]').hidden = data.is_working_hours;
            const values = {
                period_label: data.period_label,
                available: `${data.available_count} faculty${data.available_names.length ? ' — ' + data.available_names.join(', ') : ''}`,
                approved_count: data.approved_count,
                pending_count: data.pending_count,
            };
            for (const [key, value] of Object.entries(values)) {
                card.querySelector(`[data-hourly="${key}"]`).textContent = value;
            }
            card.querySelector('[data-hourly-error]').hidden = true;
        } catch (_) {
            card.querySelector('[data-hourly-error]').hidden = false;
        } finally {
            clearTimeout(timeout);
            pending = false;
        }
    }
    setInterval(refresh, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
