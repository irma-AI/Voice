// Copy buttons: a button with data-copy="<id>" copies that element's text and says so in the status line beside it.
// Without script (or without clipboard access) the button stays hidden and the code can still be selected by hand.
document.querySelectorAll("[data-copy]").forEach((button) => {
  const source = document.getElementById(button.dataset.copy);
  const status = button.parentElement.querySelector("[role=status]");
  if (!source || !navigator.clipboard) return;
  button.hidden = false;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(source.textContent.trim());
      status.textContent = "Copied. Paste it on your website.";
    } catch {
      status.textContent = "Could not copy. Select the code and copy it by hand.";
    }
  });
});
