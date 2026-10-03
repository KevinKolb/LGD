/* Send: the document as a PDF, through the device's share sheet (the user,
 * 2026-10-01: "phone share sheet for now", until the site has a domain
 * and an email service of its own). Pick Mail and the PDF is already
 * attached; the address is typed in Mail, since a share sheet cannot be
 * told a recipient.
 *
 * Unlike Save, the browser's print window cannot hand its PDF to a
 * script, so this one is made in the page, from two libraries in vendor/
 * loaded only when Send is pressed: modern-screenshot draws each document
 * with the browser's own rendering and the embedded font (so the text,
 * numbers and underlines look as on screen), at the printed width; pageCuts
 * here cuts that picture into Letter pages - each as full as it will go,
 * only between lines of text, never through a signature block, each later
 * document starting a new page - and jsPDF puts them in the file with the
 * same "Page X of Y" lines. Its pages are pictures of the text and may end
 * a line away from the printout's; Print and Save remain exact.
 *
 * The share needs a fresh tap (browsers allow a share only straight after
 * one), so the popup says "Making the PDF..." and then offers Share. Where
 * the browser cannot share a file (most Windows and Linux browsers), it
 * offers Download instead.
 *
 * Inlined into every document by DOC_BUTTONS through a Python string, so:
 * plain ES5, no backslashes, and no font of its own. */
(function () {
  "use strict";

  var LIBRARIES = ["vendor/modern-screenshot.js", "vendor/jspdf.umd.min.js"];
  var loading = null;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function loadLibraries() {
    if (!loading) {
      loading = Promise.all(LIBRARIES.map(loadScript)).then(function () {
        return { shot: window.modernScreenshot, jsPDF: window.jspdf.jsPDF };
      }, function () {
        loading = null;
        throw new Error("Sending could not start. Check the connection and try again.");
      });
    }
    return loading;
  }

  function el(tag, style, text) {
    var node = document.createElement(tag);
    if (style) { node.setAttribute("style", style); }
    if (text) { node.textContent = text; }
    return node;
  }

  var ACCENT = "#1f5d4c";
  var BUTTON = "font:inherit;border-radius:999px;padding:8px 18px;cursor:pointer;border:1px solid " + ACCENT + ";";

  function popup() {
    var overlay = el("div", "position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;" +
      "align-items:center;justify-content:center;z-index:3000;");
    overlay.className = "send-pdf-popup";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    var box = el("div", "background:#fff;color:#1c1c1a;border-radius:8px;padding:24px 22px 20px;" +
      "max-width:340px;width:calc(100% - 48px);font-size:16px;line-height:1.4;");
    var title = el("h2", "margin:0 0 12px;font-size:18px;", "Send");
    var message = el("p", "margin:0 0 18px;", "Getting " + documentName() + " ready...");
    var row = el("div", "display:flex;gap:10px;justify-content:flex-end;");
    var cancel = el("button", BUTTON + "background:#fff;color:" + ACCENT + ";", "Cancel");
    cancel.type = "button";
    row.appendChild(cancel);
    box.appendChild(title);
    box.appendChild(message);
    box.appendChild(row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    var closed = false;
    function close() {
      closed = true;
      if (overlay.parentNode) { overlay.parentNode.removeChild(overlay); }
    }
    cancel.addEventListener("click", close);
    return {
      isClosed: function () { return closed; },
      say: function (text) { message.textContent = text; },
      offer: function (label, action) {
        var go = el("button", BUTTON + "background:" + ACCENT + ";color:#fff;", label);
        go.type = "button";
        go.addEventListener("click", function () { action(close); });
        row.appendChild(go);
        go.focus();
      },
      close: close
    };
  }

  // What goes into the PDF: the sheets now showing, in order.
  function sheets() {
    return Array.prototype.filter.call(document.querySelectorAll(".sheet"), function (sheet) {
      return !sheet.hidden && sheet.offsetParent !== null;
    });
  }

  function company() {
    var heading = document.querySelector(".sheet:not([hidden]) h1.company");
    return heading ? heading.textContent.replace(/[ ]+/g, " ").trim() : "";
  }

  // What the page holds, in words: its title up to " - " ("Lease and
  // security deposit - 1534 Camp St." is "the lease and security
  // deposit"). The buttons and popups name the document, never the file
  // type (the user, 2026-10-01).
  function documentName() {
    var name = (document.title || "").split(" - ")[0].trim();
    return name ? "the " + name.toLowerCase() : "this document";
  }

  // Today as 20261001, on the end of a saved file's name (the user,
  // 2026-10-01).
  function dateStamp() {
    var now = new Date();
    function two(n) { return (n < 10 ? "0" : "") + n; }
    return String(now.getFullYear()) + two(now.getMonth() + 1) + two(now.getDate());
  }

  function fileName() {
    var name = (document.title || "Document").replace(/[^A-Za-z0-9 .,&()-]+/g, " ").replace(/[ ]+/g, " ").trim();
    return name + " " + dateStamp() + ".pdf";
  }

  // The sheets, laid out as on paper: 6.8in of text inside the 0.85in
  // margins the PDF adds, no screen zoom, no shadows, no screen-only notes.
  var CAPTURE_STYLE = [
    ".pdf-capture { width: 6.8in; background: #fff; }",
    ".pdf-capture .sheet { width: auto !important; min-height: 0 !important; margin: 0 !important;",
    "  padding: 0 !important; box-shadow: none !important; zoom: 1 !important; }",
    ".pdf-capture .footer-note, .pdf-capture .float-buttons { display: none !important; }"
  ].join(" ");
  var PAGE_HEIGHT_IN = 11 - 2 * 0.85;   // Letter less the printed margins
  var MARGIN_IN = 0.85;
  var KEEP_WHOLE = "h1, h2, h3, tr, img, input, .sig-row, .sig-line, .execution-block, .field-row";

  // Where each page ends, in CSS pixels from the top of the holder: as far
  // down the page as fits, but only between two lines of text, never inside
  // anything kept whole (a signature block, a row of fields).
  function pageCuts(holder) {
    var top = holder.getBoundingClientRect().top;
    var spans = [];
    function add(rect) {
      if (rect.height > 0) { spans.push([rect.top - top, rect.bottom - top]); }
    }
    var walker = document.createTreeWalker(holder, NodeFilter.SHOW_TEXT, null);
    var range = document.createRange();
    var node;
    while ((node = walker.nextNode())) {
      if (!node.nodeValue.trim()) { continue; }
      range.selectNodeContents(node);
      Array.prototype.forEach.call(range.getClientRects(), add);
    }
    Array.prototype.forEach.call(holder.querySelectorAll("*"), function (element) {
      var style = getComputedStyle(element);
      if (style.display === "none") { return; }
      if (element.matches(KEEP_WHOLE) || style.breakInside === "avoid" ||
          style.pageBreakInside === "avoid" || style.display.indexOf("inline") === 0) {
        add(element.getBoundingClientRect());
      }
    });
    var total = holder.getBoundingClientRect().height;
    var pagePx = PAGE_HEIGHT_IN * 96;

    function free(y) {
      for (var i = 0; i < spans.length; i++) {
        if (spans[i][0] < y - 0.5 && y + 0.5 < spans[i][1]) { return false; }
      }
      return true;
    }

    var cuts = [0];
    var at = 0;
    while (at < total - 1) {
      var limit = at + pagePx;
      var cut;
      if (limit >= total) {
        cut = total;
      } else {
        cut = at;
        spans.forEach(function (span) {
          [span[0], span[1]].forEach(function (y) {
            if (y > cut && y <= limit && free(y)) { cut = y; }
          });
        });
        if (cut <= at + 1) { cut = limit; }   // something taller than a page
      }
      cuts.push(cut);
      at = cut;
    }
    return cuts;
  }

  // iPhones refuse a canvas over about 16.7 million pixels, so each
  // document is drawn as its own picture, at twice screen resolution
  // unless that would pass the limit (a 7-page lease comes close).
  var MAX_CANVAS_PIXELS = 16000000;

  // One document's pages: [{ image, heightIn }], cut by pageCuts. The
  // copy sits off screen inside a holder, so the picture is of the copy
  // alone, not of where it was put.
  function documentPages(libs, sheet) {
    var holder = el("div", "position:absolute;left:-10000px;top:0;");
    var capture = el("div");
    capture.className = "pdf-capture";
    var copy = sheet.cloneNode(true);
    copy.removeAttribute("id");
    capture.appendChild(copy);
    holder.appendChild(capture);
    document.body.appendChild(holder);
    function remove() {
      if (holder.parentNode) { holder.parentNode.removeChild(holder); }
    }
    var box = capture.getBoundingClientRect();
    var cuts = pageCuts(capture);
    var scale = Math.min(2, Math.sqrt(MAX_CANVAS_PIXELS / (box.width * box.height)));
    return libs.shot.domToCanvas(capture, {
      scale: scale,
      width: Math.ceil(box.width),
      height: Math.ceil(box.height),
      backgroundColor: "#ffffff"
    }).then(function (canvas) {
      remove();
      var ratio = canvas.width / Math.ceil(box.width);
      var pages = [];
      for (var i = 0; i + 1 < cuts.length; i++) {
        var from = Math.round(cuts[i] * ratio);
        var height = Math.max(1, Math.min(canvas.height, Math.round(cuts[i + 1] * ratio)) - from);
        var slice = document.createElement("canvas");
        slice.width = canvas.width;
        slice.height = height;
        var context = slice.getContext("2d");
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, slice.width, slice.height);
        context.drawImage(canvas, 0, from, canvas.width, height, 0, 0, canvas.width, height);
        pages.push({ image: slice.toDataURL("image/jpeg", 0.85), heightIn: height / ratio / 96 });
      }
      canvas.width = 0;   // let the phone have its memory back
      canvas.height = 0;
      return pages;
    }, function (error) {
      remove();
      throw error;
    });
  }

  function makePdf(libs) {
    var style = el("style", null, CAPTURE_STYLE);
    document.head.appendChild(style);
    function cleanUp() {
      if (style.parentNode) { style.parentNode.removeChild(style); }
    }
    var header = company();
    var pages = [];
    var fontsReady = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
    // One document after another, each starting a new page.
    var done = fontsReady;
    sheets().forEach(function (sheet) {
      done = done.then(function () {
        return documentPages(libs, sheet).then(function (more) {
          pages = pages.concat(more);
        });
      });
    });
    return done.then(function () {
      var pdf = new libs.jsPDF({ unit: "in", format: "letter", orientation: "portrait" });
      pages.forEach(function (page, i) {
        if (i > 0) { pdf.addPage(); }
        pdf.addImage(page.image, "JPEG", MARGIN_IN, MARGIN_IN, 8.5 - 2 * MARGIN_IN, page.heightIn);
        // "LGD (Lower Garden District) Properties, Inc. - Page 1 of 8", top and
        // bottom, counting the whole file as a printout does.
        var line = (header ? header + " - " : "") + "Page " + (i + 1) + " of " + pages.length;
        pdf.setFont("times", "normal");
        pdf.setFontSize(9);
        pdf.setTextColor(68, 68, 68);
        pdf.text(line, 4.25, 0.5, { align: "center" });
        pdf.text(line, 4.25, 10.6, { align: "center" });
      });
      cleanUp();
      return new File([pdf.output("blob")], fileName(), { type: "application/pdf" });
    }, function (error) {
      cleanUp();
      throw error;
    });
  }

  function download(file) {
    var url = URL.createObjectURL(file);
    var link = el("a");
    link.href = url;
    link.download = file.name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }

  function send() {
    var box = popup();
    loadLibraries().then(makePdf).then(function (file) {
      if (box.isClosed()) { return; }
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        box.say("Ready. Tap Share, then choose Mail - " + documentName() + " will be attached.");
        box.offer("Share", function (close) {
          navigator.share({ files: [file], title: file.name }).then(close, function (error) {
            if (error && error.name === "AbortError") { return; }
            box.say("It could not be shared: " + (error && error.message ? error.message : error));
          });
        });
      } else {
        box.say("This browser cannot attach a file to an email itself. Download " + documentName() + ", then attach it to an email.");
        box.offer("Download", function (close) {
          download(file);
          close();
        });
      }
    }, function (error) {
      if (!box.isClosed()) {
        box.say(error && error.message ? error.message : "It could not be made ready to send.");
      }
    });
  }

  window.LGD = window.LGD || {};
  window.LGD.sendPdf = send;

  document.addEventListener("click", function (event) {
    var target = event.target.closest ? event.target.closest("[data-send-pdf]") : null;
    if (!target) { return; }
    event.preventDefault();
    send();
  });
})();
