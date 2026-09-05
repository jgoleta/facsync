document.addEventListener("DOMContentLoaded", () => {
  const collegeFilter = document.getElementById("collegeFilter");
  const facultyModal = document.getElementById("facultyModal");
  const facultyForm = document.getElementById("facultyForm");
  const loadingModal = document.getElementById("crudLoadingModal");
  const loadingMessage = document.getElementById("crudLoadingMessage");
  const removeModal = document.getElementById("removeFacultyConfirmModal");
  const removeFacultyName = document.getElementById("removeFacultyName");
  let pendingRemoveForm = null;

  function getCsrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input?.value) return input.value;
    const cookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  }

  function setLoading(isLoading, message = "Processing request...") {
    if (loadingMessage) loadingMessage.textContent = message;
    loadingModal?.classList.toggle("show", isLoading);
    document.body.setAttribute("aria-busy", isLoading ? "true" : "false");
  }

  function showFacultyToast(message, isError = false) {
    document.querySelector(".faculty-toast")?.remove();
    const toast = document.createElement("div");
    toast.className = `faculty-toast${isError ? " error" : ""}`;
    toast.setAttribute("role", isError ? "alert" : "status");
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("show"));
    window.setTimeout(() => {
      toast.classList.remove("show");
      window.setTimeout(() => toast.remove(), 250);
    }, 3200);
  }

  function filterSection(section, selectedCollege) {
    const rows = [...section.querySelectorAll(".faculty-row")];
    const normalizedCollege = selectedCollege.toLowerCase();
    let visibleCount = 0;
    rows.forEach((row) => {
      const visible =
        normalizedCollege === "all" ||
        (row.dataset.college || "").toLowerCase() === normalizedCollege;
      row.classList.toggle("hidden", !visible);
      if (visible) visibleCount += 1;
    });
    section.querySelector(".filter-empty")?.classList.toggle("hidden", visibleCount > 0);
    return visibleCount;
  }

  function applyCollegeFilter() {
    const college = collegeFilter?.value || "all";
    document.querySelectorAll("[data-faculty-section]").forEach((section) => {
      const count = filterSection(section, college);
      if (section.dataset.facultySection === "pending") {
        const countElement = document.getElementById("pendingFacultyCount");
        if (countElement) countElement.textContent = count;
      }
    });
  }

  collegeFilter?.addEventListener("change", applyCollegeFilter);
  applyCollegeFilter();

  function closeFacultyModal() {
    facultyModal?.classList.add("hidden");
    facultyForm?.reset();
  }

  document.getElementById("addFacultyBtn")?.addEventListener("click", () => {
    facultyModal?.classList.remove("hidden");
  });
  document.getElementById("closeFacultyModal")?.addEventListener("click", closeFacultyModal);
  document.getElementById("cancelFacultyInvite")?.addEventListener("click", closeFacultyModal);
  facultyModal?.addEventListener("click", (event) => {
    if (event.target === facultyModal) closeFacultyModal();
  });

  facultyForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = facultyForm.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    setLoading(true, "Sending faculty invitation...");
    try {
      const response = await fetch(facultyForm.action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCsrfToken(),
        },
        body: new FormData(facultyForm),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.success) {
        throw new Error(data.error || "Unable to create the faculty invitation.");
      }
      closeFacultyModal();
      showFacultyToast(data.message || "Faculty invitation created.");
      window.setTimeout(() => window.location.reload(), 1100);
    } catch (error) {
      setLoading(false);
      showFacultyToast(error.message || "Unable to create the faculty invitation.", true);
      if (submitButton) submitButton.disabled = false;
    }
  });

  function closeRemoveModal() {
    removeModal?.classList.add("hidden");
    pendingRemoveForm = null;
  }

  document.querySelectorAll(".remove-faculty-trigger").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      pendingRemoveForm = button.closest(".remove-faculty-form");
      if (removeFacultyName) {
        removeFacultyName.textContent =
          button.dataset.facultyName || "this faculty member";
      }
      removeModal?.classList.remove("hidden");
    });
  });
  document.getElementById("closeRemoveFacultyConfirm")?.addEventListener("click", closeRemoveModal);
  document.getElementById("cancelRemoveFaculty")?.addEventListener("click", closeRemoveModal);
  removeModal?.addEventListener("click", (event) => {
    if (event.target === removeModal) closeRemoveModal();
  });
  document.getElementById("confirmRemoveFaculty")?.addEventListener("click", () => {
    if (!pendingRemoveForm) return;
    const form = pendingRemoveForm;
    closeRemoveModal();
    form.requestSubmit();
  });

  document.querySelectorAll(".crud-action-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.dataset.processing === "true") return;
      form.dataset.processing = "true";
      const button = form.querySelector('button[type="submit"]');
      const token = form.querySelector('input[name="csrfmiddlewaretoken"]');
      if (button) button.disabled = true;
      setLoading(true, "Updating faculty account...");
      try {
        const response = await fetch(form.action, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": token?.value || getCsrfToken(),
          },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
          throw new Error(data.error || "Unable to complete the request.");
        }
        showFacultyToast(data.message || "Request completed successfully.");
        window.setTimeout(() => window.location.reload(), 1100);
      } catch (error) {
        setLoading(false);
        showFacultyToast(error.message || "Unable to complete the request.", true);
        form.dataset.processing = "false";
        if (button) button.disabled = false;
      }
    });
  });
});
