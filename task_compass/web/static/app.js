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
