# Vendored for the documents' Send button

`html2pdf.bundle.min.js` is html2pdf.js 0.10.2 (MIT, `html2pdf-LICENSE.txt`;
it bundles jsPDF and html2canvas, whose licenses are in
`html2pdf.bundle.min.js.LICENSE.txt`), from npm, unchanged except that its
source-map comment was removed. A document loads it only when Send is
pressed (`SEND_PDF` in `../generate_print_lease.py`), so the documents stay
one self-contained file until then.
