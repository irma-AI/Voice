// The call button a Business pastes into its website (VOI-73): a launcher in the corner that opens the call in a panel.
// The same file serves every Business; it learns which one from data-business on its own tag. No messages pass between
// the page and the panel (nothing to check the sender of); the launcher removes the panel to end the call.
(() => {
  const tag = document.currentScript;
  if (!tag || !tag.src || !tag.dataset.business) return;
  const portal = new URL(tag.src).origin;
  const core = "{{ core_origin|escapejs }}";
  const label = "Prata med vår AI-assistent";
  let panel = null;

  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.textContent = label;
  launcher.setAttribute("aria-expanded", "false");
  launcher.style.cssText = "position:fixed;right:1rem;bottom:1rem;z-index:2147483000;padding:.75rem 1.25rem;border:0;border-radius:2rem;background:#1c1917;color:#fff;font:1rem system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3)";

  function close() {
    panel?.remove();
    panel = null;
    launcher.textContent = label;
    launcher.setAttribute("aria-expanded", "false");
  }

  function open() {
    panel = document.createElement("iframe");
    panel.title = label;
    // The microphone and autoplay are the core's to use: the Portal's address redirects there, and an iframe only grants them to the address it was given.
    panel.allow = `microphone ${core}; autoplay ${core}`;
    panel.src = `${portal}/call/${encodeURIComponent(tag.dataset.business)}/`;
    panel.style.cssText = "position:fixed;right:1rem;bottom:4.5rem;z-index:2147483000;width:min(24rem,calc(100vw - 2rem));height:min(32rem,calc(100vh - 6rem));border:0;border-radius:.75rem;background:#fff;box-shadow:0 4px 24px rgba(0,0,0,.35)";
    document.body.append(panel);
    launcher.textContent = "Stäng";
    launcher.setAttribute("aria-expanded", "true");
  }

  launcher.onclick = () => (panel ? close() : open());
  document.addEventListener("keydown", (e) => e.key === "Escape" && panel && close());
  // async: the tag may run before the page body exists.
  if (document.body) document.body.append(launcher);
  else document.addEventListener("DOMContentLoaded", () => document.body.append(launcher));
})();
