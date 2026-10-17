// The call button a Business pastes into its own website (portal/templates/accounts/website_button.html).
// It asks the Portal for a call ticket; the Portal answers only a page whose address the Business listed (views.py call_from_site).
(function () {
  var script = document.currentScript;
  var portal = new URL(script.src).origin;
  var button = document.createElement("button");
  button.type = "button";
  button.className = "voice-call-button";
  button.textContent = "Prata med vår AI-assistent";
  button.addEventListener("click", function () {
    // Opened inside the click, so the browser lets it through; the call page is put in it once the ticket arrives.
    var win = window.open("", "_blank");
    if (win) win.opener = null; // the call page gets no handle on this website
    fetch(portal + "/call/" + encodeURIComponent(script.dataset.call) + "/button/")
      .then(function (r) {
        if (!r.ok) throw new Error("the Portal said " + r.status);
        return r.json();
      })
      .then(function (answer) {
        if (win) win.location.href = answer.url;
      })
      .catch(function (e) {
        if (win) win.close();
        console.error("Voice call button: no call could be started (" + e.message + "). Is this website listed in the Portal?");
      });
  });
  script.insertAdjacentElement("afterend", button);
})();
