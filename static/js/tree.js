// Dashboard tree: move decks by drag and drop.
//
// SortableJS does the dragging itself (holding on phones, the copy under the finger), but it
// never moves rows while dragging: rows jumping away made it hard to hit a folder. Instead the
// place under the pointer is shown and used when the deck is dropped:
//   middle of a row          -> into that deck (row is highlighted)
//   top / bottom of a row    -> before / after that deck (a line is shown)
// The server checks every move; after it the tree is loaded again, so icons and counts fit.
//
// The browser remembers which folders are open or closed (localStorage), so the tree looks
// the same after a test or a new page. Folders without a choice keep what the server sent:
// the first level open, deeper folders closed.
(function () {
  // Part of the row height at the top and at the bottom that means "before" / "after"
  const EDGE = 0.3;
  const MARKS = ["drop-into", "drop-before", "drop-after"];
  // Open folders by deck id: {"12": true, "15": false}
  const FOLDERS_KEY = "vocaboo.openFolders";
  // How long a deck must be held over a closed folder before the folder opens
  const OPEN_DELAY = 700;

  let dragged = null; // <li> being dragged
  let target = null; // {item: <li>, zone: "into" | "before" | "after"}
  let openTimer = null;

  function loadFolders() {
    try {
      return JSON.parse(localStorage.getItem(FOLDERS_KEY)) || {};
    } catch (error) {
      return {};
    }
  }

  function saveFolders(folders) {
    try {
      localStorage.setItem(FOLDERS_KEY, JSON.stringify(folders));
    } catch (error) {}
  }

  function folders() {
    return document.querySelectorAll("#deck-tree li.deck-node > details");
  }

  // Open and close the folders as the user left them; forget decks that are gone
  function restoreFolders() {
    const saved = loadFolders();
    const kept = {};
    folders().forEach(function (folder) {
      const id = folder.parentElement.dataset.deckId;
      if (id in saved) {
        folder.open = saved[id];
        kept[id] = saved[id];
      }
    });
    saveFolders(kept);
  }

  // Remember every open and close (also the ones while dragging)
  function onToggle(event) {
    const folder = event.target;
    if (!folder.matches || !folder.matches("#deck-tree li.deck-node > details")) {
      return;
    }
    const saved = loadFolders();
    saved[folder.parentElement.dataset.deckId] = folder.open;
    saveFolders(saved);
  }

  function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function showMessage(text) {
    const message = document.getElementById("tree-message");
    if (!message) {
      return;
    }
    message.textContent = text || "";
    message.hidden = !text;
  }

  function setTarget(next) {
    if (target) {
      target.item.classList.remove(...MARKS);
    }
    clearTimeout(openTimer);
    target = next;
    if (target) {
      target.item.classList.add("drop-" + target.zone);
      // Held over a closed folder: open it, so the deck can go between its children
      const closed = target.item.querySelector(":scope > details:not([open])");
      if (target.zone === "into" && closed) {
        openTimer = setTimeout(function () {
          closed.open = true;
        }, OPEN_DELAY);
      }
    }
  }

  function pointer(event) {
    const touch = (event.touches && event.touches[0]) || (event.changedTouches && event.changedTouches[0]);
    return touch ? { x: touch.clientX, y: touch.clientY } : { x: event.clientX, y: event.clientY };
  }

  // Find the deck row under the pointer and which part of it (the dragged copy lets clicks through)
  function onPointerMove(event) {
    if (!dragged) {
      return;
    }
    const point = pointer(event);
    const under = document.elementFromPoint(point.x, point.y);
    const row = under && under.closest("#deck-tree .deck-row");
    const item = row && row.closest("li.deck-node");
    // A deck cannot go next to or into itself, nor into its own child decks
    if (!item || dragged.contains(item)) {
      setTarget(null);
      return;
    }
    const box = row.getBoundingClientRect();
    let zone = "into";
    if (point.y < box.top + box.height * EDGE) {
      zone = "before";
    } else if (point.y > box.bottom - box.height * EDGE) {
      // Under an open folder the next row is its first child, so "after" means "into" there
      zone = item.querySelector(":scope > details[open]") ? "into" : "after";
    }
    if (!target || target.item !== item || target.zone !== zone) {
      setTarget({ item: item, zone: zone });
    }
  }

  // Load the dashboard again and put the new tree in place of the old one
  async function reloadTree() {
    const response = await fetch(window.location.href, { credentials: "same-origin" });
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    const fresh = page.getElementById("deck-tree");
    const current = document.getElementById("deck-tree");
    if (fresh && current) {
      current.replaceWith(fresh);
      setUp();
    }
  }

  async function save(item, parentId, index) {
    const data = new FormData();
    data.append("parent", parentId);
    data.append("index", index);
    // UI texts are Czech only for now
    try {
      const response = await fetch(item.dataset.placeUrl, {
        method: "POST",
        body: data,
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken() },
      });
      if (response.ok) {
        return "";
      }
      const answer = await response.json().catch(function () {
        return {};
      });
      return answer.error || "Přesun se nepodařil.";
    } catch (problem) {
      return "Přesun se nepodařil, zkontroluj připojení.";
    }
  }

  // Parent id and index for the server from the place under the pointer
  function placeFor(drop) {
    if (drop.zone === "into") {
      const open = drop.item.querySelector(":scope > details[open]");
      // Into an open folder at the top (where the user sees it), else after the last child
      return { parent: drop.item.dataset.deckId, index: open ? 0 : 100000 };
    }
    const list = drop.item.parentElement;
    const siblings = Array.from(list.children).filter(function (li) {
      return li !== dragged;
    });
    const index = siblings.indexOf(drop.item) + (drop.zone === "after" ? 1 : 0);
    return { parent: list.dataset.parentId, index: index };
  }

  async function onEnd() {
    document.removeEventListener("mousemove", onPointerMove);
    document.removeEventListener("touchmove", onPointerMove);
    document.body.classList.remove("deck-dragging");
    const drop = target;
    const item = dragged;
    setTarget(null);
    dragged = null;
    if (!drop) {
      return;
    }
    const place = placeFor({ item: drop.item, zone: drop.zone });
    showMessage(await save(item, place.parent, place.index));
    // Also after an error: the deck goes back to where the server has it
    await reloadTree();
  }

  function setUp() {
    restoreFolders();
    if (typeof Sortable === "undefined") {
      return;
    }
    document.querySelectorAll("#deck-tree ul.deck-tree").forEach(function (list) {
      Sortable.create(list, {
        group: "decks",
        draggable: "li.deck-node",
        // Own drag code instead of the browser's: works the same with links and on phones
        forceFallback: true,
        fallbackTolerance: 5,
        fallbackOnBody: true,
        // The dragged copy goes a bit under the pointer, so the row under it stays visible
        fallbackOffset: { x: -12, y: -28 },
        // On a touch screen the deck must be held a moment, so the page can still scroll
        delay: 300,
        delayOnTouchOnly: true,
        onStart: function (event) {
          dragged = event.item;
          showMessage("");
          document.body.classList.add("deck-dragging");
          document.addEventListener("mousemove", onPointerMove);
          document.addEventListener("touchmove", onPointerMove, { passive: true });
        },
        // Never move rows while dragging
        onMove: function () {
          return false;
        },
        onEnd: onEnd,
      });
    });
  }

  // The toggle event does not bubble, so it is caught on the way down
  document.addEventListener("toggle", onToggle, true);
  // The script is deferred, so the tree is already in the page
  setUp();
})();
