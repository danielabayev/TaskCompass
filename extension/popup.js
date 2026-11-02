import { T } from "./texts.js";

const $ = (id) => document.getElementById(id);

async function show(force) {
  const { focus, error } = await chrome.runtime.sendMessage({ type: "status", force });
  $("state").textContent = focus.active ? T.popupOn : T.popupOff;
  $("title").textContent = focus.active ? focus.taskTitle : "";
  $("blocked").textContent = focus.active ? T.popupBlocked(Object.keys(focus.blocked).length) : "";
  $("error").textContent = error || "";
  $("sites").replaceChildren(...Object.entries(focus.blocked || {}).map(([domain, reason]) => {
    const li = document.createElement("li");
    li.className = "blocked";
    li.textContent = `${domain}${reason ? " - " + reason : ""}`;
    return li;
  }));
}

$("refresh").textContent = T.popupRefresh;
$("refresh").addEventListener("click", () => show(true));
show(false);
