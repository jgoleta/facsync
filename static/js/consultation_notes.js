(function () {
  "use strict";

  const noteSelector = "[data-note-clamp]";
  const inputSelector = "[data-note-input]";

  function initializeCounter(input) {
    if (input.dataset.noteCounterReady === "true") return;
    const counter = input.parentElement?.querySelector("[data-note-counter]");
    if (!counter) return;

    const update = () => {
      const limit = input.maxLength;
      counter.textContent = `${input.value.length}/${limit}`;
    };
    input.addEventListener("input", update);
    update();
    input.dataset.noteCounterReady = "true";
  }

  function initializeClamp(note) {
    if (note.dataset.noteClampReady === "true") return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "consultation-note-toggle";
    button.textContent = "Show more";
    button.setAttribute("aria-expanded", "false");
    button.hidden = true;
    note.insertAdjacentElement("afterend", button);

    button.addEventListener("click", () => {
      const expanded = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(expanded));
      button.textContent = expanded ? "Show less" : "Show more";
      note.classList.toggle("is-collapsed", !expanded);
    });

    note.dataset.noteClampReady = "true";
    note._refreshNoteClamp = () => {
      const wasExpanded = button.getAttribute("aria-expanded") === "true";
      note.classList.remove("is-collapsed");
      const fullHeight = note.getBoundingClientRect().height;
      note.classList.add("is-collapsed");
      const collapsedHeight = note.getBoundingClientRect().height;
      const needsToggle = note.textContent.trim() !== "" && fullHeight > collapsedHeight + 1;

      if (!needsToggle) {
        note.classList.remove("is-collapsed");
        button.hidden = true;
        button.setAttribute("aria-expanded", "false");
        button.textContent = "Show more";
        return;
      }

      button.hidden = false;
      button.setAttribute("aria-expanded", String(wasExpanded));
      button.textContent = wasExpanded ? "Show less" : "Show more";
      note.classList.toggle("is-collapsed", !wasExpanded);
    };
    note._refreshNoteClamp();
  }

  function refresh(root = document) {
    if (root.matches?.(inputSelector)) initializeCounter(root);
    if (root.matches?.(noteSelector)) initializeClamp(root);
    root.querySelectorAll?.(inputSelector).forEach(initializeCounter);
    root.querySelectorAll?.(noteSelector).forEach(initializeClamp);
    document.querySelectorAll(`${noteSelector}[data-note-clamp-ready="true"]`).forEach((note) => {
      note._refreshNoteClamp?.();
    });
  }

  function clearClamp(note) {
    note.removeAttribute("data-note-clamp");
    note.classList.remove("consultation-note", "is-collapsed");
    delete note.dataset.noteClampReady;
    const toggle = note.nextElementSibling;
    if (toggle?.classList.contains("consultation-note-toggle")) toggle.remove();
  }

  window.FacSyncConsultationNotes = { refresh, clearClamp };

  document.addEventListener("DOMContentLoaded", () => {
    refresh();
    const observer = new MutationObserver((records) => {
      records.forEach((record) => {
        record.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) refresh(node);
        });
        if (record.type === "characterData") refresh(record.target.parentElement || document);
      });
    });
    observer.observe(document.body, { childList: true, characterData: true, subtree: true });
    window.addEventListener("resize", () => refresh());
    document.fonts?.ready.then(() => refresh());
  });
})();
