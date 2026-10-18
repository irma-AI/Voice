# The call panel, seen in a real browser

Written 2026-10-17 (VOI-72). It settles what [embedded-call-button.md](embedded-call-button.md) and [call-link-domain-limit.md](call-link-domain-limit.md) left "not checked". Desktop Chromium in the container, plus **one iPhone call** by Petter on 2026-10-18 (see [Phone check](#phone-check)). No Android phone, no Firefox, no desktop Safari.

## What was run

- **Browser:** Chromium 141.0.7390.37, headless, driven by Playwright 1.56.1, a fake microphone (`--use-fake-device-for-media-stream`). Nothing here is a phone, a headed window or another browser engine.
- **Rig (all local, nothing live):** this branch's Portal under gunicorn with TLS, and the core under uvicorn with TLS, each with its own name (`portal.voice-check.net`, `call.voice-check.net`). Two stand-in sites on port 443, so `frame-ancestors https://acme-shop.se` (default port) applies: `acme-shop.se`, `www.acme-shop.se`, `other-shop.se`. The names pointed at 127.0.0.1 through `/etc/hosts`, with a throwaway certificate authority imported into Chromium's certificate store (no `--ignore-certificate-errors`). A Business with `website_domain = acme-shop.se` and one with none.
- **No model calls, no spend:** the core had no route to Gemini on purpose (its proxy settings pointed at a closed port), so each call stopped at "Connecting to Gemini service: Connection refused". The core's call to the Portal for settings also failed in this rig (`URLError`; not investigated, it does not touch the questions here), so the core logged "call refused" before the model step.
- **Microphone:** the test driver granted the microphone to the site, or Chromium's auto-accept flag answered the prompt. So **the permission prompt itself, and whose name it shows, was not seen.**
- The scripts were not kept: CLAUDE.md § Tests has no browser seam, and a new one needs its own decision. The rig above is enough to repeat the run.

## What was seen

| # | Case | Seen |
|---|---|---|
| A | Page on `acme-shop.se` (the saved domain itself) | Launcher appears; panel opens; core page loads with `Content-Security-Policy: frame-ancestors https://acme-shop.se https://*.acme-shop.se`, exactly what the core sent. |
| B, C | `www.acme-shop.se`, and a deeper page `/shop/deep/page.html` on it | Both open the panel. The pair of entries matches the apex and a subdomain. |
| D | `other-shop.se` with the same snippet | Launcher appears, panel is empty ("call.voice-check.net refused to connect"); console: `Refused to frame … because an ancestor violates … frame-ancestors https://acme-shop.se https://*.acme-shop.se`. The Portal still handed this browser a ticket (expected: the Portal cannot see which site frames it). |
| N | `acme-shop.se` framed inside `other-shop.se`, panel opened in the inner frame | Refused with the same console message: the whole chain of ancestors is checked. |
| L | Plain tab on the Portal call route (`Sec-Fetch-Dest: document`) | 403 and the English sentence. Without the header at all (curl, standing in for an iPhone before iOS 16.4: not a phone): 403 too. |
| M | Plain tab on the core with no ticket | 403, the Swedish refusal page. |
| — | Plain tab on the core **with** a ticket | Opens (200). `frame-ancestors` is not checked for a tab, as the spec says; the Portal's in-frame check is the only thing that keeps casual visits from getting a ticket. |
| K | Business with no saved domain | Launcher appears; the panel shows the 403 sentence (the route's `xframe_options_exempt` is what lets it show). |
| — | Request headers the Portal got for the panel | `Sec-Fetch-Dest: iframe`, `Sec-Fetch-Site: cross-site`, `Referer` the page's origin. With `Referrer-Policy: no-referrer` on the page the `Referer` is gone and nothing changes: neither check uses it. |
| — | The Portal's redirect to the core | The microphone stays allowed after the redirect because `allow` names the core. An iframe built by hand with `allow="microphone"` (so only the Portal's origin) or no `allow`: `getUserMedia` is rejected, `NotAllowedError`. With `allow="microphone https://call.voice-check.net:7861"`: allowed. |
| — | A `302` carrying `X-Frame-Options: DENY`, then the core page | The core page shows in the frame: the header on the redirect does not block it. A `403` carrying `X-Frame-Options: DENY` is refused in a frame ("Refused to display … in a frame because it set 'X-Frame-Options' to 'deny'"), so `xframe_options_exempt` on `call_link` is needed for the 403 sentence, not for the redirect. |
| — | Start tap inside the panel, microphone granted | `getUserMedia` succeeds; the page's WebSocket opens from inside the frame (the core accepted it: `Origin` equals `Host`); status "Samtal pågår.". Audio output was not heard (headless). |
| — | Only the site's own origin granted, not the core's | `getUserMedia` in the frame stayed pending for 6 s (no answer), and was allowed once the core's origin was granted too. This is the driver's grant, not a real prompt; it does not say whose name a visitor sees. |
| E | Site sends `Permissions-Policy: microphone=()` | The launcher and panel appear and look fine; after Start, `getUserMedia` is rejected and the page says "Mikrofonen är blockerad. Tillåt den och försök igen." The visitor cannot fix it; the Business can. |
| F | Site sends `Content-Security-Policy: default-src 'self'` | The script is refused (`script-src-elem` falls back to `default-src`): **no launcher, no message anywhere the visitor sees.** |
| G | Same, script host allowed, frames not | Launcher appears; the panel is "This content is blocked. Contact the site owner to fix the issue." (`frame-src` falls back to `default-src`). |
| H | `frame-src` names the Portal only | The panel is blocked at the redirect: the core's address is checked against `frame-src` too. |
| I | `script-src` and `frame-src` name the Portal and the core | Works. |
| — | A page of 390 px (emulated phone viewport) | The panel fits with a margin (screenshot looked at, not kept). An emulation, not a phone. |

Other console lines seen on every page, working or not: `Potential permissions policy violation: microphone / autoplay is not allowed in this document` (a warning; the call worked anyway).

## What this changes

- **Settled** (and corrected in the two older notes): the apex plus subdomain pair; the whole-chain check; a redirect inside the frame and the microphone; the `X-Frame-Options` question; the WebSocket from inside the frame; a customer's `Permissions-Policy` and CSP; the `Sec-Fetch-*` and `Referer` values; a plain tab; `frame-ancestors` not stopping a tab.
- **Found, not hidden:** a Business whose own site sets a strict Content-Security-Policy or `Permissions-Policy` gets a button that is missing (F) or a panel that is blocked (G, H, E), and its dashboard says nothing about it. To work, its policy must allow the Portal's origin as a script source and **both** the Portal's and the core's origins as frame sources, and must not block the microphone. This is ticket VOI-91, not part of this check.
- **Seen on an iPhone** (below): the microphone prompt and its name, audio after the Start tap, the whole path on the live Portal and core.
- **Still not seen:** an Android phone; an iPhone before iOS 16.4; Firefox; desktop Safari; a test page on a different registrable domain from the Portal and core.

## Phone check

Done 2026-10-18 (about 08:19 Stockholm time) by Petter, on **one iPhone**. The iOS version and the browser were not recorded. The page was a throwaway test page at `paneltest.petterannerwall.se` with the dashboard's script tag, for the Business with `website_domain = petterannerwall.se`; the live Portal and live call app served the panel. The page was removed afterwards.

| Question | Seen on the iPhone |
|---|---|
| Does the microphone prompt appear, and whose name does it show? | It appeared and showed the **test page's name** (the framing site's), not the Portal's or the call app's. Matches the spec text quoted in [embedded-call-button.md](embedded-call-button.md) § 4. |
| Does audio start after the Start tap? | Yes: Petter heard the assistant clearly. |
| Did the call reach the model and the Portal? | The call app's log (kept in `/mnt/project-files/notes/voi-72-call-log-2026-10-18.txt`, ticket redacted, no personal data) shows one call through the Portal's call link for the Business, 17 s, the assistant spoke, one barge-in, and the record delivered to the Portal. The Portal's own log was not read. |
| Was the iPhone let through the in-frame check? | Yes, so it sent `Sec-Fetch-Dest: iframe`, which only iOS 16.4 and later do (MDN browser-compat-data, in [embedded-call-button.md](embedded-call-button.md)). |

**Not tried on a phone:**

- An **Android phone** (Chrome Android): Petter chose to skip it.
- An **iPhone before iOS 16.4**, which sends no `Sec-Fetch-*` and should be refused by the Portal (the same refusal as a plain tab, seen on the desktop with `curl`).
- A phone **refused** case: another site or a site with no saved domain.
- A **strict Content-Security-Policy** or `Permissions-Policy` on the page (desktop cases E to I only).
- Speakerphone, a second call at the same time, and the 10-minute cut.

**Caveat:** the test page shares the registrable domain `petterannerwall.se` with the Portal and the call app, so the browser may treat the frames as same-site. The prompt name and the audio start are what a customer's site on its own domain should see, but that was not tried.
