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
  // The sentence of the chosen meaning goes into the empty sentence fields ("upravit" opens them);
  // a sentence the user wrote is never overwritten
  const sentence = form.querySelector("[name='context_sentence']");
  const sentenceNative = form.querySelector("[name='context_sentence_native']");
  if (sentence && button.dataset.sentence && !sentence.value.trim() && !sentenceNative.value.trim()) {
    sentence.value = button.dataset.sentence;
    sentenceNative.value = button.dataset.sentenceNative || "";
    // Remember what was filled in, so a change of the foreign word can take it away again
    sentence.dataset.autofilled = sentence.value;
    sentenceNative.dataset.autofilled = sentenceNative.value;
    updateMoreSummary(form);
  }
  // The suggestions disappear after a choice; the row keeps its height
  const row = button.closest(".suggest-row");
  if (row) {
    row.replaceChildren();
  }
});

// The line under the word form (instead of "Více"): what is in the sentence and note fields
function updateMoreSummary(form) {
  const summary = form.querySelector("[data-more-summary]");
  if (!summary) {
    return;
  }
  const plain = (text) => text.replace(/[{}]/g, "").trim();
  const sentence = plain(form.querySelector("[name='context_sentence']").value);
  const native = plain(form.querySelector("[name='context_sentence_native']").value);
  const note = form.querySelector("[name='note']").value.trim();
  let text = summary.dataset.empty;
  if (sentence) {
    text = "„" + sentence + "“" + (native ? " · " + native : "");
  } else if (note) {
    text = summary.dataset.note;
  }
  summary.querySelector(".more-preview").textContent = text;
  summary.querySelector(".more-edit").hidden = !sentence && !note;
}

document.addEventListener("input", function (event) {
  if (event.target.matches("[name='context_sentence'], [name='context_sentence_native'], [name='note']")) {
    updateMoreSummary(event.target.closest("form"));
  }
});

// Another foreign word: the sentence filled in from a suggestion belongs to the old word
// (impose → trinket), so it goes away. A sentence the user wrote or changed stays.
document.addEventListener("input", function (event) {
  if (!event.target.matches("[name='foreign']")) {
    return;
  }
  const form = event.target.closest("form");
  let removed = false;
  form.querySelectorAll("[name='context_sentence'], [name='context_sentence_native']").forEach(function (field) {
    if (field.dataset.autofilled !== undefined) {
      if (field.value === field.dataset.autofilled) {
        field.value = "";
        removed = true;
      }
      delete field.dataset.autofilled;
    }
  });
  if (removed) {
    updateMoreSummary(form);
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

// Pronunciation (button 🔊, templates/_speak.html): the voice of the browser reads the word
// or the sentence.
const speech = window.speechSynthesis || null;
let voices = [];

// Which variant of a language sounds best (American English is the most common in series)
const PREFERRED_LANG = { en: "en-us", es: "es-es" };
// Names of voices that usually sound natural (online voices of Google and Microsoft)
const GOOD_VOICE = /google|natural|online|neural/i;

function voiceLang(voice) {
  return voice.lang.toLowerCase().replace("_", "-");
}

function voiceFor(lang) {
  const matching = voices.filter(function (voice) {
    return voiceLang(voice).split("-")[0] === lang;
  });
  if (!matching.length) {
    return null;
  }
  const preferred = PREFERRED_LANG[lang];
  return (
    matching.find((voice) => voiceLang(voice) === preferred && GOOD_VOICE.test(voice.name)) ||
    matching.find((voice) => GOOD_VOICE.test(voice.name)) ||
    matching.find((voice) => voiceLang(voice) === preferred) ||
    matching[0]
  );
}

// Buttons for the voice of the browser come hidden; show them when the browser can speak at
// all. Some browsers report their voices late or with odd language codes, so a missing voice
// for the language does not hide the button: the browser then chooses a voice by itself.
function showSpeechButtons() {
  document.querySelectorAll("[data-speak-text]").forEach(function (button) {
    button.hidden = !speech;
  });
}

function loadVoices() {
  voices = speech ? speech.getVoices() : [];
  showSpeechButtons();
}

if (speech) {
  // Some browsers (Chrome) load the voices later
  speech.addEventListener("voiceschanged", loadVoices);
}
document.addEventListener("DOMContentLoaded", loadVoices);
// A new card or list came (after an outerHTML swap the old target is gone, so look everywhere)
document.addEventListener("htmx:afterSwap", function () {
  showSpeechButtons();
});

function stopPlaying() {
  if (speech) {
    speech.cancel();
  }
  document.querySelectorAll(".speak.speaking").forEach(function (button) {
    button.classList.remove("speaking");
  });
}

function playAudio(button) {
  stopPlaying();
  button.classList.add("speaking");
  const done = function () {
    button.classList.remove("speaking");
  };

  if (!speech) {
    done();
    return;
  }
  const lang = button.dataset.lang;
  const voice = voiceFor(lang);
  const utterance = new SpeechSynthesisUtterance(button.dataset.speakText);
  if (voice) {
    utterance.voice = voice;
  }
  // Without a known voice the language alone tells the browser how to read it
  utterance.lang = voice ? voice.lang : PREFERRED_LANG[lang] || lang;
  // A bit slower than normal, it is for learning
  utterance.rate = 0.9;
  utterance.addEventListener("end", done);
  utterance.addEventListener("error", done);
  speech.speak(utterance);
}

document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-action='play-audio']");
  if (button) {
    playAudio(button);
  }
});

// End of a test: put the example from the dictionary into the two sentence fields
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-action='use-example']");
  if (!button) {
    return;
  }
  const form = button.closest("form");
  form.querySelector("[name='context_sentence']").value = button.dataset.text;
  form.querySelector("[name='context_sentence_native']").value = button.dataset.translation;
  form.querySelector("[name='context_sentence']").focus();
});

// "Teď ne": hide the sentence task (it can come again after another test)
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-action='hide-task']");
  if (button) {
    button.closest(".sentence-task").remove();
  }
});

// "+N" in front of the coloured dots of answers: show the older ones (and the link to the history)
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-action='more-dots']");
  if (!button) {
    return;
  }
  const row = button.closest(".dots-row");
  row.querySelectorAll(".dot[hidden], .dots-history[hidden]").forEach(function (element) {
    element.hidden = false;
  });
  button.remove();
});

// Cards "Co ti nejde": a click or Enter / Space turns the card (not a click on the link)
function flipHardWord(card) {
  const flipped = card.classList.toggle("flipped");
  card.setAttribute("aria-pressed", flipped ? "true" : "false");
}

document.addEventListener("click", function (event) {
  const card = event.target.closest("[data-action='flip-hard-word']");
  if (card && !event.target.closest("a")) {
    flipHardWord(card);
  }
});

document.addEventListener("keydown", function (event) {
  const card = event.target.closest && event.target.closest("[data-action='flip-hard-word']");
  if (card && event.target === card && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    flipHardWord(card);
  }
});

// "/" jumps into the search field (on the dashboard and the search page); not while typing
// in a field
document.addEventListener("keydown", function (event) {
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) {
    return;
  }
  if (event.target.closest("input, textarea, select, [contenteditable]")) {
    return;
  }
  const field = document.querySelector("[data-search-input]");
  if (field) {
    event.preventDefault();
    field.focus();
    field.select();
  }
});

// Today on the dashboard: a click on a number shows its last 7 days in the chart under them
document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-today-metric]");
  if (!button) {
    return;
  }
  const section = button.closest(".today");
  section.querySelectorAll("[data-today-metric]").forEach(function (item) {
    item.setAttribute("aria-selected", item === button ? "true" : "false");
  });
  section.querySelectorAll("[data-today-chart]").forEach(function (chart) {
    chart.hidden = chart.dataset.todayChart !== button.dataset.todayMetric;
  });
});

// The account menu in the bar closes after a click somewhere else
document.addEventListener("click", function (event) {
  document.querySelectorAll("details.dropdown[open]").forEach(function (menu) {
    if (!menu.contains(event.target)) {
      menu.removeAttribute("open");
    }
  });
});

// Light / dark look from the account menu; "auto" follows the system. Kept in this browser
// only (localStorage), the page sets it before drawing (base.html).
function showThemeChoice() {
  let theme = "auto";
  try {
    theme = localStorage.getItem("vocaboo.theme") || "auto";
  } catch (error) {}
  document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
    button.setAttribute("aria-pressed", button.dataset.themeChoice === theme ? "true" : "false");
  });
}

document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-theme-choice]");
  if (!button) {
    return;
  }
  const theme = button.dataset.themeChoice;
  if (theme === "auto") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
  try {
    if (theme === "auto") {
      localStorage.removeItem("vocaboo.theme");
    } else {
      localStorage.setItem("vocaboo.theme", theme);
    }
  } catch (error) {
    // Storage can be blocked, the look then lasts only for this page
  }
  showThemeChoice();
  showThemeColor();
});

document.addEventListener("DOMContentLoaded", showThemeChoice);

// The colour of the phone's top bar follows the look: indigo by day, dark at night. The
// meta tags in base.html follow the system; a look chosen in the menu wins over it.
const THEME_COLORS = {light: "#5b4bc4", dark: "#13171f"};

function showThemeColor() {
  const chosen = document.documentElement.dataset.theme;
  document.querySelectorAll('meta[name="theme-color"]').forEach(function (meta) {
    if (!meta.dataset.media) {
      meta.dataset.media = meta.getAttribute("media");
    }
    if (chosen) {
      meta.removeAttribute("media");
      meta.setAttribute("content", THEME_COLORS[chosen]);
    } else {
      // Back to the system: each tag for its own look again
      meta.setAttribute("media", meta.dataset.media);
      meta.setAttribute("content", meta.dataset.media.includes("dark") ? THEME_COLORS.dark : THEME_COLORS.light);
    }
  });
}

document.addEventListener("DOMContentLoaded", showThemeColor);

// Installing the app on the home screen. Android and Chrome / Edge on a computer send
// beforeinstallprompt, then our button opens their own "Install?" window. An iPhone has no
// such window, and neither have some Android browsers (e.g. Firefox), so there the button
// shows the steps (dialogs #install-guide-ios and #install-guide-android in base.html).
let installPrompt = null;

function isInstalled() {
  return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
}

function isIOS() {
  // An iPad says it is a Mac, but a Mac has no touch screen
  return /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function isAndroid() {
  return /Android/.test(navigator.userAgent);
}

// Steps for a phone whose browser has no install window, or null
function installGuide() {
  if (isIOS()) {
    return document.getElementById("install-guide-ios");
  }
  if (isAndroid()) {
    return document.getElementById("install-guide-android");
  }
  return null;
}

function installDismissed() {
  try {
    return localStorage.getItem("vocaboo.installDismissed") === "1";
  } catch (error) {
    return false;
  }
}

function dismissInstall() {
  try {
    localStorage.setItem("vocaboo.installDismissed", "1");
  } catch (error) {
    // Storage can be blocked, the offer then comes back on the next page
  }
}

function showInstall() {
  const canInstall = !isInstalled() && (installPrompt !== null || installGuide() !== null);
  document.querySelectorAll("[data-install-item]").forEach(function (item) {
    item.hidden = !canInstall;
  });
  // The offer on the overview only on a phone or tablet, and only until "Not now"
  const phone = window.matchMedia("(pointer: coarse)").matches;
  document.querySelectorAll("[data-install-card]").forEach(function (card) {
    card.hidden = !(canInstall && phone && !installDismissed());
  });
}

window.addEventListener("beforeinstallprompt", function (event) {
  // Our own button instead of the browser's bar at the bottom
  event.preventDefault();
  installPrompt = event;
  showInstall();
});

window.addEventListener("appinstalled", function () {
  installPrompt = null;
  dismissInstall();
  showInstall();
});

document.addEventListener("click", function (event) {
  if (event.target.closest("[data-install]")) {
    event.target.closest("details.dropdown")?.removeAttribute("open");
    if (installPrompt) {
      const prompt = installPrompt;
      // The window can be opened only once, after that the browser sends a new event
      installPrompt = null;
      prompt.prompt();
      prompt.userChoice.then(function (choice) {
        if (choice.outcome === "accepted") {
          dismissInstall();
        }
        showInstall();
      });
    } else if (installGuide()) {
      installGuide().showModal();
      // The browser never says whether the steps were done; the offer on the overview has
      // done its job, the menu item stays
      dismissInstall();
      showInstall();
    }
    return;
  }
  if (event.target.closest("[data-install-dismiss]")) {
    dismissInstall();
    showInstall();
    return;
  }
  if (event.target.closest("[data-install-close]")) {
    event.target.closest("dialog")?.close();
  }
});

document.addEventListener("DOMContentLoaded", showInstall);

// Password fields: an eye button inside the field shows the password and hides it again
const EYE_OPEN =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYE_CLOSED =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/></svg>';

function showPasswordState(button, shown) {
  button.innerHTML = shown ? EYE_CLOSED : EYE_OPEN;
  button.setAttribute("aria-pressed", shown ? "true" : "false");
  button.setAttribute("aria-label", shown ? gettext("Hide password") : gettext("Show password"));
  button.title = button.getAttribute("aria-label");
}

function addPasswordEyes() {
  document.querySelectorAll("input[type='password']").forEach(function (input) {
    if (input.parentElement.classList.contains("password-field")) {
      return;
    }
    const wrap = document.createElement("span");
    wrap.className = "password-field";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "password-eye";
    showPasswordState(button, false);
    wrap.appendChild(button);
  });
}

document.addEventListener("click", function (event) {
  const button = event.target.closest(".password-eye");
  if (!button) {
    return;
  }
  const input = button.parentElement.querySelector("input");
  const shown = input.type === "password";
  input.type = shown ? "text" : "password";
  showPasswordState(button, shown);
  // Back to the field, so typing goes on
  input.focus();
});

document.addEventListener("DOMContentLoaded", addPasswordEyes);

// Words from a topic: "select all on this page" and the number of ticked words in the button
function showTopicCount(form) {
  const ticked = form.querySelectorAll(".topic-words input[name='sense']:checked").length;
  const button = form.querySelector("[data-topic-add]");
  if (button) {
    button.querySelector("[data-topic-count]").textContent = ticked;
    button.disabled = ticked === 0;
  }
}

document.addEventListener("change", function (event) {
  const form = event.target.closest("form");
  if (!form || !form.querySelector("[data-topic-add]")) {
    return;
  }
  if (event.target.matches("[data-action='topic-select-all']")) {
    form.querySelectorAll(".topic-words input[name='sense']:not(:disabled)").forEach(function (box) {
      box.checked = event.target.checked;
    });
  }
  showTopicCount(form);
});


// A word from "Odložené" fills the form: move the page only when the section "Nové slovíčko"
// is not all on the screen, and then only so far that its heading shows
function showNewWordSection() {
  const section = document.getElementById("new-word");
  if (!section) {
    return;
  }
  const box = section.getBoundingClientRect();
  if (box.top >= 0 && box.bottom <= window.innerHeight) {
    return;
  }
  section.scrollIntoView({ block: "start" });
}

// From the list "Odložené": the deck page opens with ?later=<id>
if (new URLSearchParams(window.location.search).has("later")) {
  showNewWordSection();
}

// From the card on the deck page: HTMX puts the filled form in place
let laterFilling = false;
document.addEventListener("click", function (event) {
  if (event.target.closest("[data-later-fill]")) {
    laterFilling = true;
  }
});
document.addEventListener("htmx:afterSettle", function () {
  if (laterFilling) {
    laterFilling = false;
    showNewWordSection();
  }
});
