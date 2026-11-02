// Focus mode. While a task runs in Task Compass, sites the model judged unhelpful
// are blocked: a popup says so, and OK sends the tab back to its last allowed page.
// The service worker sleeps between events, so all state lives in chrome.storage.
import { T } from "./texts.js";

const API = "http://127.0.0.1:5000";
const SYNC_ALARM = "focus-sync";
const NO_FOCUS = { active: false, taskId: null, taskTitle: null, blocked: {}, ok: [] };

// --- state -------------------------------------------------------------------

async function loadFocus() {
  return (await chrome.storage.local.get({ focus: NO_FOCUS })).focus;
}

async function saveFocus(focus) {
  await chrome.storage.local.set({ focus });
}

// Per tab: the last page that was not blocked, and whether the block popup is up.
async function loadTabs() {
  return (await chrome.storage.session.get({ tabs: {} })).tabs;
}

async function updateTab(tabId, patch) {
  const tabs = await loadTabs();
  tabs[tabId] = { ...(tabs[tabId] || {}), ...patch };
  await chrome.storage.session.set({ tabs });
}

// --- server ------------------------------------------------------------------

async function api(path, body) {
  const res = await fetch(API + path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export function domainOf(url) {
  try {
    const u = new URL(url);
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    const host = u.hostname.toLowerCase().replace(/^www\./, "");
    if (host === "localhost" || host === "127.0.0.1" || host.endsWith(".localhost")) return null;
    return host;
  } catch {
    return null;
  }
}

function blockedMap(list) {
  return Object.fromEntries(list.map((s) => [s.domain, s.reason]));
}

// The last 50 pages from the browser history: domain and title only, never the full URL.
async function recentSites() {
  const items = await chrome.history.search({ text: "", maxResults: 50, startTime: 0 });
  const seen = new Map();
  for (const item of items) {
    const domain = domainOf(item.url);
    if (domain && !seen.has(domain)) seen.set(domain, { domain, title: item.title || "" });
  }
  return [...seen.values()];
}

// --- syncing with the running task ---------------------------------------------

async function sync({ force = false } = {}) {
  let status;
  try {
    status = await api("/api/focus");
  } catch {
    return { error: T.popupServerDown, focus: await loadFocus() }; // keep the last known state
  }
  const prev = await loadFocus();
  if (!status.active) {
    await saveFocus(NO_FOCUS);
    await releaseAllTabs();
    return { focus: NO_FOCUS };
  }
  if (force || prev.taskId !== status.task_id) {
    // A new task: let the model judge the recent history first.
    try {
      status = await api("/api/focus/history", { sites: await recentSites() });
    } catch {
      /* the sites will be judged one by one as they are opened */
    }
  }
  const blocked = blockedMap(status.blocked);
  const sameTask = prev.taskId === status.task_id;
  const ok = (sameTask ? prev.ok : []).filter((d) => !(d in blocked));
  const focus = { active: true, taskId: status.task_id, taskTitle: status.task_title, blocked, ok };
  await saveFocus(focus);
  for (const tab of await chrome.tabs.query({})) {
    if (tab.url) await handlePage(tab.id, tab.url, tab.title, { final: false });
  }
  return { focus, error: status.error };
}

async function releaseAllTabs() {
  const tabs = await loadTabs();
  for (const tabId of Object.keys(tabs)) {
    if (tabs[tabId].blocked) await hideBlock(Number(tabId));
  }
  await chrome.storage.session.set({ tabs: {} });
}

// --- deciding about a page -----------------------------------------------------

// `final` is true once the page has loaded (its title is known): only then is an
// unknown site sent to the model. Known sites are decided at once.
async function handlePage(tabId, url, title, { final }) {
  const domain = domainOf(url);
  if (!domain) return;
  const focus = await loadFocus();
  if (!focus.active) return markGood(tabId, url);
  if (domain in focus.blocked) return showBlock(tabId, domain, focus.blocked[domain]);
  if (focus.ok.includes(domain)) return markGood(tabId, url);
  if (!final) return;

  let verdict;
  try {
    verdict = await api("/api/focus/check", { domain, title: title || "" });
  } catch {
    return markGood(tabId, url); // server down: do not block
  }
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || domainOf(tab.url) !== domain) return; // the person moved on while the model thought
  if (!verdict.active) return sync();
  const latest = await loadFocus();
  if (verdict.blocked) {
    latest.blocked[domain] = verdict.reason;
    await saveFocus(latest);
    return showBlock(tabId, domain, verdict.reason);
  }
  if (!latest.ok.includes(domain)) latest.ok.push(domain);
  await saveFocus(latest);
  return markGood(tabId, url);
}

async function markGood(tabId, url) {
  await updateTab(tabId, { lastGood: url, blocked: null });
}

// --- the block popup -------------------------------------------------------------

async function showBlock(tabId, domain, reason) {
  await updateTab(tabId, { blocked: domain });
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: injectOverlay,
      args: [domain, reason || "", { title: T.blockedTitle, body: T.blockedBody(domain), ok: T.ok, need: T.need }],
    });
  } catch {
    /* the page is not ready yet; the next load event tries again */
  }
}

async function hideBlock(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => document.getElementById("task-compass-block")?.remove(),
    });
  } catch {
    /* the tab is gone or cannot be scripted */
  }
}

// Runs inside the blocked page. A closed shadow root keeps the page's CSS out of it.
function injectOverlay(domain, reason, text) {
  if (document.getElementById("task-compass-block")) return;
  const host = document.createElement("div");
  host.id = "task-compass-block";
  host.style.cssText = "all:initial;position:fixed;inset:0;z-index:2147483647;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      .backdrop { position: fixed; inset: 0; background: #1f2933; display: flex;
        align-items: center; justify-content: center; font-family: system-ui, sans-serif; }
      .box { background: #fff; color: #1f2933; max-width: 420px; padding: 28px; border-radius: 12px;
        text-align: right; direction: rtl; line-height: 1.5; }
      h1 { font-size: 20px; margin: 0 0 12px; }
      p { margin: 0 0 10px; }
      .reason { color: #52606d; }
      .buttons { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
      button { font: inherit; padding: 9px 16px; border-radius: 8px; border: 1px solid #1f2933;
        cursor: pointer; background: #fff; color: #1f2933; }
      button.primary { background: #1f2933; color: #fff; }
    </style>
    <div class="backdrop"><div class="box" dir="rtl" lang="he" role="alertdialog">
      <h1></h1><p class="body"></p><p class="reason"></p>
      <div class="buttons"><button class="primary" id="ok"></button><button id="need"></button></div>
    </div></div>`;
  root.querySelector("h1").textContent = text.title;
  root.querySelector(".body").textContent = text.body;
  root.querySelector(".reason").textContent = reason;
  root.getElementById("ok").textContent = text.ok;
  root.getElementById("need").textContent = text.need;
  root.getElementById("ok").addEventListener("click", () => chrome.runtime.sendMessage({ type: "back" }));
  root.getElementById("need").addEventListener("click", () => chrome.runtime.sendMessage({ type: "allow", domain }));
  document.documentElement.appendChild(host);
  root.getElementById("ok").focus();
}

// OK: back to the last page that was not blocked, or the app itself if there is none.
async function goBack(tabId) {
  const tabs = await loadTabs();
  const focus = await loadFocus();
  const last = tabs[tabId]?.lastGood;
  const lastDomain = last && domainOf(last);
  const target = last && !(lastDomain in focus.blocked) ? last : API + "/";
  await updateTab(tabId, { blocked: null });
  await chrome.tabs.update(tabId, { url: target });
}

async function allowSite(tabId, domain) {
  try {
    await api("/api/focus/allow", { domain });
  } catch {
    return;
  }
  const focus = await loadFocus();
  delete focus.blocked[domain];
  if (!focus.ok.includes(domain)) focus.ok.push(domain);
  await saveFocus(focus);
  await hideBlock(tabId);
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (tab?.url) await markGood(tabId, tab.url);
}

// --- events ----------------------------------------------------------------------

chrome.webNavigation.onCommitted.addListener((d) => {
  if (d.frameId === 0) handlePage(d.tabId, d.url, "", { final: false });
});

chrome.webNavigation.onCompleted.addListener(async (d) => {
  if (d.frameId !== 0) return;
  const tab = await chrome.tabs.get(d.tabId).catch(() => null);
  if (tab) handlePage(d.tabId, d.url, tab.title, { final: true });
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const tabs = await loadTabs();
  delete tabs[tabId];
  await chrome.storage.session.set({ tabs });
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const tabId = sender.tab?.id;
  if (msg.type === "back" && tabId !== undefined) goBack(tabId);
  else if (msg.type === "allow" && tabId !== undefined) allowSite(tabId, msg.domain);
  else if (msg.type === "status") sync({ force: msg.force }).then(reply);
  else return false;
  return msg.type === "status"; // keep the channel open for the async reply
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === SYNC_ALARM) sync();
});

function start() {
  chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 0.5 }); // notices a task starting or ending
  sync();
}

chrome.runtime.onInstalled.addListener(start);
chrome.runtime.onStartup.addListener(start);
