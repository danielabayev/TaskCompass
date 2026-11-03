// Countdown for a running task. The deadline comes from the server, so a page
// refresh never resets it. When time is up, the stage is reloaded and the
// server moves the task to the checkpoint.
(function () {
  function tick() {
    var el = document.querySelector("[data-deadline]");
    if (!el) return;
    var left = Math.round((Date.parse(el.dataset.deadline) - Date.now()) / 1000);
    if (left <= 0) {
      if (!el.dataset.reloaded) {
        el.dataset.reloaded = "1";
        htmx.ajax("GET", el.dataset.stageUrl, { target: "#stage", swap: "outerHTML" });
      }
      return;
    }
    var h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60), s = left % 60;
    el.textContent = (h ? h + ":" : "") + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }
  setInterval(tick, 1000);
  document.addEventListener("htmx:afterSwap", tick);
  document.addEventListener("DOMContentLoaded", tick);
})();

// In chat-like text boxes (marked data-enter="send"), Enter sends the form and
// Shift+Enter adds a new line. Forms with several boxes (checkpoint, retro)
// keep the normal Enter so a half-filled form is not sent by accident.
document.addEventListener("keydown", function (e) {
  var box = e.target;
  if (e.key !== "Enter" || e.shiftKey || e.isComposing || box.tagName !== "TEXTAREA") return;
  if (box.dataset.enter !== "send" || !box.form) return;
  e.preventDefault();
  var button = box.form.querySelector("button[type=submit]");
  if (button && button.disabled) return;  // already sending (HTMX disables the button)
  box.form.requestSubmit();  // runs "required" checks and lets HTMX handle the submit
});

// Subtask titles: a one-line box that grows with its text. Enter saves the list
// (like in a normal text field), and pasted line breaks become spaces.
(function () {
  function grow(box) {
    box.style.height = "auto";
    box.style.height = box.scrollHeight + "px";
  }
  function growAll() {
    document.querySelectorAll("textarea.subtask-title").forEach(grow);
  }
  document.addEventListener("input", function (e) {
    var box = e.target;
    if (!box.classList || !box.classList.contains("subtask-title")) return;
    if (/[\r\n]/.test(box.value)) box.value = box.value.replace(/\s*[\r\n]+\s*/g, " ");
    grow(box);
  });
  document.addEventListener("keydown", function (e) {
    var box = e.target;
    if (e.key !== "Enter" || e.isComposing || !box.classList || !box.classList.contains("subtask-title")) return;
    e.preventDefault();
    var save = box.form && box.form.querySelector("button[name=action][value=save]");
    if (save) box.form.requestSubmit(save);
  });
  document.addEventListener("DOMContentLoaded", growAll);
  document.addEventListener("htmx:afterSwap", growAll);
  window.addEventListener("resize", growAll);
})();

// When the server can't be reached (stopped, restarted) or crashes, HTMX
// swaps nothing, so without this the page would look as if nothing happened.
// Show the error above the form; the typed text stays in the box.
function showNotSent(e) {
  var form = e.detail.elt.closest("form");
  if (!form) return;
  var box = form.querySelector(".error.not-sent");
  if (!box) {
    box = document.createElement("p");
    box.className = "error not-sent";
    box.setAttribute("role", "alert");
    box.textContent = document.body.dataset.notSent;
    form.prepend(box);
  }
}
document.addEventListener("htmx:sendError", showNotSent);
document.addEventListener("htmx:responseError", showNotSent);
