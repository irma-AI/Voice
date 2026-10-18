// The Portal's one script, on every page. Each part only adds to a page that already works without it.

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

// A form is sent once: a second press while the first is on its way does nothing, and the buttons say they are busy.
// The buttons are disabled after the submit event, so the pressed button's name (Check) still goes with the form.
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.dataset.sending) {
    event.preventDefault();
    return;
  }
  form.dataset.sending = "1";
  const pressed = event.submitter;
  setTimeout(() => {
    form.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
      if (button === pressed && button.dataset.busy) {
        button.dataset.idle = button.textContent;
        button.textContent = button.dataset.busy;
      }
    });
    form.setAttribute("aria-busy", "true");
  });
});

// Back to a page from the browser's cache (the Back button): its forms can be sent again.
window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  document.querySelectorAll("form[data-sending]").forEach((form) => {
    delete form.dataset.sending;
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button").forEach((button) => {
      button.disabled = false;
      if (button.dataset.idle) button.textContent = button.dataset.idle;
    });
  });
});

// A refused save: the list of what to fix takes the focus, so it is read out and on screen even when Save was far down.
const summary = document.querySelector(".error-summary");
if (summary) {
  summary.tabIndex = -1;
  summary.focus();
}

// A counter under a text with a limit: <p data-count="<id>" hidden> beside the field shows how much of the limit is used.
document.querySelectorAll("[data-count]").forEach((line) => {
  const field = document.getElementById(line.dataset.count);
  const max = field && Number(field.getAttribute("maxlength"));
  if (!max) return;
  const show = () => {
    line.textContent = `${field.value.length.toLocaleString("en")} of ${max.toLocaleString("en")} characters`;
  };
  field.addEventListener("input", show);
  show();
  line.hidden = false;
});
