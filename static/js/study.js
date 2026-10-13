// Test screen: turn the card, measure the time, keyboard and the legend of the buttons.
(function () {
  const LEGEND_KEY = "vokie.legendSeen";

  let card = null;
  let flipped = false;
  let sending = false;
  let phaseStart = 0;
  let paused = 0; // time the page was hidden in the current phase (ms)
  let hiddenSince = null;
  let thinkMs = null;

  function now() {
    return performance.now();
  }

  function phaseTime() {
    return Math.round(now() - phaseStart - paused);
  }

  // A new card is on the screen: start measuring the thinking time
  function start() {
    card = document.getElementById("card");
    flipped = false;
    sending = false;
    thinkMs = null;
    phaseStart = now();
    paused = 0;
    // Foreign → native: the foreign word is the question, so it is read at once. The browser
    // allows it only after the user clicked on the page (so not for the very first card).
    if (card && card.dataset.direction === "F2N") {
      autoplay();
    }
  }

  // Read the word or the sentence by itself, as chosen in the settings
  function autoplay() {
    const what = card.dataset.autoplay;
    if (!what) {
      return;
    }
    const visible = "[data-speak='" + what + "']:not([hidden])";
    const speak = card.querySelector(visible) || card.querySelector("[data-speak='word']:not([hidden])");
    if (speak) {
      playAudio(speak);
    }
  }

  // Foreign → native shows 🔊 from the start; native → foreign only after turning the card
  function canSpeak() {
    return card && (flipped || card.dataset.direction === "F2N");
  }

  function flip() {
    if (!card || flipped) {
      return;
    }
    flipped = true;
    thinkMs = phaseTime();
    card.querySelector(".card-back").hidden = false;
    card.querySelectorAll(".after-flip").forEach(function (element) {
      element.hidden = false;
    });
    card.querySelector(".card-show").hidden = true;
    card.querySelector(".ratings").hidden = false;
    fitMeanings();
    // Native → foreign: the foreign word is the answer, read it now. The flip comes from a
    // click or a key, so the browser allows the sound.
    if (card.dataset.direction !== "F2N") {
      autoplay();
    }
    // Now measure the time until the rating
    phaseStart = now();
    paused = 0;
  }

  // Meanings from the dictionary: show as many as fit on one line and "+N" for the rest.
  // It can be measured only when the back of the card is visible.
  function fitMeanings() {
    const row = card && card.querySelector(".meaning-row");
    if (!row || row.dataset.open) {
      return;
    }
    const items = Array.from(row.querySelectorAll(".meaning"));
    const more = row.querySelector(".meaning-more");
    items.forEach(function (item) {
      item.hidden = false;
      item.classList.remove("last-shown");
    });
    more.hidden = true;
    const firstTop = items[0].getBoundingClientRect().top;
    function onFirstLine(element) {
      return element.getBoundingClientRect().top < firstTop + 2;
    }
    if (items.every(onFirstLine)) {
      return;
    }
    // Hide words from the end until the rest and "+N" fit on the first line
    more.hidden = false;
    let hidden = 0;
    for (let index = items.length - 1; index > 0; index--) {
      items[index].hidden = true;
      items[index].classList.remove("last-shown");
      items[index - 1].classList.add("last-shown");
      hidden += 1;
      more.textContent = "+" + hidden;
      if (onFirstLine(more) && items.every((item) => item.hidden || onFirstLine(item))) {
        break;
      }
    }
  }

  // Phone turned or window resized: the line has another width
  window.addEventListener("resize", function () {
    if (flipped) {
      fitMeanings();
    }
  });

  function fillTimes(form) {
    form.elements.think_ms.value = thinkMs === null ? "" : thinkMs;
    form.elements.decide_ms.value = phaseTime();
  }

  // Pause the clock while the phone is locked or another app is open
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      hiddenSince = now();
    } else if (hiddenSince !== null) {
      paused += now() - hiddenSince;
      hiddenSince = null;
    }
  });

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-action='flip']")) {
      flip();
    }
    // "+3" under the answer shows the other meanings from the dictionary
    const more = event.target.closest("[data-action='more-meanings']");
    if (more) {
      const row = more.closest(".meaning-row");
      row.dataset.open = "1";
      row.querySelectorAll(".meaning").forEach(function (item) {
        item.hidden = false;
        item.classList.remove("last-shown");
      });
      more.hidden = true;
    }
  });

  // Times go with the rating; used by HTMX and by a normal form submit
  document.addEventListener(
    "submit",
    function (event) {
      if (event.target.matches(".ratings")) {
        fillTimes(event.target);
      }
    },
    true,
  );
  document.addEventListener("htmx:configRequest", function (event) {
    const form = event.detail.elt.closest && event.detail.elt.closest(".ratings");
    if (form) {
      event.detail.parameters.think_ms = thinkMs === null ? "" : thinkMs;
      event.detail.parameters.decide_ms = phaseTime();
      sending = true;
    }
  });
  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id === "card") {
      start();
    }
  });
  document.addEventListener("htmx:responseError", function () {
    sending = false;
  });

  document.addEventListener("keydown", function (event) {
    if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }
    if (event.target.closest("input, textarea, select")) {
      return;
    }
    if (event.key === " ") {
      // Space turns the card instead of scrolling or pressing a focused button
      event.preventDefault();
      flip();
      return;
    }
    // E opens the edit of the word
    if (event.key.toLowerCase() === "e") {
      event.preventDefault();
      editTerm();
      return;
    }
    // P plays the word, V reads the sentence
    const speakKinds = { p: "word", v: "sentence" };
    const kind = speakKinds[event.key.toLowerCase()];
    if (canSpeak() && kind) {
      const speak = card.querySelector("[data-speak='" + kind + "']:not([hidden])");
      if (speak) {
        event.preventDefault();
        playAudio(speak);
      }
      return;
    }
    if (flipped && !sending && card) {
      const button = card.querySelector(".rating[data-hotkey='" + event.key + "']");
      if (button) {
        event.preventDefault();
        button.click();
      }
    }
  });

  // ✏️: edit the word of the shown card; saving (or not) comes back to the same card
  function editTerm() {
    const shown = document.getElementById("card");
    if (shown && shown.dataset.editUrl) {
      window.location.href = shown.dataset.editUrl;
    }
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-action='edit-term']")) {
      editTerm();
    }
  });

  // Legend
  function setLegend(visible) {
    const legend = document.getElementById("legend");
    if (legend) {
      legend.hidden = !visible;
    }
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-action='close-legend']")) {
      setLegend(false);
      try {
        localStorage.setItem(LEGEND_KEY, "1");
      } catch (error) {
        // Storage can be blocked, the legend then comes again next time
      }
    } else if (event.target.closest("[data-action='toggle-legend']")) {
      const legend = document.getElementById("legend");
      setLegend(legend && legend.hidden);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    start();
    let seen = false;
    try {
      seen = localStorage.getItem(LEGEND_KEY) === "1";
    } catch (error) {
      seen = false;
    }
    setLegend(!seen);
  });
})();
