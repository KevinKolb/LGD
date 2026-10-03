// Cloudflare Worker for every company's address: <subdomain>.residentialguide.app
// (the user, 2026-10-03: "https://lgd.residentialguide.app will be for LGD,
// on admin page is where you can pick a url subdomain").
//
// GitHub Pages serves the site at residentialguide.app only - one exact
// address per site, no wildcards. This Worker sits on the route
// *.residentialguide.app/* and answers each request with the same page
// from residentialguide.app, so lgd.residentialguide.app/manager/ is the
// Manager Portal. The page itself works out its company from the address
// (shared/home.js, client_by_subdomain in supabase/migrations/019).
//
// www.residentialguide.app is sent to the main address instead.

const ORIGIN = "https://residentialguide.app";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.hostname === "www.residentialguide.app") {
      return Response.redirect(ORIGIN + url.pathname + url.search, 301);
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Not allowed.", { status: 405 });
    }
    const upstream = await fetch(ORIGIN + url.pathname + url.search, {
      method: request.method,
      headers: { "Accept": request.headers.get("Accept") || "*/*" },
      redirect: "manual",
    });
    // GitHub's own redirects (a folder without its slash) point at the main
    // address; keep the visitor on their company's.
    const location = upstream.headers.get("Location");
    if (location && location.startsWith(ORIGIN)) {
      return Response.redirect("https://" + url.hostname + location.slice(ORIGIN.length), upstream.status);
    }
    return new Response(upstream.body, upstream);
  },
};
