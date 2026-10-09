// Small helpers for all pages

// Translation suggestion: put it into the translation field of the word form
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-action='use-suggestion']");
  if (!button) {
    return;
  }
  const form = button.closest("form");
  const native = form.querySelector("[name='native']");
  native.value = button.dataset.translation;
  // Let the duplicate check see the new value
  native.dispatchEvent(new Event("input", { bubbles: true }));
  native.focus();
  // The suggestions disappear after a choice; the row keeps its height
  const row = button.closest(".suggest-row");
  if (row) {
    row.replaceChildren();
  }
});

// Choosing words in the word list of a deck (for moving them to another deck)
function updateSelection(list) {
  const boxes = list.querySelectorAll(".select-box");
  const chosen = list.querySelectorAll(".select-box:checked").length;
  list.querySelector("[data-select-count]").textContent = chosen ? "(" + chosen + ")" : "";
  list.querySelector(".select-bar [type='submit']").disabled = chosen === 0;
  list.querySelector("[data-action='select-all']").checked = chosen === boxes.length;
}

document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-action='toggle-select']");
  if (!button) {
    return;
  }
  const list = button.closest("#term-list");
  const selecting = list.classList.toggle("selecting");
  if (!selecting) {
    list.querySelectorAll("input[type='checkbox']").forEach(function (box) {
      box.checked = false;
    });
  }
  updateSelection(list);
});

document.addEventListener("change", function (event) {
  const list = event.target.closest("#term-list");
  if (!list || event.target.type !== "checkbox") {
    return;
  }
  if (event.target.dataset.action === "select-all") {
    list.querySelectorAll(".select-box").forEach(function (box) {
      box.checked = event.target.checked;
    });
  }
  updateSelection(list);
});
