// Cloudflare Email Worker for residentialguide.app (the user, 2026-10-03:
// "setup manager@residentialguide.app and a catch all on cloudflare to
// forward to an email address specified on the admin tab").
//
// Email Routing sends manager@ and the catch-all here. Each message is
// forwarded to the address saved on the Admin Portal (site_settings
// 'mail_forward', supabase/migrations/018), read fresh for every message.
// If none is saved, or forwarding to it fails, it goes to FALLBACK.
//
// Cloudflare only forwards to a verified destination address: whatever is
// typed on the admin page must also be added once under Email Routing ->
// Destination addresses, and the link in Cloudflare's email clicked.
//
// Settings (Worker -> Settings -> Variables and Secrets):
//   SUPABASE_URL  plain text  https://zglkceocuvioxovbnqrz.supabase.co
//   SUPABASE_KEY  secret      the project's sb_secret_... key (never in a page)
//   FALLBACK      plain text  a verified destination address

async function savedAddress(env) {
  try {
    const response = await fetch(env.SUPABASE_URL + "/rest/v1/rpc/mail_forward_target", {
      method: "POST",
      headers: { apikey: env.SUPABASE_KEY, "Content-Type": "application/json" },
      body: "{}",
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
    const saved = await savedAddress(env);
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
