# Vendored for the documents' Send button

- `modern-screenshot.js` - modern-screenshot 4.7.0 (MIT,
  `modern-screenshot-LICENSE.txt`), `dist/index.js` from npm. It draws a
  document with the browser's own rendering (an SVG foreignObject), with the
  page's embedded font carried along, so the picture matches the screen.
- `jspdf.umd.min.js` - jsPDF 4.2.1 (MIT, `jspdf-LICENSE.txt`), from npm. It
  puts those pictures on Letter pages in a PDF file.

Both unchanged except that their source-map comments were removed. A
document loads them only when Send is pressed (`LIBRARIES` in
`../send-pdf.js`), so the documents stay one self-contained file until then.

Until 2026-10-01 this held html2pdf.js, whose html2canvas redraws text
itself: on the sent copy numbers lost their lining figures, underlines
crossed the letters and "2026" came out as "20 26".
