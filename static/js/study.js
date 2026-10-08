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
  }

  function flip() {
    if (!card || flipped) {
      return;
    }
    flipped = true;
    thinkMs = phaseTime();
    card.querySelector(".card-back").hidden = false;
    card.querySelector(".card-show").hidden = true;
    card.querySelector(".ratings").hidden = false;
    // Now measure the time until the rating
    phaseStart = now();
    paused = 0;
  }

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
    if (flipped && !sending && card) {
      const button = card.querySelector(".rating[data-hotkey='" + event.key + "']");
      if (button) {
        event.preventDefault();
        button.click();
      }
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
