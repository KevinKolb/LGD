// Cloudflare Email Worker for residentialguide.app (the user, 2026-10-03:
// "setup manager@ ... and a catch all on cloudflare to forward to an email
// address specified on the admin tab", then: each company at its own
// subdomain).
//
// Email Routing sends every address at each company's subdomain here -
// manager@lgd.residentialguide.app, anything@lgd.residentialguide.app.
// Each message goes to that company's forwarding address, saved on the
// Admin Portal (managers.mail_forward, supabase/migrations/019) and read
// fresh for every message. If none is saved, or forwarding fails, it goes
// to FALLBACK.
//
// Cloudflare only forwards to a verified destination address: whatever is
// typed on the admin page must also be added once under Email Routing ->
// Destination addresses, and the link in Cloudflare's email clicked.
//
// Settings (Worker -> Settings -> Variables and Secrets):
//   SUPABASE_URL  plain text  https://zglkceocuvioxovbnqrz.supabase.co
//   SUPABASE_KEY  secret      the project's sb_secret_... key (never in a page)
//   FALLBACK      plain text  a verified destination address

async function savedAddress(env, recipient) {
  try {
    const response = await fetch(env.SUPABASE_URL + "/rest/v1/rpc/mail_forward_target", {
      method: "POST",
      headers: { apikey: env.SUPABASE_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ recipient }),
    });
    if (!response.ok) return "";
    const value = await response.json();
    return typeof value === "string" && value.includes("@") ? value : "";
  } catch (error) {
    return "";
  }
}

export default {
  async email(message, env) {
    const saved = await savedAddress(env, message.to);
    const to = saved || env.FALLBACK;
    try {
      await message.forward(to);
    } catch (error) {
      if (env.FALLBACK && to !== env.FALLBACK) {
        await message.forward(env.FALLBACK);
      } else {
        message.setReject("This address could not take the message just now.");
      }
    }
  },
};
