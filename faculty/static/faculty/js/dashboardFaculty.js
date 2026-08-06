document.addEventListener('DOMContentLoaded', () => {
    // --- Consultation Request Filtering ---
    const filterButtons = document.querySelectorAll('.filter-btn');
    const requestItems = document.querySelectorAll('.request-item');

    if (filterButtons.length > 0 && requestItems.length > 0) {
        filterButtons.forEach(button => {
            button.addEventListener('click', () => {
                // Update active button
                filterButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');

                const filter = button.dataset.filter;

                // Filter request items
                requestItems.forEach(item => {
                    if (filter === 'all' || item.dataset.status === filter) {
                        item.style.display = 'flex';
                    } else {
                        item.style.display = 'none';
                    }
                });
            });
        });
    }
    console.log('Faculty dashboard script loaded.');
});