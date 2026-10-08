// Small helpers for all pages

// "Je to jiný význam": open the extra fields of the word form and go to the meaning field
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-action='other-meaning']");
  if (!button) {
    return;
  }
  const form = button.closest("form");
  const more = form.querySelector("details");
  const hint = form.querySelector("[name='meaning_hint']");
  if (more) {
    more.open = true;
  }
  if (hint) {
    hint.focus();
  }
});
