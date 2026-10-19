// controllers/templates.js — named layout templates: select, save, apply, delete
// (F11-B, T4/T5).
//
// DI factory (R14): ``createTemplates({store, bus, config})`` -> ``{refresh}``.
// LEAF module — never imports main. The pure reshape lives in
// ``templates-core.js``; this module owns only the DOM and the three REST calls.
//
// Apply reuses the EXISTING path: write the four store keys, emit
// ``indicator:changed`` (main rebuilds) + ``layout:loaded`` (object tree
// re-renders). main.rebuild() then calls indicators.saveLayout(), so the chart's
// own layout PUT persists it. No new bus event, no new store key, no new write
// path (#68).
import { templateToStore, storeToTemplate } from "../templates-core.js";
import { buildIndicators } from "./indicators.js";

export function createTemplates({ store, bus, config }) {
  const select = document.getElementById("template-select");
  const applyBtn = document.getElementById("template-apply");
  const saveBtn = document.getElementById("template-save");
  const deleteBtn = document.getElementById("template-delete");
  const status = document.getElementById("template-status");
  const dialog = document.getElementById("template-dialog");
  const nameInput = document.getElementById("template-name");
  const errorEl = document.getElementById("template-error");

  if (!select || !dialog) return { refresh: function () {} };

  let templates = [];

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function announce(text) {
    if (status) status.textContent = text;
  }

  function selected() {
    const id = parseInt(select.value, 10);
    return templates.find(function (t) { return t.id === id; }) || null;
  }

  function syncButtons() {
    const has = selected() !== null;
    if (applyBtn) applyBtn.disabled = !has;
    if (deleteBtn) deleteBtn.disabled = !has;
    if (saveBtn) saveBtn.disabled = false;
  }

  function render() {
    select.textContent = "";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = templates.length ? "—" : "No templates";
    select.appendChild(blank);

    templates.forEach(function (template) {
      const option = document.createElement("option");
      option.value = String(template.id);
      option.textContent = template.name;
      select.appendChild(option);
    });

    select.disabled = templates.length === 0;
    syncButtons();
  }

  function refresh() {
    return fetch(config.urls.templates)
      .then(function (response) {
        if (!response.ok) throw new Error("templates " + response.status);
        return response.json();
      })
      .then(function (body) {
        templates = (body && body.templates) || [];
        render();
      })
      .catch(function () {
        templates = [];
        render();
        announce("Could not load templates");
      });
  }

  // --- Save as... -----------------------------------------------------------

  function showError(message) {
    if (!errorEl) return;
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function clearError() {
    if (!errorEl) return;
    errorEl.textContent = "";
    errorEl.hidden = true;
  }

  function save() {
    const name = (nameInput ? nameInput.value : "").trim();
    const entries = storeToTemplate(buildIndicators, store.get());
    fetch(config.urls.templates, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ name: name, indicators: entries }),
    })
      .then(function (response) {
        if (response.ok) return response.json();
        return response.json().then(function (body) {
          // Keep the dialog open on failure: writing to a closed dialog is the
          // F10 bug (an invisible error).
          showError((body && body.error) || "Could not save the template");
          throw new Error("save failed");
        });
      })
      .then(function (created) {
        dialog.close();
        announce('Template "' + created.name + '" saved');
        return refresh();
      })
      .catch(function () { /* the inline error already explains it */ });
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      clearError();
      if (nameInput) nameInput.value = "";
      dialog.showModal();
    });
  }

  // Validate on SUBMIT, not on close: a whitespace-only name passes the native
  // ``required`` check, so the dialog would already be closed (and the error
  // invisible) if we validated in the close handler — the F10 bug.
  const form = dialog.querySelector("form");
  if (form) {
    form.addEventListener("submit", function (event) {
      // The Cancel button is also a submit (value="cancel"): let it close.
      const submitter = event.submitter;
      if (submitter && submitter.value === "cancel") return;
      const name = (nameInput ? nameInput.value : "").trim();
      if (!name) {
        event.preventDefault(); // keep the dialog open so the error is visible
        showError("Name is required");
        if (nameInput) nameInput.focus();
        return;
      }
      save();
    });
  }

  // --- Apply ----------------------------------------------------------------

  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      const template = selected();
      if (!template) return;
      const next = templateToStore(template.indicators);
      store.set({
        indicators: next.indicators,
        params: next.params,
        styles: next.styles,
        indicatorVisible: next.indicatorVisible,
      });
      bus.emit("indicator:changed"); // main rebuilds + saveLayout()
      bus.emit("layout:loaded", { indicators: template.indicators });
      announce('Template "' + template.name + '" applied');
    });
  }

  // --- Delete ---------------------------------------------------------------

  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      const template = selected();
      if (!template) return;
      fetch(config.urls.templates + "/" + template.id, {
        method: "DELETE",
        headers: { "X-CSRFToken": csrfToken() },
      })
        .then(function (response) {
          if (!response.ok) throw new Error("delete " + response.status);
          announce('Template "' + template.name + '" deleted');
          return refresh();
        })
        .catch(function () {
          announce("Could not delete the template");
        });
    });
  }

  if (select) select.addEventListener("change", syncButtons);

  refresh();
  return { refresh: refresh };
}
