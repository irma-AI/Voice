// The call button a Business pastes into its website (VOI-73): a launcher in the corner that opens the call in a panel.
// Its address names the Business (?business=<call slug>); the tag carries the core's origin and the Business's adjusted
// accent and the text on it in data-core, data-fill and data-ink (VOI-135), written by the Portal's dashboard. No messages
// pass between the page and the panel (nothing to check the sender of); the launcher removes the panel to end the call.
//
// Pasted tags name this file by a hash of its bytes (integrity=): an edit here makes every one of them stop loading, so a
// change goes in call-button.v2.js with its own hash, and this file stays. `make generate` writes the hash the dashboard shows.
//
// The host page is someone else's: the launcher and the panel live in a closed shadow root, so its styles don't reach
// them and theirs don't leak out. Built with DOM calls only and styled through a constructed stylesheet, which a
// Content-Security-Policy's style-src and Trusted Types leave alone (docs/research/embedded-call-button.md § 5).
(() => {
  const tag = document.currentScript;
  if (!tag || !tag.src) return;
  const portal = new URL(tag.src).origin;
  // A tag pasted before VOI-89 names its Business in data-business instead; it keeps working, in Voice's own look.
  const business = new URL(tag.src).searchParams.get("business") || tag.dataset.business;
  if (!business) return;
  const core = tag.dataset.core;
  // The launcher's fill and the ring and words on it, at AA or better (portal/accounts/theme.py, on_accent).
  const { fill, ink } = tag.dataset;
  if (!core || !fill || !ink) {
    console.warn("voice-call-button: the script tag needs data-core, data-fill and data-ink; paste the code from the Portal's dashboard again");
    return;
  }
  const label = "Prata med vår AI-assistent";
  const NAME = "voice-call-button";

  // Deep sea and Granite from portal/static/portal/tokens.css: the panel's ground is the call page's, so nothing flashes white before it paints.
  const css = `
    :host { all: initial; }
    button {
      position: fixed; z-index: 2147483000;
      right: max(1rem, env(safe-area-inset-right)); bottom: max(1rem, env(safe-area-inset-bottom));
      display: inline-flex; align-items: center; gap: .625rem;
      box-sizing: border-box; min-height: 3rem; margin: 0; padding: 0 1.25rem 0 1rem;
      border: 0; border-radius: 9999px; background: ${fill}; color: ${ink};
      font: 500 .9375rem/1.2 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      letter-spacing: normal; text-transform: none; white-space: nowrap; cursor: pointer;
      box-shadow: 0 1px 2px rgb(11 19 34 / .2), 0 8px 24px rgb(11 19 34 / .2);
      transition: transform .2s ease-out, box-shadow .2s ease-out;
      -webkit-tap-highlight-color: transparent;
    }
    button:hover { transform: translateY(-1px); box-shadow: 0 1px 2px rgb(11 19 34 / .2), 0 12px 28px rgb(11 19 34 / .26); }
    /* Drawn inside the pill in the ink, so it reads on any accent and any host page. */
    button:focus-visible { outline: 2px solid ${ink}; outline-offset: -6px; }
    svg { display: block; flex: none; width: 1.25rem; height: 1.25rem; }
    circle { fill: none; stroke: currentColor; stroke-width: 2; }
    iframe {
      position: fixed; z-index: 2147483000;
      right: max(1rem, env(safe-area-inset-right)); bottom: calc(max(1rem, env(safe-area-inset-bottom)) + 3.75rem);
      box-sizing: border-box; width: min(24rem, calc(100vw - 2rem));
      height: min(32rem, calc(100vh - 6.75rem)); height: min(32rem, calc(100dvh - 6.75rem));
      margin: 0; padding: 0; border: 1px solid #3A3F47; border-radius: .75rem;
      background: #0B1322; color-scheme: dark;
      box-shadow: 0 16px 48px rgb(11 19 34 / .35);
    }
    @media (prefers-reduced-motion: reduce) {
      button { transition: none; }
      button:hover { transform: none; }
    }
  `;

  function mount() {
    // A second tag (pasted twice, or added by a tag manager) would stack a second launcher on the first.
    if (document.querySelector(NAME)) return;
    const host = document.createElement(NAME);
    // The host page's own rules can still reach the host element itself; an inline !important reset outranks them.
    host.style.setProperty("all", "initial", "important");
    const root = host.attachShadow({ mode: "closed" });
    if ("adoptedStyleSheets" in root) {
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(css);
      root.adoptedStyleSheets = [sheet];
    } else {
      // Safari before 16.4: a style element, which a strict style-src blocks (the button still opens the call).
      const style = document.createElement("style");
      style.textContent = css;
      root.append(style);
    }

    const launcher = document.createElement("button");
    launcher.type = "button";
    // Its words are Swedish whatever the host page's language, so a screen reader reads them in Swedish (WCAG 3.1.2).
    launcher.lang = "sv";
    launcher.setAttribute("aria-expanded", "false");
    // Voice's ring mark, in the ink on the accent.
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 20 20");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const ring = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    ring.setAttribute("cx", "10");
    ring.setAttribute("cy", "10");
    ring.setAttribute("r", "8");
    svg.append(ring);
    const words = document.createElement("span");
    words.textContent = label;
    launcher.append(svg, words);
    let panel = null;

    function close() {
      panel?.remove();
      panel = null;
      words.textContent = label;
      launcher.setAttribute("aria-expanded", "false");
      launcher.removeAttribute("aria-controls");
    }

    function open() {
      panel = document.createElement("iframe");
      panel.id = "panel";
      panel.title = label;
    panel.lang = "sv"; // the title's language; the call page inside says its own
      // The microphone and autoplay are the core's to use: the Portal's address redirects there, and an iframe only grants them to the address it was given.
      panel.allow = `microphone ${core}; autoplay ${core}`;
      panel.src = `${portal}/call/${encodeURIComponent(business)}/`;
      // Keyboard and screen-reader users land in the call, not back on the host page.
      panel.addEventListener("load", () => panel?.focus(), { once: true });
      root.append(panel);
      words.textContent = "Stäng";
      launcher.setAttribute("aria-expanded", "true");
      launcher.setAttribute("aria-controls", "panel");
    }

    launcher.onclick = () => (panel ? close() : open());
    // Escape reaches here only while focus is on the host page; inside the panel the call page hangs up on it itself (VOI-96).
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && panel) {
        close();
        launcher.focus();
      }
    });
    root.append(launcher);
    document.body.append(host);
  }

  // async: the tag may run before the page body exists.
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
