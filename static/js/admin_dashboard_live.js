(function () {
  const config = window.adminDashboardConfig || {};
  const liveUrl = config.liveUrl;
  const initialAttackMapPoints = Array.isArray(config.attackMapPoints) ? config.attackMapPoints : [];
  const initialTopThreats = Array.isArray(config.topThreats) ? config.topThreats : [];
  const initialTopThreatScore = Number(config.topThreatScore || 0);

  if (!liveUrl) {
    return;
  }

  let attackMap = null;
  let attackMarkers = [];

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatAmarilloTime(value) {
    if (!value) return "";

    const raw = String(value).trim();
    if (!raw) return "";

    let normalized = raw;
    if (normalized.endsWith("Z")) {
      normalized = normalized.replace("Z", "+00:00");
    } else if (!/[zZ]|[+\-]\d{2}:\d{2}$/.test(normalized)) {
      normalized = normalized + "Z";
    }

    const dt = new Date(normalized);
    if (Number.isNaN(dt.getTime())) {
      return raw;
    }

    return dt.toLocaleString("en-US", {
      timeZone: "America/Chicago",
      month: "2-digit",
      day: "2-digit",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true
    });
  }

  function prettyLabel(value) {
    const raw = String(value || "");
    if (!raw) return "Unknown Event";

    const directMap = {
      login_failed: "Login Failed",
      login: "Login Success",
      logout: "Logout",
      profile_update: "Profile Updated",
      set_role: "Role Changed",
      set_active: "Account Status Changed",
      reset_password: "Password Reset",
      wipe_all_data: "Data Wipe",
      recreate_schema: "Schema Recreated",
      security_setting_updated: "Security Setting Updated",
      resident_signin_failed: "Resident Sign In Failed",
      resident_signin_rate_limited: "Resident Sign In Rate Limited",
      scanner_probe_detected: "Scanner Probe Detected",
      scanner_probe_banned: "Scanner Probe Banned",
      public_abuse_rate_limited: "Public Abuse Rate Limited",
      public_abuse_banned: "Public Abuse Banned",
      banned_ip_blocked: "Banned IP Blocked",
      cloudflare_bypass_blocked: "Cloudflare Bypass Blocked",
      bad_method_blocked: "Bad Method Blocked",
      bad_user_agent_detected: "Bad User Agent Detected",
      bad_user_agent_banned: "Bad User Agent Banned",
      login_rate_limited_ip: "Staff Login Rate Limited By IP",
      login_rate_limited_user: "Staff Login Rate Limited By User",
      login_username_locked: "Staff Username Locked",
      login_ip_banned: "Staff Login IP Banned",
      login_blocked_banned_ip: "Staff Login Blocked Banned IP"
    };

    if (directMap[raw]) {
      return directMap[raw];
    }

    if (raw.startsWith("kiosk_")) {
      return raw.slice(6).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
    }

    return raw.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function eventClass(value) {
    const raw = String(value || "");

    if (
      raw.includes("scanner") ||
      raw.includes("banned") ||
      raw.includes("block") ||
      raw === "login_failed" ||
      raw === "wipe_all_data" ||
      raw === "recreate_schema" ||
      raw.endsWith("_failed")
    ) {
      return "danger";
    }

    if (
      raw.includes("rate_limited") ||
      raw.includes("locked") ||
      raw === "reset_password" ||
      raw === "set_role" ||
      raw === "set_active" ||
      raw === "security_setting_updated"
    ) {
      return "warn";
    }

    if (raw === "login" || raw === "logout") {
      return "success";
    }

    if (raw.startsWith("kiosk_") || raw.startsWith("resident_signin_")) {
      return "info";
    }

    return "neutral";
  }

  function computeSecurityState(data) {
    const settings = data.settings || {};
    const ipThreshold = Number(settings.attacker_ip_alert_threshold || 10);
    const userThreshold = Number(settings.targeted_username_alert_threshold || 10);
    const topIpAttempts = data.top_attacking_ips && data.top_attacking_ips.length
      ? Number(data.top_attacking_ips[0].attempts || 0)
      : 0;
    const topUserAttempts = data.targeted_usernames && data.targeted_usernames.length
      ? Number(data.targeted_usernames[0].attempts || 0)
      : 0;
    const topThreatScore = Number(data.top_threat_score || 0);
    const incidents = Array.isArray(data.recent_security_incidents) ? data.recent_security_incidents : [];
    const hasHighIncident = incidents.some(row => String(row.severity || "").toLowerCase() === "high");

    if ((data.banned_ips || []).length || (data.locked_usernames || []).length || topThreatScore >= 10 || hasHighIncident) {
      return {
        level: "CRITICAL",
        led: "red",
        pill: "danger",
        banner: "danger",
        title: "Active Threat Pressure Detected",
        copy: "The application layer is seeing hostile activity patterns, active defenses, or recent high severity indicators."
      };
    }

    if (topIpAttempts >= ipThreshold || topUserAttempts >= userThreshold) {
      return {
        level: "CRITICAL",
        led: "red",
        pill: "danger",
        banner: "danger",
        title: "Active Attack Detected",
        copy: "One or more sources are above defined hostile activity thresholds. Review the attack radar and threat queue."
      };
    }

    if (topThreatScore >= 5 || topIpAttempts >= 5 || topUserAttempts >= 6 || incidents.length > 0) {
      return {
        level: "ELEVATED",
        led: "amber",
        pill: "warn",
        banner: "warn",
        title: "Elevated Security Activity",
        copy: "Security activity is above normal baseline. Review active threats, rate limiting, and recent incidents."
      };
    }

    return {
      level: "NORMAL",
      led: "green",
      pill: "",
      banner: "",
      title: "System Stable",
      copy: "No active threat indicators are currently above alert threshold inside the application layer."
    };
  }

  function updateSecurityBanner(data) {
    const state = computeSecurityState(data);

    const pill = document.getElementById("security-status-pill");
    const pillLed = document.getElementById("security-status-led");
    const pillText = document.getElementById("security-status-text");
    const banner = document.getElementById("security-banner");
    const bannerTitle = document.getElementById("security-banner-title");
    const bannerCopy = document.getElementById("security-banner-copy");

    if (pill) {
      pill.className = "status-pill" + (state.pill ? " " + state.pill : "");
    }
    if (pillLed) {
      pillLed.className = "led " + state.led;
    }
    if (pillText) {
      pillText.textContent = "Security Level " + state.level;
    }
    if (banner) {
      banner.className = "security-banner" + (state.banner ? " " + state.banner : "");
    }
    if (bannerTitle) {
      bannerTitle.textContent = state.title;
    }
    if (bannerCopy) {
      bannerCopy.textContent = state.copy;
    }
  }

  function updateTopStats(data) {
    const hostileEvents = document.getElementById("failed-logins-stat");
    const attackers = document.getElementById("live-attackers-stat");
    const sessions = document.getElementById("staff-sessions-stat");
    const targeted = document.getElementById("targeted-accounts-stat");
    const defenses = document.getElementById("active-defenses-stat");
    const threatScore = document.getElementById("threat-score-stat");

    if (hostileEvents) hostileEvents.textContent = String(data.failed_login_count || 0);
    if (attackers) attackers.textContent = String((data.top_attacking_ips || []).length);
    if (sessions) sessions.textContent = String((data.recent_staff_sessions || []).length);
    if (targeted) targeted.textContent = String((data.targeted_usernames || []).length);
    if (defenses) defenses.textContent = String((data.locked_usernames || []).length + (data.banned_ips || []).length);
    if (threatScore) threatScore.textContent = String(data.top_threat_score || 0);
  }

  function updateKioskPanel(data) {
    const el = document.getElementById("kiosk-events-body");
    if (!el) return;

    const rows = data.kiosk_security_events || [];
    if (!rows.length) {
      el.innerHTML = `
        <tr>
          <td colspan="3" class="empty-state">No kiosk security activity recorded.</td>
        </tr>
      `;
      return;
    }

    el.innerHTML = rows.map(row => `
      <tr>
        <td>${escapeHtml(formatAmarilloTime(row.created_at || ""))}</td>
        <td class="event-cell">
          <span class="event-pill ${escapeHtml(eventClass(row.action_type || ""))}">
            ${escapeHtml(prettyLabel(row.action_type || ""))}
          </span>
        </td>
        <td class="detail-cell">${escapeHtml(row.action_details || "")}</td>
      </tr>
    `).join("");
  }

  function updateStaffSessions(data) {
    const el = document.getElementById("active-staff-session-body");
    if (!el) return;

    const rows = data.recent_staff_sessions || [];
    if (!rows.length) {
      el.innerHTML = `
        <tr>
          <td colspan="4" class="empty-state">No recent active staff sessions detected.</td>
        </tr>
      `;
      return;
    }

    el.innerHTML = rows.map(row => `
      <tr>
        <td class="event-cell">${escapeHtml(row.username || "")}</td>
        <td><span class="event-pill success">Active</span></td>
        <td class="event-cell">${escapeHtml(prettyLabel(row.last_action || "login"))}</td>
        <td>${escapeHtml(formatAmarilloTime(row.last_seen || ""))}</td>
      </tr>
    `).join("");
  }

  function updateSecurityIncidents(data) {
    const el = document.getElementById("security-incidents-list");
    if (!el) return;

    const rows = data.recent_security_incidents || [];
    if (!rows.length) {
      el.className = "";
      el.innerHTML = `<div class="empty-state">No security incidents recorded.</div>`;
      return;
    }

    el.className = "incident-list";
    el.innerHTML = rows.map(row => `
      <div class="incident-item">
        <div class="incident-top">
          <div>
            <span class="event-pill ${escapeHtml(row.severity || "neutral")}">
              ${escapeHtml(String(row.severity || "unknown").replace(/^./, c => c.toUpperCase()))}
            </span>
          </div>
          <div class="timeline-time">${escapeHtml(formatAmarilloTime(row.created_at || ""))}</div>
        </div>
        <div class="incident-title">${escapeHtml(row.title || "Security Incident")}</div>
        <div class="detail-cell">${escapeHtml(row.details || "")}</div>
        <div class="incident-meta">
          ${row.related_ip ? `IP: ${escapeHtml(row.related_ip)}` : ``}
          ${row.related_ip && row.related_username ? `<br>` : ``}
          ${row.related_username ? `Username: ${escapeHtml(row.related_username)}` : ``}
          ${row.status ? `<br>Status: ${escapeHtml(row.status)}` : ``}
        </div>
      </div>
    `).join("");
  }

  function updateThreatQueue(data) {
    const el = document.getElementById("active-threat-queue");
    if (!el) return;

    const rows = Array.isArray(data.top_threats) ? data.top_threats : [];
    if (!rows.length) {
      el.innerHTML = `<div class="empty-state">Threat scoring is not active yet or no scored threats are currently present.</div>`;
      return;
    }

    el.innerHTML = rows.slice(0, 8).map(row => {
      const score = Number(row.score || 0);
      let cls = "info";
      if (score >= 10) cls = "danger";
      else if (score >= 5) cls = "warn";

      return `
        <div class="live-feed-item">
          <div class="live-feed-top">
            <div>Threat Source</div>
            <div>Score ${escapeHtml(String(score))}</div>
          </div>
          <div class="live-feed-title">
            <span class="event-pill ${cls}">
              ${escapeHtml(row.ip || "Unknown IP")}
            </span>
          </div>
          <div class="detail-cell">
            ${escapeHtml(row.summary || "Suspicious repeated behavior detected from this source.")}
          </div>
        </div>
      `;
    }).join("");
  }

  function buildLiveActivityRows(data) {
    const combined = [];

    (data.recent_audit || []).slice(0, 4).forEach(row => {
      combined.push({
        source: "Audit",
        created_at: row.created_at || "",
        action_type: row.action_type || "",
        action_details: row.action_details || "",
      });
    });

    (data.recent_failed_logins || []).slice(0, 4).forEach(row => {
      combined.push({
        source: "Threat",
        created_at: row.created_at || "",
        action_type: row.action_type || "",
        action_details: row.action_details || "",
      });
    });

    (data.kiosk_security_events || []).slice(0, 4).forEach(row => {
      combined.push({
        source: "Kiosk",
        created_at: row.created_at || "",
        action_type: row.action_type || "",
        action_details: row.action_details || "",
      });
    });

    (data.recent_security_incidents || []).slice(0, 4).forEach(row => {
      combined.push({
        source: "Incident",
        created_at: row.created_at || "",
        action_type: row.incident_type || "",
        action_details: row.title || row.details || "",
      });
    });

    combined.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
    return combined.slice(0, 8);
  }

  function updateLiveActivity(data) {
    const el = document.getElementById("live-activity-list");
    if (!el) return;

    const rows = buildLiveActivityRows(data);
    if (!rows.length) {
      el.innerHTML = `<div class="empty-state">No live activity available.</div>`;
      return;
    }

    el.innerHTML = rows.map(row => `
      <div class="live-feed-item">
        <div class="live-feed-top">
          <div>${escapeHtml(row.source)}</div>
          <div>${escapeHtml(formatAmarilloTime(row.created_at || ""))}</div>
        </div>
        <div class="live-feed-title">
          <span class="event-pill ${escapeHtml(eventClass(row.action_type || ""))}">
            ${escapeHtml(prettyLabel(row.action_type || ""))}
          </span>
        </div>
        <div class="detail-cell">${escapeHtml(row.action_details || "")}</div>
      </div>
    `).join("");
  }

  function ensureAttackMap() {
    const mapEl = document.getElementById("attack-map");
    if (!mapEl || typeof window.L === "undefined") {
      return null;
    }

    if (!attackMap) {
      attackMap = window.L.map(mapEl, {
        zoomControl: true,
        attributionControl: true,
      }).setView([25, 0], 2);

      window.L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
          maxZoom: 6,
          minZoom: 2,
          attribution: "&copy; OpenStreetMap contributors",
        }
      ).addTo(attackMap);
    }

    return attackMap;
  }

  function updateAttackMap(data) {
    const map = ensureAttackMap();
    const emptyEl = document.getElementById("attack-map-empty");

    if (!map) {
      return;
    }

    attackMarkers.forEach(marker => map.removeLayer(marker));
    attackMarkers = [];

    const points = Array.isArray(data.attack_map_points) ? data.attack_map_points : [];

    if (!points.length) {
      if (emptyEl) {
        emptyEl.style.display = "block";
      }
      map.setView([25, 0], 2);
      setTimeout(() => map.invalidateSize(), 0);
      return;
    }

    if (emptyEl) {
      emptyEl.style.display = "none";
    }

    const bounds = [];

    points.forEach(point => {
      const lat = Number(point.lat);
      const lon = Number(point.lon);
      const attempts = Number(point.attempts || 0);

      if (Number.isNaN(lat) || Number.isNaN(lon)) {
        return;
      }

      bounds.push([lat, lon]);

      const marker = window.L.circleMarker([lat, lon], {
        radius: Math.min(16, Math.max(6, attempts + 2)),
        color: "#ff6b6b",
        weight: 2,
        fillColor: "#ff3b3b",
        fillOpacity: 0.7,
      }).addTo(map);

      marker.bindPopup(
        `<strong>${escapeHtml(point.ip || "")}</strong><br>` +
        `${escapeHtml(point.city || "")}${point.city && point.region ? ", " : ""}${escapeHtml(point.region || "")}<br>` +
        `${escapeHtml(point.country || "")}<br>` +
        `Events: ${escapeHtml(String(point.attempts || 0))}`
      );

      attackMarkers.push(marker);
    });

    if (bounds.length === 1) {
      map.setView(bounds[0], 4);
    } else if (bounds.length > 1) {
      map.fitBounds(bounds, { padding: [30, 30] });
    } else {
      map.setView([25, 0], 2);
    }

    setTimeout(() => map.invalidateSize(), 0);
  }

  function hydrateInitialThreatQueue() {
    updateThreatQueue({
      top_threats: initialTopThreats
    });

    const threatScore = document.getElementById("threat-score-stat");
    if (threatScore) {
      threatScore.textContent = String(initialTopThreatScore || 0);
    }
  }

  async function refreshLive() {
    try {
      const res = await fetch(liveUrl, {
        method: "GET",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
        cache: "no-store"
      });

      if (!res.ok) {
        return;
      }

      const data = await res.json();
      if (!data.ok) {
        return;
      }

      updateSecurityBanner(data);
      updateTopStats(data);
      updateKioskPanel(data);
      updateStaffSessions(data);
      updateSecurityIncidents(data);
      updateThreatQueue(data);
      updateLiveActivity(data);
      updateAttackMap(data);
    } catch (err) {
      console.error("Live dashboard refresh failed", err);
    }
  }

  if (initialAttackMapPoints.length) {
    updateAttackMap({ attack_map_points: initialAttackMapPoints });
  } else {
    updateAttackMap({ attack_map_points: [] });
  }

  hydrateInitialThreatQueue();
  refreshLive();
  setInterval(refreshLive, 10000);
})();

/* ---------------------------------------
   Security Control Confirmation Guard
--------------------------------------- */

document.addEventListener("DOMContentLoaded", function () {
  const securityForms = document.querySelectorAll(".security-control-actions form");

  securityForms.forEach(form => {
    form.addEventListener("submit", function (e) {
      const actionBtn = form.querySelector("button[type='submit']");
      const actionText = actionBtn ? actionBtn.innerText.trim() : "change this setting";

      const confirmMsg =
        "Are you sure you want to " +
        actionText.toLowerCase() +
        "?\n\nThis affects live system operations.";

      if (!confirm(confirmMsg)) {
        e.preventDefault();
      }
    });
  });
});
