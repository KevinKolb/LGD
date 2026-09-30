/* Save as PDF, beside every Print button (the user, 2026-09-30: "in
 * addition to all of the print buttons add save buttons that save to pdf").
 *
 * The PDF is made by the browser's own print window, the same as Print,
 * so it is exactly the printed pages - the embedded font, the page
 * counters, the page breaks. (A PDF drawn in the page by a script library
 * would paginate on its own and lose all of that.) Save first says where
 * "Save as PDF" is on this device, then opens the print window. The
 * page's title is the suggested file name, and each page already sets it
 * ("Residential Lease - 1558 Camp St., Unit A", "Rent Register -
 * September 2026").
 *
 * Written in plain ES5 without backslashes: the printed documents carry a
 * copy of this file inlined into a Python string (DOC_BUTTONS in
 * documents/print/generate_print_lease.py), since they load nothing. */
(function () {
  "use strict";

  function steps() {
    var agent = navigator.userAgent || "";
    var ios = /iPhone|iPad|iPod/.test(agent) ||
      (/Macintosh/.test(agent) && navigator.maxTouchPoints > 1);
    if (ios) {
      return ["In the print window, tap the Share button (the square with an arrow pointing up).",
              "Tap Save to Files, choose where, and tap Save."];
    }
    if (/Android/.test(agent)) {
      return ["In the print window, tap the printer name at the top and choose Save as PDF.",
              "Tap the round PDF button, then Save."];
    }
    return ["In the print window, set Destination (or Printer) to Save as PDF.",
            "Click Save and choose where."];
  }

  function el(tag, style, text) {
    var node = document.createElement(tag);
    if (style) { node.setAttribute("style", style); }
    if (text) { node.textContent = text; }
    return node;
  }

  function openPrint() {
    var fontsReady = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
    fontsReady.then(function () { window.print(); });
  }

  function savePdf() {
    var accent = "var(--accent, #1f5d4c)";
    var overlay = el("div", "position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;" +
      "align-items:center;justify-content:center;z-index:3000;");
    overlay.className = "save-pdf-popup";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    var box = el("div", "background:#fff;color:#1c1c1a;border-radius:8px;padding:24px 22px 20px;" +
      "max-width:340px;width:calc(100% - 48px);font-size:16px;line-height:1.4;");
    box.appendChild(el("h2", "margin:0 0 12px;font-size:18px;", "Save as PDF"));
    var list = el("ol", "margin:0 0 18px;padding-left:22px;");
    steps().forEach(function (step) { list.appendChild(el("li", "margin-bottom:8px;", step)); });
    box.appendChild(list);
    var row = el("div", "display:flex;gap:10px;justify-content:flex-end;");
    var button = "font:inherit;border-radius:999px;padding:8px 18px;cursor:pointer;border:1px solid " + accent + ";";
    var cancel = el("button", button + "background:#fff;color:" + accent + ";", "Cancel");
    var go = el("button", button + "background:" + accent + ";color:#fff;", "Continue");
    cancel.type = "button";
    go.type = "button";
    row.appendChild(cancel);
    row.appendChild(go);
    box.appendChild(row);
    overlay.appendChild(box);

    function close() {
      document.removeEventListener("keydown", onKey);
      if (overlay.parentNode) { overlay.parentNode.removeChild(overlay); }
    }
    function onKey(event) {
      if (event.key === "Escape") { close(); }
    }
    cancel.addEventListener("click", close);
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) { close(); }
    });
    go.addEventListener("click", function () {
      close();
      openPrint();
    });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    go.focus();
  }

  window.LGD = window.LGD || {};
  window.LGD.savePdf = savePdf;

  // Any element marked data-save-pdf is a Save button.
  document.addEventListener("click", function (event) {
    var target = event.target.closest ? event.target.closest("[data-save-pdf]") : null;
    if (!target) { return; }
    event.preventDefault();
    savePdf();
  });
})();
