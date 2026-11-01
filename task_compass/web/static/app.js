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
