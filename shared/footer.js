"use strict";
/* The one footer every page in this app shares. Included as
 * <script src="/shared/footer.js"></script> just before </body>, so the
 * links only ever have to change in one place.
 *
 * Injected rather than copied into each page's HTML for the same reason
 * landlord/account.js injects the account bar: there is no template
 * engine here, and six hand-kept copies of the same markup drift. */

(function () {
  const LINKS = [
    { href: "/landlord/", text: "Landlord" },
    { href: "/applicant/", text: "Applicant" },
    { href: "/tenant/", text: "Tenant" },
    { href: "/admin/", text: "Admin" },
  ];

  const footer = document.createElement("footer");
  for (const link of LINKS) {
    const anchor = document.createElement("a");
    anchor.href = link.href;
    anchor.textContent = link.text;
    footer.append(anchor);
  }
  document.body.append(footer);
})();
