#!/usr/bin/env python3
"""Authenticated gateway console served at server.menteso.com."""

import json
import hashlib
import hmac
import os
import platform
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

from openai_usage import OpenAIUsageError, get_openai_usage_dashboard


APP_NAME = "Menteso Server Console"
DOMAIN = os.getenv("MENTESO_CONSOLE_DOMAIN", "server.menteso.com")
PUBLIC_IP = os.getenv("MENTESO_GATEWAY_PUBLIC_IP", "43.205.83.226")
OFFICE_SERVER = os.getenv("MENTESO_OFFICE_SERVER", "MENT-SVR")
OFFICE_LAN_IP = os.getenv("MENTESO_OFFICE_LAN_IP", "192.168.0.10")
HEARTBEAT_FILE = Path(os.getenv("MENTESO_HEARTBEAT_FILE", "/var/lib/menteso-console/office-heartbeat.json"))
COMMANDS_FILE = Path(os.getenv("MENTESO_COMMANDS_FILE", "/var/lib/menteso-console/office-commands.json"))
LOGIN_ATTEMPTS_FILE = Path(os.getenv("MENTESO_LOGIN_ATTEMPTS_FILE", "/var/lib/menteso-console/login-attempts.json"))
SECURITY_EVENTS_FILE = Path(os.getenv("MENTESO_SECURITY_EVENTS_FILE", "/var/lib/menteso-console/security-events.json"))
GEO_CACHE_FILE = Path(os.getenv("MENTESO_GEO_CACHE_FILE", "/var/lib/menteso-console/geo-cache.json"))
HEARTBEAT_TOKEN = os.getenv("MENTESO_HEARTBEAT_TOKEN", "")
CONSOLE_USER = os.getenv("MENTESO_CONSOLE_USER", "admin")
PASSWORD_SALT = os.getenv("MENTESO_PASSWORD_SALT", "menteso-console-v1")
PASSWORD_HASH = os.getenv("MENTESO_PASSWORD_HASH", "2721a84cbf39ba1eeb5394c0ecabdd7aa0c5b330445474048479486ec279839c")
SESSION_SECRET = os.getenv("MENTESO_SESSION_SECRET", HEARTBEAT_TOKEN or secrets.token_urlsafe(32))
SESSIONS = {}
CAPTCHAS = {}
STARTED_AT = time.time()
OPENAI_DASHBOARD_FILE = Path(__file__).with_name("openai-dashboard.html")


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Menteso Server Console</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #637083;
      --line: #d9e0ea;
      --good: #117a43;
      --warn: #9a5b00;
      --bad: #b42318;
      --blue: #1f5eff;
      --soft-blue: #e8f0ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      background: #0f172a;
      color: #fff;
      padding: 18px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      border-bottom: 1px solid #24314a;
    }
    h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0; }
    .sub { color: #b6c2d4; font-size: 13px; margin-top: 4px; }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .user-chip {
      display: flex;
      align-items: center;
      gap: 10px;
      padding-left: 12px;
      border-left: 1px solid #334155;
    }
    .avatar {
      display: grid;
      place-items: center;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: #2563eb;
      color: #fff;
      font-size: 14px;
      font-weight: 800;
      box-shadow: 0 0 0 3px rgba(255, 255, 255, .1);
    }
    .user-copy { min-width: 0; line-height: 1.2; }
    .user-email { max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 700; }
    .user-role { margin-top: 3px; color: #94a3b8; font-size: 11px; }
    .server-tabs {
      display: inline-flex;
      gap: 4px;
      margin-bottom: 18px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: #e8edf5;
    }
    .server-tab { border: 0; background: transparent; color: #475569; padding: 9px 16px; }
    .server-tab.active { background: #17223a; color: #fff; box-shadow: 0 1px 2px rgba(15, 23, 42, .18); }
    .server-panel-hidden { display: none !important; }
    .project-path { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; color: #334155; }
    .shell { max-width: 1220px; margin: 0 auto; padding: 24px; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      min-height: 120px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }
    .span-internet { grid-column: span 4; }
    .span-info { grid-column: span 4; }
    .span-services { grid-column: span 3; }
    .span-instances { grid-column: span 9; }
    h2 { font-size: 15px; margin: 0 0 14px; }
    .metric { font-size: 28px; font-weight: 750; margin: 2px 0 4px; }
    .label { color: var(--muted); font-size: 13px; }
    .row { display: flex; justify-content: space-between; gap: 16px; padding: 9px 0; border-top: 1px solid #edf1f6; }
    .row:first-of-type { border-top: 0; padding-top: 0; }
    .key { color: var(--muted); }
    .val { text-align: right; font-weight: 600; overflow-wrap: anywhere; }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
      background: #eef2f7;
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
    .ok .dot { background: var(--good); }
    .warn .dot { background: var(--warn); }
    .bad .dot { background: var(--bad); }
    .ok { color: var(--good); background: #eaf7ef; }
    .warn { color: var(--warn); background: #fff4df; }
    .bad { color: var(--bad); background: #fff0ee; }
    .bar { height: 9px; background: #e7edf5; border-radius: 999px; overflow: hidden; margin-top: 10px; }
    .bar > div { height: 100%; background: var(--blue); width: 0%; transition: width .25s ease; }
    .service-list { display: grid; gap: 8px; }
    .service {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border: 1px solid #edf1f6;
      border-radius: 7px;
      padding: 10px 12px;
      background: #fbfcfe;
    }
    .muted { color: var(--muted); }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: #0f172a;
      color: #dbeafe;
      padding: 14px;
      border-radius: 8px;
      max-height: 260px;
      overflow: auto;
      font-size: 12px;
    }
    button {
      border: 1px solid #34415c;
      background: #17223a;
      color: #fff;
      border-radius: 7px;
      padding: 8px 12px;
      font-weight: 700;
      cursor: pointer;
    }
    .table-wrap { overflow-x: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 1040px;
      table-layout: fixed;
    }
    th, td {
      text-align: left;
      padding: 10px 9px;
      border-bottom: 1px solid #edf1f6;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .02em;
      background: #fbfcfe;
      position: sticky;
      top: 0;
    }
    td strong { display: block; margin-bottom: 3px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace; font-size: 12px; }
    .truncate {
      display: block;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .runtime-list {
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
      max-height: 48px;
      overflow: hidden;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      max-width: 96px;
      border-radius: 999px;
      background: #eef2f7;
      color: #334155;
      padding: 3px 7px;
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    th:nth-child(1), td:nth-child(1) { width: 170px; }
    th:nth-child(2), td:nth-child(2) { width: 92px; }
    th:nth-child(3), td:nth-child(3) { width: 170px; }
    th:nth-child(4), td:nth-child(4) { width: 70px; }
    th:nth-child(5), td:nth-child(5) { width: 210px; }
    th:nth-child(6), td:nth-child(6) { width: 70px; }
    th:nth-child(7), td:nth-child(7) { width: 78px; }
    th:nth-child(8), td:nth-child(8) { width: 92px; }
    th:nth-child(9), td:nth-child(9) { width: 150px; }
    th:nth-child(10), td:nth-child(10) { width: 88px; }
    th:nth-child(11), td:nth-child(11) { width: 74px; }
    .security-table { min-width: 1120px; }
    .security-table th:nth-child(1), .security-table td:nth-child(1) { width: 180px; }
    .security-table th:nth-child(2), .security-table td:nth-child(2) { width: 92px; }
    .security-table th:nth-child(3), .security-table td:nth-child(3) { width: 94px; }
    .security-table th:nth-child(4), .security-table td:nth-child(4) { width: 135px; }
    .security-table th:nth-child(5), .security-table td:nth-child(5) { width: 150px; }
    .security-table th:nth-child(6), .security-table td:nth-child(6) { width: 180px; }
    .security-table th:nth-child(7), .security-table td:nth-child(7) { width: 175px; }
    .security-table th:nth-child(8), .security-table td:nth-child(8) { width: 170px; }
    .security-table th:nth-child(9), .security-table td:nth-child(9) { width: 130px; }
    .pager {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .pager button {
      padding: 6px 9px;
      min-width: 34px;
    }
    .pager button:disabled {
      opacity: .45;
      cursor: not-allowed;
    }
    @media (max-width: 900px) {
      .span-3, .span-4, .span-6, .span-8, .span-internet, .span-info, .span-services, .span-instances { grid-column: span 12; }
      header { align-items: flex-start; flex-direction: column; }
      .shell { padding: 16px; }
      .header-actions { width: 100%; flex-wrap: wrap; }
      .user-chip { margin-left: auto; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Menteso Server Console</h1>
      <div class="sub">Public gateway for AI-agent infrastructure</div>
    </div>
    <div class="header-actions">
      <span id="overall" class="pill warn"><span class="dot"></span>Loading</span>
      <button type="button" onclick="location.href='/openai-dashboard'">OpenAI Usage</button>
      <button onclick="loadStatus()">Refresh</button>
      <div class="user-chip" title="Signed-in administrator">
        <span id="userAvatar" class="avatar" aria-hidden="true">S</span>
        <div class="user-copy">
          <div id="userEmail" class="user-email">sajan@menteso.com</div>
          <div id="userRole" class="user-role">Administrator</div>
        </div>
      </div>
    </div>
  </header>
  <main class="shell">
    <nav class="server-tabs" aria-label="Server dashboard">
      <button id="localTab" class="server-tab active" type="button" onclick="selectServerTab('local')">Local Server</button>
      <button id="awsTab" class="server-tab" type="button" onclick="selectServerTab('aws')">AWS Server</button>
    </nav>
    <section class="grid">
      <div class="card span-3 server-aws">
        <h2>AWS CPU</h2>
        <div id="cpu" class="metric">-</div>
        <div class="label">Gateway utilization</div>
        <div class="bar"><div id="cpuBar"></div></div>
      </div>
      <div class="card span-3 server-aws">
        <h2>AWS Memory</h2>
        <div id="mem" class="metric">-</div>
        <div class="label">RAM used</div>
        <div class="bar"><div id="memBar"></div></div>
      </div>
      <div class="card span-3 server-aws">
        <h2>AWS Disk</h2>
        <div id="disk" class="metric">-</div>
        <div class="label">Root volume used</div>
        <div class="bar"><div id="diskBar"></div></div>
      </div>
      <div class="card span-3 server-aws">
        <h2>Uptime</h2>
        <div id="uptime" class="metric">-</div>
        <div class="label">AWS gateway uptime</div>
      </div>

      <div class="card span-3 server-local">
        <h2>MENT-SVR CPU</h2>
        <div id="officeCpu" class="metric">-</div>
        <div class="label">Windows server utilization</div>
        <div class="bar"><div id="officeCpuBar"></div></div>
      </div>
      <div class="card span-3 server-local">
        <h2>MENT-SVR Memory</h2>
        <div id="officeMem" class="metric">-</div>
        <div class="label">Windows RAM used</div>
        <div class="bar"><div id="officeMemBar"></div></div>
      </div>
      <div class="card span-3 server-local">
        <h2>MENT-SVR Disk</h2>
        <div id="officeDisk" class="metric">-</div>
        <div class="label">C: volume used</div>
        <div class="bar"><div id="officeDiskBar"></div></div>
      </div>
      <div class="card span-3 server-local">
        <h2>MENT-SVR Uptime</h2>
        <div id="officeUptime" class="metric">-</div>
        <div class="label">Windows server uptime</div>
      </div>
      <div class="card span-internet server-local">
        <h2>Internet</h2>
        <div id="internetStatus" class="metric">-</div>
        <div id="internetDetails" class="label">Waiting for heartbeat</div>
        <div class="bar"><div id="internetBar"></div></div>
      </div>

      <div class="card span-info server-aws">
        <h2>Gateway</h2>
        <div class="row"><span class="key">Domain</span><span id="domain" class="val">-</span></div>
        <div class="row"><span class="key">Elastic IP</span><span id="publicIp" class="val">-</span></div>
        <div class="row"><span class="key">Host</span><span id="host" class="val">-</span></div>
        <div class="row"><span class="key">Platform</span><span id="platform" class="val">-</span></div>
      </div>

      <div class="card span-info server-local">
        <h2>Office Server</h2>
        <div class="row"><span class="key">Server</span><span id="officeName" class="val">-</span></div>
        <div class="row"><span class="key">LAN IP</span><span id="officeIp" class="val">-</span></div>
        <div class="row"><span class="key">Heartbeat</span><span id="heartbeat" class="val">Not connected yet</span></div>
        <div class="row"><span class="key">Mode</span><span class="val">AWS public gateway</span></div>
      </div>

      <div class="card span-services server-aws">
        <h2>Gateway Services</h2>
        <div id="services" class="service-list"></div>
      </div>

      <div class="card span-instances server-local">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;">
          <h2 style="margin:0;">Instances From C:\sites</h2>
          <button type="button" disabled title="Coming next: deploy a new app into C:\sites">Add Project</button>
        </div>
        <div class="label" style="margin-bottom:10px;">Auto-detected project folders, runtime processes, listening ports, Git state, memory, and storage.</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Project</th>
                <th>Status</th>
                <th>Runtime</th>
                <th>Ports</th>
                <th>URL</th>
                <th>CPU</th>
                <th>Memory</th>
                <th>Storage</th>
                <th>Git</th>
                <th>Domain</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="instancesTable">
              <tr><td colspan="11" class="muted">Waiting for office heartbeat.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card span-12 server-aws">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;">
          <div>
            <h2 style="margin:0 0 4px;">AWS Managed Projects</h2>
            <div class="label">Administrator-only project home directories</div>
          </div>
          <span class="pill ok"><span class="dot"></span>2 projects</span>
        </div>
        <div class="service-list">
          <div class="service">
            <div><strong>Menteso OS</strong><span class="project-path">/home/menteso_os</span></div>
            <span class="pill warn"><span class="dot"></span>Configured</span>
          </div>
          <div class="service">
            <div><strong>PatentZoom Production</strong><span class="project-path">/home/patentzoom_prod</span></div>
            <span class="pill warn"><span class="dot"></span>Configured</span>
          </div>
        </div>
      </div>

      <div class="card span-12 server-aws">
        <h2>Gateway Terminal</h2>
        <div class="label" style="margin-bottom:10px;">Runs on the AWS gateway as the restricted console service user. Timeout: 20 seconds.</div>
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px;">
          <input id="terminalCommand" placeholder="systemctl status caddy --no-pager" style="flex:1;border:1px solid var(--line);border-radius:7px;padding:9px 10px;font:inherit;">
          <button onclick="runTerminal()">Run</button>
        </div>
        <pre id="terminalOutput">No command run yet.</pre>
      </div>

      <div class="card span-12 server-aws">
        <h2>Recent Gateway Log</h2>
        <pre id="log">Loading...</pre>
      </div>

      <div class="card span-12 server-aws">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;">
          <h2 style="margin:0;">Login Attempts</h2>
          <div id="loginAttemptsPager" class="pager"></div>
        </div>
        <div class="label" style="margin-bottom:10px;">Stored from gateway access logs in /var/lib/menteso-console/login-attempts.json. Failed attempts are blocked after 3 tries.</div>
        <div class="table-wrap">
          <table class="security-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Result</th>
                <th>User</th>
                <th>Reason</th>
                <th>IP</th>
                <th>Device</th>
                <th>Location</th>
                <th>ISP</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="loginAttemptsTable">
              <tr><td colspan="9" class="muted">Waiting for login data.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </main>
  <script>
    (function securityWatch() {
      let sent = false;
      function report(reason) {
        if (sent) return;
        sent = true;
        const payload = JSON.stringify({
          reason,
          path: location.pathname,
          width_gap: Math.abs(window.outerWidth - window.innerWidth),
          height_gap: Math.abs(window.outerHeight - window.innerHeight),
          at: new Date().toISOString()
        });
        if (navigator.sendBeacon) {
          navigator.sendBeacon("/api/security-event", new Blob([payload], { type: "application/json" }));
        } else {
          fetch("/api/security-event", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true }).catch(() => {});
        }
      }
      setInterval(() => {
        if (Math.abs(window.outerWidth - window.innerWidth) > 180 || Math.abs(window.outerHeight - window.innerHeight) > 180) {
          report("devtools_window_gap");
        }
      }, 1500);
      window.addEventListener("keydown", event => {
        if (event.key === "F12" || (event.ctrlKey && event.shiftKey && ["I", "J", "C"].includes(event.key.toUpperCase())) || (event.ctrlKey && event.key.toUpperCase() === "U")) {
          event.preventDefault();
          report("devtools_shortcut");
        }
      }, true);
    })();
    const pct = n => `${Math.round(Number(n) || 0)}%`;
    let loginAttempts = [];
    let loginAttemptsPage = 1;
    const loginAttemptsPageSize = 10;
    function selectServerTab(tab) {
      const showLocal = tab === "local";
      document.querySelectorAll(".server-local").forEach(el => el.classList.toggle("server-panel-hidden", !showLocal));
      document.querySelectorAll(".server-aws").forEach(el => el.classList.toggle("server-panel-hidden", showLocal));
      document.getElementById("localTab").classList.toggle("active", showLocal);
      document.getElementById("awsTab").classList.toggle("active", !showLocal);
      sessionStorage.setItem("menteso-server-tab", tab);
    }
    function humanDuration(seconds) {
      seconds = Math.max(0, Math.floor(Number(seconds) || 0));
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      if (days) return `${days}d ${hours}h ${minutes}m`;
      if (hours) return `${hours}h ${minutes}m`;
      return `${minutes}m`;
    }
    const pill = (ok, warn=false) => ok ? "pill ok" : warn ? "pill warn" : "pill bad";
    function setBar(id, value) { document.getElementById(id).style.width = `${Math.min(100, Math.max(0, value || 0))}%`; }
    function serviceRow(name, state) {
      const good = state === "active" || state === "running";
      return `<div class="service"><strong>${name}</strong><span class="${pill(good)}"><span class="dot"></span>${state || "unknown"}</span></div>`;
    }
    function rowsFromObject(obj) {
      const entries = Object.entries(obj || {});
      if (!entries.length) return `<div class="muted">Waiting for live data.</div>`;
      return entries.map(([k,v]) => serviceRow(k.replaceAll("_", " "), String(v))).join("");
    }
    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
      }[ch]));
    }
    function renderInstances(items) {
      const tbody = document.getElementById("instancesTable");
      if (items && !Array.isArray(items)) items = [items];
      if (!Array.isArray(items) || !items.length) {
        tbody.innerHTML = `<tr><td colspan="11" class="muted">No app projects found in C:\\sites.</td></tr>`;
        return;
      }
      tbody.innerHTML = items.map(item => {
        const running = item.status === "running";
        const publicHealth = item.public || {};
        const statusWarn = item.status === "public_down";
        const statusText = item.status === "public_down" ? "public down" : item.status;
        const publicDetail = publicHealth.configured
          ? `${publicHealth.url || "-"} · ${publicHealth.status || "-"}${publicHealth.status_code ? " · " + publicHealth.status_code : ""}`
          : `local only`;
        const git = item.git || {};
        const processText = (item.processes || []).length ? (item.processes || []).join(", ") : "none";
        const runtimes = String(item.kind || "-").split(",").map(x => x.trim()).filter(Boolean);
        const ports = (item.ports || []).length ? (item.ports || []).join(", ") : "-";
        const urls = (item.urls || []).length
          ? (item.urls || []).map(url => `<a class="truncate" title="${esc(url)}" href="${esc(url)}" target="_blank" rel="noreferrer">${esc(url)}</a>`).join("")
          : "-";
        const gitLine = git.is_repo
          ? `${esc(git.branch || "-")} @ ${esc(git.commit || "-")}${git.dirty ? " · dirty" : ""}`
          : "not a repo";
        const canRun = !!item.run_supported;
        const runTitle = canRun ? esc(item.run_command || "Run") : "Add .menteso/app.json or a standard start script";
        return `
          <tr>
            <td><strong class="truncate" title="${esc(item.name)}">${esc(item.name)}</strong><span class="muted mono truncate" title="${esc(item.path)}">${esc(item.path)}</span></td>
            <td><span class="${pill(running, statusWarn)}"><span class="dot"></span>${esc(statusText)}</span><span class="muted mono truncate" title="${esc(publicDetail)}">${esc(publicDetail)}</span></td>
            <td><div class="runtime-list" title="${esc(item.kind || "-")}">${runtimes.map(x => `<span class="tag">${esc(x)}</span>`).join("")}</div><span class="muted truncate" title="${esc(processText)}">${esc(processText)}</span></td>
            <td class="mono truncate" title="${esc(ports)}">${esc(ports)}</td>
            <td class="mono">${urls}</td>
            <td>${esc(item.cpu_percent ?? 0)}%</td>
            <td>${esc(item.memory_mb ?? 0)} MB</td>
            <td>${esc(item.storage_mb ?? 0)} MB</td>
            <td><span class="truncate" title="${gitLine.replaceAll('"', '&quot;')}">${gitLine}</span>${git.remote ? `<span class="muted mono truncate" title="${esc(git.remote)}">${esc(git.remote)}</span>` : ""}</td>
            <td><button title="Publish this project through a domain" onclick="setDomain('${esc(item.name)}', '${esc((item.ports || [])[0] || "")}')">Domain</button></td>
            <td><button ${canRun ? "" : "disabled"} title="${runTitle}" onclick="runInstance('${esc(item.name)}')">Run</button></td>
          </tr>`;
      }).join("");
    }
    function renderLoginAttempts(items) {
      const tbody = document.getElementById("loginAttemptsTable");
      const pager = document.getElementById("loginAttemptsPager");
      loginAttempts = Array.isArray(items) ? items : [];
      const totalPages = Math.max(1, Math.ceil(loginAttempts.length / loginAttemptsPageSize));
      loginAttemptsPage = Math.min(Math.max(1, loginAttemptsPage), totalPages);
      if (!loginAttempts.length) {
        tbody.innerHTML = `<tr><td colspan="9" class="muted">No login attempts recorded yet.</td></tr>`;
        pager.innerHTML = "";
        return;
      }
      const start = (loginAttemptsPage - 1) * loginAttemptsPageSize;
      const visible = loginAttempts.slice(start, start + loginAttemptsPageSize);
      pager.innerHTML = `
        <button type="button" ${loginAttemptsPage <= 1 ? "disabled" : ""} onclick="changeLoginAttemptsPage(-1)">Prev</button>
        <span>Page ${loginAttemptsPage} / ${totalPages} · ${loginAttempts.length} records</span>
        <button type="button" ${loginAttemptsPage >= totalPages ? "disabled" : ""} onclick="changeLoginAttemptsPage(1)">Next</button>
      `;
      tbody.innerHTML = visible.map(item => {
        const success = item.status === "success";
        const when = item.time ? new Date(item.time).toLocaleString() : "-";
        const location = [item.city, item.region, item.country].filter(Boolean).join(", ") || "-";
        const action = item.path === "/api/login" ? "login" : (item.path || "-");
        const reason = item.reason || (success ? "allowed" : "blocked");
        return `
          <tr>
            <td><span class="truncate" title="${esc(item.time || "")}">${esc(when)}</span></td>
            <td><span class="${pill(success)}"><span class="dot"></span>${esc(item.status || "-")}</span></td>
            <td><span class="truncate" title="${esc(item.user || "")}">${esc(item.user || "-")}</span></td>
            <td><span class="truncate" title="${esc(reason)}">${esc(reason)}</span></td>
            <td class="mono"><span class="truncate" title="${esc(item.ip || "")}">${esc(item.ip || "-")}</span></td>
            <td><span class="truncate" title="${esc([item.device, item.device_name, item.user_agent].filter(Boolean).join(" | "))}">${esc(item.device || "-")}</span></td>
            <td><span class="truncate" title="${esc(location)}">${esc(location)}</span></td>
            <td><span class="truncate" title="${esc(item.isp || "")}">${esc(item.isp || "-")}</span></td>
            <td class="mono"><span class="truncate" title="${esc(item.path || "")}">${esc(action)}</span></td>
          </tr>`;
      }).join("");
    }
    function changeLoginAttemptsPage(delta) {
      loginAttemptsPage += delta;
      renderLoginAttempts(loginAttempts);
    }
    async function loadStatus() {
      try {
        const res = await fetch("/api/status", { cache: "no-store" });
        const data = await res.json();
        const currentUser = data.session?.user || "sajan@menteso.com";
        document.getElementById("userEmail").textContent = currentUser;
        document.getElementById("userAvatar").textContent = currentUser.slice(0, 1).toUpperCase() || "U";
        document.getElementById("overall").className = pill(data.ok);
        document.getElementById("overall").innerHTML = `<span class="dot"></span>${data.ok ? "Gateway online" : "Check gateway"}`;
        document.getElementById("cpu").textContent = pct(data.system.cpu_percent);
        document.getElementById("mem").textContent = pct(data.system.memory_percent);
        document.getElementById("disk").textContent = pct(data.system.disk_percent);
        document.getElementById("uptime").textContent = data.system.uptime_human;
        setBar("cpuBar", data.system.cpu_percent);
        setBar("memBar", data.system.memory_percent);
        setBar("diskBar", data.system.disk_percent);
        document.getElementById("domain").textContent = data.gateway.domain;
        document.getElementById("publicIp").textContent = data.gateway.public_ip;
        document.getElementById("host").textContent = data.gateway.hostname;
        document.getElementById("platform").textContent = data.gateway.platform;
        document.getElementById("officeName").textContent = data.office.name;
        document.getElementById("officeIp").textContent = data.office.lan_ip;
        document.getElementById("heartbeat").textContent = data.office.heartbeat || "Not connected yet";
        document.getElementById("services").innerHTML = Object.entries(data.services).map(([k,v]) => serviceRow(k, v)).join("");
        const h = data.office.data || {};
        const officeServer = h.server || {};
        document.getElementById("officeCpu").textContent = pct(officeServer.cpu_percent);
        document.getElementById("officeMem").textContent = pct(officeServer.memory_percent);
        document.getElementById("officeDisk").textContent = pct(officeServer.disk_c_percent);
        document.getElementById("officeUptime").textContent = officeServer.uptime_seconds ? humanDuration(officeServer.uptime_seconds) : (officeServer.uptime || "-");
        setBar("officeCpuBar", officeServer.cpu_percent);
        setBar("officeMemBar", officeServer.memory_percent);
        setBar("officeDiskBar", officeServer.disk_c_percent);
        const internet = h.internet || {};
        const internetOnline = internet.status === "online";
        const internetDegraded = internet.status === "degraded";
        const mbps = internet.download_mbps ?? null;
        document.getElementById("internetStatus").textContent = internet.status ? internet.status.toUpperCase() : "-";
        document.getElementById("internetStatus").style.color = internetOnline ? "var(--good)" : internetDegraded ? "var(--warn)" : "var(--bad)";
        document.getElementById("internetDetails").textContent = internet.status
          ? `AWS ${internet.gateway_latency_ms ?? "-"} ms · ${mbps ?? "-"} Mbps · DNS ${internet.dns_ok ? "ok" : "fail"}`
          : "Waiting for heartbeat";
        setBar("internetBar", Math.min(100, Math.max(0, Number(mbps || 0) * 2)));
        renderInstances(h.instances || []);
        renderLoginAttempts(data.security?.login_attempts || []);
        document.getElementById("log").textContent = data.logs.join("\n") || "No recent logs.";
      } catch (err) {
        document.getElementById("overall").className = "pill bad";
        document.getElementById("overall").innerHTML = `<span class="dot"></span>Offline`;
        document.getElementById("log").textContent = String(err);
      }
    }
    selectServerTab(sessionStorage.getItem("menteso-server-tab") || "local");
    loadStatus();
    setInterval(loadStatus, 15000);
    async function runTerminal() {
      const input = document.getElementById("terminalCommand");
      const output = document.getElementById("terminalOutput");
      const command = input.value.trim();
      if (!command) return;
      output.textContent = "Running...";
      try {
        const res = await fetch("/api/terminal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command })
        });
        const data = await res.json();
        output.textContent = [
          `$ ${command}`,
          `exit=${data.code}`,
          data.stdout ? `\n--- stdout ---\n${data.stdout}` : "",
          data.stderr ? `\n--- stderr ---\n${data.stderr}` : ""
        ].join("\n");
      } catch (err) {
        output.textContent = String(err);
      }
    }
    async function runInstance(name) {
      if (!confirm(`Run ${name}?`)) return;
      const output = document.getElementById("terminalOutput");
      output.textContent = `Queued run for ${name}. The office heartbeat agent will execute it shortly.`;
      try {
        const res = await fetch("/api/office-command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "run", project: name })
        });
        const data = await res.json();
        output.textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        output.textContent = String(err);
      }
    }
    async function setDomain(name, defaultPort) {
      const value = prompt(`Domain for ${name} (example: app.menteso.com)`, "");
      if (value === null) return;
      const domain = value.trim();
      if (!domain) return;
      const portValue = prompt(`Local port for ${name}`, defaultPort || "8010");
      if (portValue === null) return;
      const local_port = Number(portValue);
      if (!Number.isInteger(local_port) || local_port < 1 || local_port > 65535) {
        alert("Enter a valid local port.");
        return;
      }
      const output = document.getElementById("terminalOutput");
      output.textContent = `Queued public domain setup for ${name}: ${domain} -> localhost:${local_port}`;
      try {
        const res = await fetch("/api/office-command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "set_domain", project: name, domain, local_port })
        });
        const data = await res.json();
        const record = data.dns || data.command?.dns;
        output.textContent = record
          ? [
              `Domain setup queued for ${name}`,
              "",
              "Create this DNS record at your domain provider:",
              `Type: ${record.type}`,
              `Name/Host: ${record.name}`,
              `Value/Points to: ${record.value}`,
              `TTL: ${record.ttl}`,
              "",
              `After DNS updates, open: ${record.url}`,
              "",
              JSON.stringify(data, null, 2)
            ].join("\n")
          : JSON.stringify(data, null, 2);
      } catch (err) {
        output.textContent = String(err);
      }
    }
  </script>
</body>
</html>
"""

LOGIN_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Menteso Server Login</title>
  <style>
    :root { color-scheme: light; --bg:#f5f7fb; --panel:#fff; --ink:#17202a; --muted:#637083; --line:#d9e0ea; --bad:#b42318; --blue:#1f5eff; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .login { width:min(420px, calc(100vw - 32px)); background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:24px; box-shadow:0 10px 30px rgba(15,23,42,.08); }
    h1 { margin:0 0 6px; font-size:22px; }
    .sub { color:var(--muted); font-size:13px; margin-bottom:20px; }
    label { display:block; font-size:13px; font-weight:700; margin:14px 0 6px; }
    input { width:100%; border:1px solid var(--line); border-radius:7px; padding:10px 11px; font:inherit; }
    .captcha { display:flex; gap:10px; align-items:center; }
    .captcha .question { min-width:110px; padding:10px 12px; border:1px solid var(--line); border-radius:7px; background:#f8fafc; font-weight:800; text-align:center; }
    button { width:100%; margin-top:18px; border:0; background:#17223a; color:#fff; border-radius:7px; padding:11px 12px; font-weight:800; cursor:pointer; }
    .error { display:none; margin-top:12px; color:var(--bad); font-size:13px; }
  </style>
</head>
<body>
  <form class="login" onsubmit="login(event)">
    <h1>Menteso Server Console</h1>
    <div class="sub">Secure access for AI-agent infrastructure</div>
    <label for="username">Username</label>
    <input id="username" autocomplete="username" required>
    <label for="password">Password</label>
    <input id="password" type="password" autocomplete="current-password" required>
    <label for="captcha">Verification</label>
    <div class="captcha">
      <div id="captchaQuestion" class="question">...</div>
      <input id="captcha" inputmode="numeric" autocomplete="off" required>
    </div>
    <button type="submit">Login</button>
    <div id="error" class="error">Login failed.</div>
  </form>
  <script>
    (function securityWatch() {
      let sent = false;
      function report(reason) {
        if (sent) return;
        sent = true;
        const payload = JSON.stringify({
          reason,
          path: location.pathname,
          width_gap: Math.abs(window.outerWidth - window.innerWidth),
          height_gap: Math.abs(window.outerHeight - window.innerHeight),
          at: new Date().toISOString()
        });
        if (navigator.sendBeacon) {
          navigator.sendBeacon("/api/security-event", new Blob([payload], { type: "application/json" }));
        } else {
          fetch("/api/security-event", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true }).catch(() => {});
        }
      }
      setInterval(() => {
        if (Math.abs(window.outerWidth - window.innerWidth) > 180 || Math.abs(window.outerHeight - window.innerHeight) > 180) {
          report("devtools_window_gap");
        }
      }, 1500);
      window.addEventListener("keydown", event => {
        if (event.key === "F12" || (event.ctrlKey && event.shiftKey && ["I", "J", "C"].includes(event.key.toUpperCase())) || (event.ctrlKey && event.key.toUpperCase() === "U")) {
          event.preventDefault();
          report("devtools_shortcut");
        }
      }, true);
    })();
    let captchaId = "";
    async function loadCaptcha() {
      const res = await fetch("/api/captcha", { cache: "no-store" });
      const data = await res.json();
      captchaId = data.id;
      document.getElementById("captchaQuestion").textContent = data.question;
      document.getElementById("captcha").value = "";
    }
    async function login(event) {
      event.preventDefault();
      const error = document.getElementById("error");
      error.style.display = "none";
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("username").value,
          password: document.getElementById("password").value,
          captcha_id: captchaId,
          captcha: document.getElementById("captcha").value
        })
      });
      if (res.ok) {
        location.href = "/";
      } else {
        error.style.display = "block";
        await loadCaptcha();
      }
    }
    loadCaptcha();
  </script>
</body>
</html>
"""


def run(args, timeout=5):
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return completed.returncode, (completed.stdout or "").strip(), (completed.stderr or "").strip()
    except Exception as exc:
        return 1, "", str(exc)


def hash_password(password):
    return hashlib.sha256((PASSWORD_SALT + str(password or "")).encode("utf-8")).hexdigest()


def create_captcha():
    a = secrets.randbelow(8) + 2
    b = secrets.randbelow(8) + 2
    captcha_id = secrets.token_urlsafe(18)
    CAPTCHAS[captcha_id] = {"answer": str(a + b), "expires": time.time() + 300}
    return {"id": captcha_id, "question": f"{a} + {b}"}


def verify_captcha(captcha_id, answer):
    item = CAPTCHAS.pop(str(captcha_id or ""), None)
    if not item or item.get("expires", 0) < time.time():
        return False
    return secrets.compare_digest(str(answer or "").strip(), str(item.get("answer")))


def make_session(user):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {"user": user, "expires": time.time() + 12 * 3600}
    return token


def session_user(headers):
    cookie_header = headers.get("Cookie", "")
    cookies = {}
    for part in cookie_header.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            cookies[key] = value
    token = cookies.get("menteso_session", "")
    item = SESSIONS.get(token)
    if not item or item.get("expires", 0) < time.time():
        SESSIONS.pop(token, None)
        return ""
    item["expires"] = time.time() + 12 * 3600
    return item.get("user") or ""


def service_state(name):
    code, out, _ = run(["systemctl", "is-active", name], timeout=3)
    if code == 0:
        return out or "active"
    code, out, _ = run(["systemctl", "is-enabled", name], timeout=3)
    return out or "unknown"


def read_cpu_percent():
    def sample():
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            parts = handle.readline().split()[1:]
        nums = [int(x) for x in parts]
        idle = nums[3] + nums[4]
        total = sum(nums)
        return idle, total
    idle1, total1 = sample()
    time.sleep(0.12)
    idle2, total2 = sample()
    total_delta = max(1, total2 - total1)
    idle_delta = idle2 - idle1
    return round((1 - idle_delta / total_delta) * 100, 1)


def read_memory_percent():
    data = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            data[key] = int(value.strip().split()[0])
    total = data.get("MemTotal", 1)
    available = data.get("MemAvailable", 0)
    return round((1 - available / total) * 100, 1)


def human_duration(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def read_heartbeat():
    if not HEARTBEAT_FILE.exists():
        return {}, ""
    try:
        data = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}, "Invalid heartbeat file"
    ts = data.get("updated_at") or data.get("timestamp") or ""
    status = data.get("status") or "received"
    return data, f"{status} at {ts}" if ts else status


def load_commands():
    if not COMMANDS_FILE.exists():
        return {"pending": [], "history": []}
    try:
        data = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {"pending": list(data.get("pending") or []), "history": list(data.get("history") or [])}
    except Exception:
        pass
    return {"pending": [], "history": []}


def save_commands(data):
    COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["history"] = list(data.get("history") or [])[-100:]
    temp_path = COMMANDS_FILE.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(COMMANDS_FILE)


def normalize_domain(value):
    domain = str(value or "").strip().lower()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.split("/")[0].split(":")[0].strip(".")
    return domain


def dns_record_for_domain(value):
    domain = normalize_domain(value)
    parts = domain.split(".")
    if len(parts) >= 3:
        host = ".".join(parts[:-2])
        root = ".".join(parts[-2:])
    elif len(parts) == 2:
        host = "@"
        root = domain
    else:
        host = domain or "@"
        root = domain
    return {
        "type": "A",
        "name": host,
        "host": host,
        "domain": domain,
        "root": root,
        "value": PUBLIC_IP,
        "ttl": 60,
        "url": f"https://{domain}" if domain else "",
        "note": "Create this A record at the DNS provider for the domain. For a root/apex domain, use @ as the host/name.",
    }


def queue_office_command(payload):
    project = str(payload.get("project") or "").strip()
    action = str(payload.get("action") or "run").strip().lower()
    domain = str(payload.get("domain") or "").strip()
    local_port = payload.get("local_port")
    if not project:
        return {"ok": False, "error": "project is required"}
    if action not in {"run", "set_domain"}:
        return {"ok": False, "error": "only run and set_domain are supported right now"}
    if action == "set_domain" and not domain:
        return {"ok": False, "error": "domain is required"}
    if action == "set_domain":
        try:
            local_port = int(local_port)
            if local_port < 1 or local_port > 65535:
                raise ValueError()
        except Exception:
            return {"ok": False, "error": "valid local_port is required"}
    dns = dns_record_for_domain(domain) if action == "set_domain" else None
    command = {
        "id": uuid4().hex,
        "action": action,
        "project": project,
        "domain": domain,
        "local_port": local_port,
        "dns": dns,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data = load_commands()
    data["pending"].append(command)
    save_commands(data)
    return {"ok": True, "command": command, "dns": dns}


def take_pending_commands(limit=3):
    data = load_commands()
    pending = list(data.get("pending") or [])
    selected = pending[:limit]
    data["pending"] = pending[limit:]
    if selected:
        save_commands(data)
    return selected


def record_command_results(results):
    if not isinstance(results, list) or not results:
        return
    data = load_commands()
    history = list(data.get("history") or [])
    history.extend(results)
    data["history"] = history
    save_commands(data)


def recent_logs():
    candidates = [
        "/var/log/menteso-console/app.log",
        "/var/log/caddy/access.log",
        "/var/log/syslog",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-40:]
            except Exception:
                continue
    return []


def read_json_file(path, fallback):
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if data is not None else fallback
    except Exception:
        pass
    return fallback


def write_json_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def parse_device(user_agent):
    ua = str(user_agent or "")
    browser = "Unknown"
    os_name = "Unknown"
    if "Edg/" in ua:
        browser = "Microsoft Edge"
    elif "Chrome/" in ua and "Chromium" not in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser = "Safari"
    elif "curl/" in ua:
        browser = "curl"
    elif "PowerShell" in ua:
        browser = "PowerShell"

    if "Windows NT" in ua:
        os_name = "Windows"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Mac OS X" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    return {"browser": browser, "os": os_name, "summary": f"{browser} on {os_name}"}


def reverse_dns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def is_public_ip(ip):
    try:
        parsed = ip_address(ip)
        return parsed.is_global
    except Exception:
        return False


def lookup_geo(ip):
    cache = read_json_file(GEO_CACHE_FILE, {})
    cached = cache.get(ip)
    now = time.time()
    if cached and now - float(cached.get("_cached_at", 0)) < 86400:
        return {k: v for k, v in cached.items() if not k.startswith("_")}
    if not is_public_ip(ip):
        geo = {"country": "", "region": "", "city": "", "isp": "", "latitude": None, "longitude": None}
    else:
        try:
            url = f"https://ipwho.is/{ip}?fields=success,country,region,city,latitude,longitude,connection"
            with urllib.request.urlopen(url, timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("success") is False:
                geo = {"country": "", "region": "", "city": "", "isp": "", "latitude": None, "longitude": None}
            else:
                connection = data.get("connection") or {}
                geo = {
                    "country": data.get("country") or "",
                    "region": data.get("region") or "",
                    "city": data.get("city") or "",
                    "isp": connection.get("isp") or connection.get("org") or "",
                    "latitude": data.get("latitude"),
                    "longitude": data.get("longitude"),
                }
        except Exception:
            geo = {"country": "", "region": "", "city": "", "isp": "", "latitude": None, "longitude": None}
    cache[ip] = dict(geo, _cached_at=now)
    try:
        write_json_file(GEO_CACHE_FILE, cache)
    except Exception:
        pass
    return geo


def sync_login_attempts():
    existing = read_json_file(LOGIN_ATTEMPTS_FILE, [])
    if not isinstance(existing, list):
        existing = []
    seen = {item.get("id") for item in existing if isinstance(item, dict)}
    attempts = list(existing)
    log_path = Path("/var/log/caddy/access.log")
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-1500:]
        except Exception:
            lines = []
        for line in lines:
            try:
                entry = json.loads(line)
            except Exception:
                continue
            req = entry.get("request") or {}
            host = req.get("host") or req.get("headers", {}).get("Host", [""])[0]
            status = int(entry.get("status") or 0)
            if host != DOMAIN or status not in {200, 401}:
                continue
            uri = req.get("uri") or ""
            method = req.get("method") or ""
            if uri != "/api/login" or method != "POST" or status != 401:
                continue
            remote_ip = req.get("remote_ip") or ""
            headers = req.get("headers") or {}
            user_agent = (headers.get("User-Agent") or [""])[0]
            user_id = entry.get("user_id") or ""
            event_id = f"{entry.get('ts')}|{remote_ip}|{status}|{uri}|{user_agent[:80]}|{user_id}"
            if event_id in seen:
                continue
            device = parse_device(user_agent)
            geo = lookup_geo(remote_ip)
            attempts.append({
                "id": event_id,
                "time": datetime.fromtimestamp(float(entry.get("ts") or time.time()), timezone.utc).isoformat(),
                "status": "failed",
                "http_status": status,
                "user": user_id or "unknown",
                "ip": remote_ip,
                "device": device.get("summary"),
                "browser": device.get("browser"),
                "os": device.get("os"),
                "device_name": reverse_dns(remote_ip),
                "path": uri,
                "method": method,
                "country": geo.get("country") or "",
                "region": geo.get("region") or "",
                "city": geo.get("city") or "",
                "isp": geo.get("isp") or "",
                "latitude": geo.get("latitude"),
                "longitude": geo.get("longitude"),
                "user_agent": user_agent,
            })
            seen.add(event_id)
    attempts = [
        item for item in attempts
        if item.get("path") == "/api/login"
    ]
    attempts = sorted(attempts, key=lambda item: item.get("time", ""), reverse=True)[:500]
    try:
        write_json_file(LOGIN_ATTEMPTS_FILE, attempts)
    except Exception:
        pass
    return attempts


def append_login_attempt_from_request(handler, username, success, reason):
    forwarded = handler.headers.get("X-Forwarded-For", "")
    remote_ip = forwarded.split(",")[0].strip() if forwarded else handler.client_address[0]
    user_agent = handler.headers.get("User-Agent", "")
    device = parse_device(user_agent)
    geo = lookup_geo(remote_ip)
    attempts = read_json_file(LOGIN_ATTEMPTS_FILE, [])
    if not isinstance(attempts, list):
        attempts = []
    attempts.insert(0, {
        "id": uuid4().hex,
        "time": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "http_status": 200 if success else 401,
        "user": str(username or "unknown")[:80],
        "ip": remote_ip,
        "device": device.get("summary"),
        "browser": device.get("browser"),
        "os": device.get("os"),
        "device_name": reverse_dns(remote_ip),
        "path": "/api/login",
        "method": "POST",
        "country": geo.get("country") or "",
        "region": geo.get("region") or "",
        "city": geo.get("city") or "",
        "isp": geo.get("isp") or "",
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "reason": reason,
        "source": "app_login",
        "user_agent": user_agent,
    })
    write_json_file(LOGIN_ATTEMPTS_FILE, attempts[:500])


def append_security_event_from_request(handler, payload):
    forwarded = handler.headers.get("X-Forwarded-For", "")
    remote_ip = forwarded.split(",")[0].strip() if forwarded else handler.client_address[0]
    user_agent = handler.headers.get("User-Agent", "")
    device = parse_device(user_agent)
    geo = lookup_geo(remote_ip)
    events = read_json_file(SECURITY_EVENTS_FILE, [])
    if not isinstance(events, list):
        events = []
    events.insert(0, {
        "id": uuid4().hex,
        "time": datetime.now(timezone.utc).isoformat(),
        "event": "browser_debug_signal",
        "reason": str((payload or {}).get("reason") or "unknown")[:120],
        "path": str((payload or {}).get("path") or "")[:200],
        "ip": remote_ip,
        "device": device.get("summary"),
        "browser": device.get("browser"),
        "os": device.get("os"),
        "device_name": reverse_dns(remote_ip),
        "country": geo.get("country") or "",
        "region": geo.get("region") or "",
        "city": geo.get("city") or "",
        "isp": geo.get("isp") or "",
        "width_gap": (payload or {}).get("width_gap"),
        "height_gap": (payload or {}).get("height_gap"),
        "user_agent": user_agent,
    })
    write_json_file(SECURITY_EVENTS_FILE, events[:500])


def run_terminal_command(command):
    command = str(command or "").strip()
    if not command:
        return {"ok": False, "code": None, "stdout": "", "stderr": "Empty command"}
    if len(command) > 1000:
        return {"ok": False, "code": None, "stdout": "", "stderr": "Command too long"}
    started = time.time()
    try:
        completed = subprocess.run(
            ["/bin/bash", "-lc", command],
            cwd="/opt/menteso-server-console",
            capture_output=True,
            text=True,
            timeout=20,
        )
        return {
            "ok": completed.returncode == 0,
            "code": completed.returncode,
            "stdout": (completed.stdout or "")[-20000:],
            "stderr": (completed.stderr or "")[-20000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "code": None,
            "stdout": (exc.stdout or "")[-20000:] if isinstance(exc.stdout, str) else "",
            "stderr": "Command timed out after 20 seconds",
            "duration_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        return {"ok": False, "code": None, "stdout": "", "stderr": str(exc)}


def status_payload():
    disk = shutil.disk_usage("/")
    disk_percent = round((disk.used / disk.total) * 100, 1)
    code, boot_time, _ = run(["cut", "-d", " ", "-f1", "/proc/uptime"], timeout=2)
    uptime_seconds = float(boot_time or "0")
    heartbeat_data, heartbeat_text = read_heartbeat()
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gateway": {
            "domain": DOMAIN,
            "public_ip": PUBLIC_IP,
            "hostname": socket.gethostname(),
            "platform": f"{platform.system()} {platform.release()}",
        },
        "office": {
            "name": OFFICE_SERVER,
            "lan_ip": OFFICE_LAN_IP,
            "heartbeat": heartbeat_text,
            "data": heartbeat_data,
        },
        "system": {
            "cpu_percent": read_cpu_percent(),
            "memory_percent": read_memory_percent(),
            "disk_percent": disk_percent,
            "uptime_human": human_duration(uptime_seconds),
            "console_uptime_human": human_duration(time.time() - STARTED_AT),
        },
        "services": {
            "menteso-console": service_state("menteso-console"),
            "caddy": service_state("caddy"),
            "ssh": service_state("ssh"),
        },
        "officeCommands": load_commands(),
        "security": {
            "login_attempts": sync_login_attempts(),
            "login_limit": 3,
        },
        "logs": recent_logs(),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, content_type, body, include_body=True, extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _authorized(self):
        return bool(session_user(self.headers))

    def _redirect_login(self, include_body=True):
        self._send(302, "text/plain; charset=utf-8", "login required\n", include_body, {"Location": "/login"})

    def _route(self, include_body=True):
        path = urlparse(self.path).path
        if path == "/robots.txt":
            self._send(200, "text/plain; charset=utf-8", "User-agent: *\nDisallow: /\n", include_body)
            return
        if path == "/login":
            self._send(200, "text/html; charset=utf-8", LOGIN_HTML, include_body)
            return
        if path == "/api/captcha":
            self._send(200, "application/json; charset=utf-8", json.dumps(create_captcha()), include_body)
            return
        if path == "/":
            if not self._authorized():
                self._redirect_login(include_body)
                return
            self._send(200, "text/html; charset=utf-8", HTML, include_body)
            return
        if path == "/openai-dashboard":
            if not self._authorized():
                self._redirect_login(include_body)
                return
            try:
                dashboard_html = OPENAI_DASHBOARD_FILE.read_text(encoding="utf-8")
            except OSError:
                self._send(503, "text/plain; charset=utf-8", "OpenAI dashboard is unavailable.\n", include_body)
                return
            self._send(200, "text/html; charset=utf-8", dashboard_html, include_body)
            return
        if path == "/api/openai/usage":
            if not self._authorized():
                self._send(401, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "login required"}), include_body)
                return
            try:
                query = parse_qs(urlparse(self.path).query)
                days = int((query.get("days") or ["7"])[0])
                force_refresh = str((query.get("refresh") or ["false"])[0]).lower() in {"1", "true", "yes"}
                payload = get_openai_usage_dashboard(days=days, force_refresh=force_refresh)
                self._send(200, "application/json; charset=utf-8", json.dumps(payload), include_body)
            except OpenAIUsageError as exc:
                self._send(exc.status_code, "application/json; charset=utf-8", json.dumps({"ok": False, "error": str(exc)}), include_body)
            except (TypeError, ValueError):
                self._send(400, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "invalid reporting range"}), include_body)
            except Exception:
                self._send(500, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "OpenAI usage reporting failed."}), include_body)
            return
        if path == "/api/speed-test":
            if not HEARTBEAT_TOKEN:
                self._send(503, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "heartbeat token is not configured"}), include_body)
                return
            expected = f"Bearer {HEARTBEAT_TOKEN}"
            if not secrets.compare_digest(self.headers.get("Authorization", ""), expected):
                self._send(401, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "unauthorized"}), include_body)
                return
            try:
                query = urlparse(self.path).query
                params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
                size = min(1024 * 1024, max(64 * 1024, int(params.get("bytes", "524288"))))
            except Exception:
                size = 524288
            self._send(200, "application/octet-stream", b"0" * size, include_body)
            return
        if path == "/api/status":
            if not self._authorized():
                self._send(401, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "login required"}), include_body)
                return
            payload = status_payload()
            payload["session"] = {"user": session_user(self.headers), "role": "Administrator"}
            self._send(200, "application/json; charset=utf-8", json.dumps(payload), include_body)
            return
        if path == "/healthz":
            self._send(200, "text/plain; charset=utf-8", "ok\n", include_body)
            return
        self._send(404, "text/plain; charset=utf-8", "not found\n", include_body)

    def do_GET(self):
        self._route(include_body=True)

    def do_HEAD(self):
        self._route(include_body=False)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/security-event":
            try:
                length = min(int(self.headers.get("Content-Length", "0") or 0), 1024 * 16)
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(raw) if raw else {}
                if not isinstance(payload, dict):
                    payload = {}
                append_security_event_from_request(self, payload)
                self._send(204, "text/plain; charset=utf-8", "")
            except Exception:
                self._send(204, "text/plain; charset=utf-8", "")
            return
        if path == "/api/login":
            try:
                length = min(int(self.headers.get("Content-Length", "0") or 0), 1024 * 32)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                username = str(payload.get("username") or "")
                password = str(payload.get("password") or "")
                captcha_ok = verify_captcha(payload.get("captcha_id"), payload.get("captcha"))
                password_ok = secrets.compare_digest(username, CONSOLE_USER) and secrets.compare_digest(hash_password(password), PASSWORD_HASH)
                if not captcha_ok or not password_ok:
                    append_login_attempt_from_request(self, username, False, "captcha_failed" if not captcha_ok else "password_failed")
                    self._send(401, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "invalid login"}))
                    return
                append_login_attempt_from_request(self, username, True, "login_ok")
                token = make_session(CONSOLE_USER)
                self._send(
                    200,
                    "application/json; charset=utf-8",
                    json.dumps({"ok": True}),
                    True,
                    {"Set-Cookie": f"menteso_session={token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=43200"},
                )
            except Exception as exc:
                self._send(400, "application/json; charset=utf-8", json.dumps({"ok": False, "error": str(exc)}))
            return
        if path == "/api/logout":
            self._send(
                200,
                "application/json; charset=utf-8",
                json.dumps({"ok": True}),
                True,
                {"Set-Cookie": "menteso_session=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0"},
            )
            return
        if path == "/api/terminal":
            if not self._authorized():
                self._send(401, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "login required"}))
                return
            try:
                length = min(int(self.headers.get("Content-Length", "0") or 0), 1024 * 32)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = run_terminal_command(payload.get("command") if isinstance(payload, dict) else "")
                self._send(200, "application/json; charset=utf-8", json.dumps(result))
            except Exception as exc:
                self._send(400, "application/json; charset=utf-8", json.dumps({"ok": False, "error": str(exc)}))
            return
        if path == "/api/office-command":
            if not self._authorized():
                self._send(401, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "login required"}))
                return
            try:
                length = min(int(self.headers.get("Content-Length", "0") or 0), 1024 * 32)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = queue_office_command(payload if isinstance(payload, dict) else {})
                self._send(200 if result.get("ok") else 400, "application/json; charset=utf-8", json.dumps(result))
            except Exception as exc:
                self._send(400, "application/json; charset=utf-8", json.dumps({"ok": False, "error": str(exc)}))
            return
        if path != "/api/heartbeat":
            self._send(404, "text/plain; charset=utf-8", "not found\n")
            return
        if not HEARTBEAT_TOKEN:
            self._send(503, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "heartbeat token is not configured"}))
            return
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {HEARTBEAT_TOKEN}"
        if not secrets.compare_digest(auth, expected):
            self._send(401, "application/json; charset=utf-8", json.dumps({"ok": False, "error": "unauthorized"}))
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0") or 0), 1024 * 512)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be an object")
            record_command_results(payload.get("command_results") or [])
            payload["received_at"] = datetime.now(timezone.utc).isoformat()
            HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_path = HEARTBEAT_FILE.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temp_path.replace(HEARTBEAT_FILE)
            self._send(200, "application/json; charset=utf-8", json.dumps({"ok": True, "commands": take_pending_commands()}))
        except Exception as exc:
            self._send(400, "application/json; charset=utf-8", json.dumps({"ok": False, "error": str(exc)}))

    def log_message(self, fmt, *args):
        print(f"{datetime.now(timezone.utc).isoformat()} {self.address_string()} {fmt % args}", flush=True)


def main():
    host = os.getenv("MENTESO_CONSOLE_HOST", "127.0.0.1")
    port = int(os.getenv("MENTESO_CONSOLE_PORT", "9000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"{APP_NAME} listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
