const addFacultyBtn = document.getElementById('addFacultyBtn');
        const facultyModal = document.getElementById('facultyModal');
        const closeFacultyModal = document.getElementById('closeFacultyModal');
        const cancelFacultyModal = document.getElementById('cancelFacultyModal');
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
        cancelFacultyModal.addEventListener('click', closeFacultyModalFn);
        facultyModal.addEventListener('click', (event) => {
            if (event.target === facultyModal) {
                closeFacultyModalFn();
            }
        });

        facultyForm.addEventListener('submit', (event) => {
            event.preventDefault();
            closeFacultyModalFn();
        });