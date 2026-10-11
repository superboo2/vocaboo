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

// Buttons for the voice of the browser come hidden; show those the browser can read
function showSpeechButtons() {
  document.querySelectorAll("[data-speak-text]").forEach(function (button) {
    button.hidden = !voiceFor(button.dataset.lang);
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

  const voice = speech && voiceFor(button.dataset.lang);
  if (!voice) {
    done();
    return;
  }
  const utterance = new SpeechSynthesisUtterance(button.dataset.speakText);
  utterance.voice = voice;
  utterance.lang = voice.lang;
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
