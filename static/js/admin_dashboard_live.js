(function(){
  const config = window.adminDashboardConfig || {};
  const liveUrl = config.liveUrl;

  if(!liveUrl){
    return;
  }

  function escapeHtml(value){
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function prettyLabel(value){
    const raw = String(value || "");
    if(!raw) return "Unknown Event";
    if(raw === "login_failed") return "Login Failed";
    if(raw === "login") return "Login Success";
    if(raw === "logout") return "Logout";
    if(raw === "profile_update") return "Profile Updated";
    if(raw === "set_role") return "Role Changed";
    if(raw === "set_active") return "Account Status Changed";
    if(raw === "reset_password") return "Password Reset";
    if(raw === "wipe_all_data") return "Data Wipe";
    if(raw === "recreate_schema") return "Schema Recreated";
    if(raw === "security_setting_updated") return "Security Setting Updated";
    if(raw.startsWith("kiosk_")){
      return raw.slice(6).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
    }
    return raw.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function eventClass(value){
    const raw = String(value || "");
    if(["login_failed", "wipe_all_data", "recreate_schema"].includes(raw) || raw.startsWith("kiosk_block") || raw.startsWith("kiosk_denied")){
      return "danger";
    }
    if(["reset_password", "set_role", "set_active", "security_setting_updated"].includes(raw)){
      return "warn";
    }
    if(["login", "logout"].includes(raw)){
      return "success";
    }
    if(raw.startsWith("kiosk_")){
      return "info";
    }
    return "neutral";
  }

  function computeSecurityState(data){
    const settings = data.settings || {};
    const ipThreshold = Number(settings.attacker_ip_alert_threshold || 10);
    const userThreshold = Number(settings.targeted_username_alert_threshold || 10);
    const topIpAttempts = data.top_attacking_ips && data.top_attacking_ips.length ? Number(data.top_attacking_ips[0].attempts || 0) : 0;
    const topUserAttempts = data.targeted_usernames && data.targeted_usernames.length ? Number(data.targeted_usernames[0].attempts || 0) : 0;

    if((data.banned_ips || []).length){
      return {
        level: "ACTIVE ATTACK",
        led: "red",
        pill: "danger",
        banner: "danger",
        title: "Active Defense Triggered",
        copy: "One or more IP addresses are currently banned. Immediate hostile activity is being contained."
      };
    }

    if((data.locked_usernames || []).length){
      return {
        level: "ACTIVE ATTACK",
        led: "red",
        pill: "danger",
        banner: "danger",
        title: "Account Targeting Detected",
        copy: "Username lockouts are active. Repeated credential attacks are in progress or were recently contained."
      };
    }

    if(topIpAttempts >= ipThreshold){
      return {
        level: "ACTIVE ATTACK",
        led: "red",
        pill: "danger",
        banner: "danger",
        title: "Active Attack Detected",
        copy: "An IP has crossed high volume login failure thresholds. Review the attack radar and intrusion timeline."
      };
    }

    if(topUserAttempts >= userThreshold){
      return {
        level: "ACTIVE ATTACK",
        led: "red",
        pill: "danger",
        banner: "danger",
        title: "Focused Username Attack Detected",
        copy: "One or more staff usernames are being repeatedly targeted. Review lockout pressure and affected accounts."
      };
    }

    if(topIpAttempts >= 5){
      return {
        level: "ELEVATED",
        led: "yellow",
        pill: "warn",
        banner: "warn",
        title: "Elevated Threat Posture",
        copy: "Failed login activity is elevated. Continue monitoring intrusion events and attacker concentration."
      };
    }

    if(topUserAttempts >= 6){
      return {
        level: "ELEVATED",
        led: "yellow",
        pill: "warn",
        banner: "warn",
        title: "Targeted Login Pressure",
        copy: "Repeated failures are clustering around specific usernames. Watch for lockouts and follow on activity."
      };
    }

    return {
      level: "NORMAL",
      led: "green",
      pill: "",
      banner: "",
      title: "System Stable",
      copy: "No active threat indicators are currently above alert threshold."
    };
  }

  function updateSecurityBanner(data){
    const state = computeSecurityState(data);

    const pill = document.getElementById("security-status-pill");
    const pillLed = document.getElementById("security-status-led");
    const pillText = document.getElementById("security-status-text");
    const banner = document.getElementById("security-banner");
    const bannerTitle = document.getElementById("security-banner-title");
    const bannerCopy = document.getElementById("security-banner-copy");

    if(pill){
      pill.className = "status-pill" + (state.pill ? " " + state.pill : "");
    }
    if(pillLed){
      pillLed.className = "led " + state.led;
    }
    if(pillText){
      pillText.textContent = "Security Level " + state.level;
    }
    if(banner){
      banner.className = "security-banner" + (state.banner ? " " + state.banner : "");
    }
    if(bannerTitle){
      bannerTitle.textContent = state.title;
    }
    if(bannerCopy){
      bannerCopy.textContent = state.copy;
    }
  }

  function updateTopStats(data){
    const failed = document.getElementById("failed-logins-stat");
    const attackers = document.getElementById("live-attackers-stat");
    const sessions = document.getElementById("staff-sessions-stat");
    const targeted = document.getElementById("targeted-accounts-stat");
    const defenses = document.getElementById("active-defenses-stat");

    if(failed) failed.textContent = String(data.failed_login_count || 0);
    if(attackers) attackers.textContent = String((data.top_attacking_ips || []).length);
    if(sessions) sessions.textContent = String((data.recent_staff_sessions || []).length);
    if(targeted) targeted.textContent = String((data.targeted_usernames || []).length);
    if(defenses) defenses.textContent = String((data.locked_usernames || []).length + (data.banned_ips || []).length);
  }

  function updateKioskPanel(data){
    const el = document.getElementById("kiosk-events-body");
    if(!el) return;

    const rows = data.kiosk_security_events || [];
    if(!rows.length){
      el.className = "empty-state";
      el.innerHTML = "No kiosk security activity recorded.";
      return;
    }

    el.className = "";
    el.innerHTML = rows.map(row => `
      <tr>
        <td>${escapeHtml(row.created_at || "")}</td>
        <td class="event-cell">
          <span class="event-pill ${escapeHtml(eventClass(row.action_type || ""))}">
            ${escapeHtml(prettyLabel(row.action_type || ""))}
          </span>
        </td>
        <td class="detail-cell">${escapeHtml(row.action_details || "")}</td>
      </tr>
    `).join("");
  }

  function updateStaffSessions(data){
    const el = document.getElementById("active-staff-session-body");
    if(!el) return;

    const rows = data.recent_staff_sessions || [];
    if(!rows.length){
      el.className = "empty-state";
      el.innerHTML = "No recent active staff sessions detected.";
      return;
    }

    el.className = "";
    el.innerHTML = rows.map(row => `
      <tr>
        <td class="event-cell">${escapeHtml(row.username || "")}</td>
        <td><span class="event-pill success">Active</span></td>
        <td class="event-cell">${escapeHtml(prettyLabel(row.last_action || "login"))}</td>
        <td>${escapeHtml(row.last_seen || "")}</td>
      </tr>
    `).join("");
  }

  function updateSecurityIncidents(data){
    const el = document.getElementById("security-incidents-list");
    if(!el) return;

    const rows = data.recent_security_incidents || [];
    if(!rows.length){
      el.className = "empty-state";
      el.innerHTML = "No security incidents recorded.";
      return;
    }

    el.className = "incident-list";
    el.innerHTML = rows.map(row => `
      <div class="incident-item">
        <div class="incident-top">
          <div>
            <span class="event-pill ${escapeHtml(row.severity || "neutral")}">${escapeHtml(String(row.severity || "unknown").replace(/^./, c => c.toUpperCase()))}</span>
          </div>
          <div class="timeline-time">${escapeHtml(row.created_at || "")}</div>
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

  function buildLiveActivityRows(data){
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
        source: "Intrusion",
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

  function updateLiveActivity(data){
    const el = document.getElementById("live-activity-list");
    if(!el) return;

    const rows = buildLiveActivityRows(data);
    if(!rows.length){
      el.innerHTML = `<div class="empty-state">No live activity available.</div>`;
      return;
    }

    el.innerHTML = rows.map(row => `
      <div class="live-feed-item">
        <div class="live-feed-top">
          <div>${escapeHtml(row.source)}</div>
          <div>${escapeHtml(row.created_at || "")}</div>
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

  async function refreshLive(){
    try{
      const res = await fetch(liveUrl, {
        method: "GET",
        headers: {"X-Requested-With": "XMLHttpRequest"},
        credentials: "same-origin",
        cache: "no-store"
      });

      if(!res.ok){
        return;
      }

      const data = await res.json();
      if(!data.ok){
        return;
      }

      updateSecurityBanner(data);
      updateTopStats(data);
      updateKioskPanel(data);
      updateStaffSessions(data);
      updateSecurityIncidents(data);
      updateLiveActivity(data);
    }catch(err){
      console.error("Live dashboard refresh failed", err);
    }
  }

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
