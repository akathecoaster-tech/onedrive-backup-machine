async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (_) {
      data = { raw: text };
    }
  }
  if (!response.ok) {
    throw new Error(data.error || data.message || `HTTP ${response.status}`);
  }
  return data;
}

function el(id) {
  return document.getElementById(id);
}

function renderStatus(status) {
  const authClass = status.authenticated ? "ok" : "bad";
  el("status").innerHTML = `
    <div>API: <strong>${status.api || "unknown"}</strong> · v${status.version || "?"}</div>
    <div>Client ID configured: <strong>${status.client_id_configured ? "yes" : "no"}</strong></div>
    <div>Authenticated: <strong class="${authClass}">${status.authenticated ? "yes" : "no"}</strong></div>
    <div>Running: <strong>${status.running ? "yes" : "no"}</strong></div>
    <div>Backup root: <code>${status.backup_root || ""}</code></div>
    <div>Latest job: <strong>${status.latest_job_status || "idle"}</strong></div>
  `;
}

function renderTasks(tasks) {
  if (!tasks.length) {
    el("tasks").textContent = "No tasks configured.";
    return;
  }
  const rows = tasks
    .map(
      (task) => `
      <tr>
        <td><code>${task.id}</code><div class="muted">${task.name || ""}</div></td>
        <td>${task.mode || "incremental"}</td>
        <td><code>${task.schedule || "-"}</code></td>
        <td><code>${task.remote_path || "(root)"}</code></td>
        <td><button data-run-task="${task.id}">Run</button></td>
      </tr>`
    )
    .join("");
  el("tasks").innerHTML = `
    <table>
      <thead><tr><th>Task</th><th>Mode</th><th>Schedule</th><th>Remote path</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  document.querySelectorAll("[data-run-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api(`/api/tasks/${button.dataset.runTask}/run`, { method: "POST" });
        await refresh();
      } catch (error) {
        alert(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderJobs(jobs) {
  if (!jobs.length) {
    el("jobs").textContent = "No jobs yet.";
    return;
  }
  const rows = jobs
    .slice(0, 10)
    .map((job) => {
      const summary = job.summary || {};
      return `
        <tr>
          <td><strong>${job.status || "unknown"}</strong><div class="muted">${job.task_name || job.task_id || ""}</div></td>
          <td>${job.mode || ""}</td>
          <td>${summary.downloaded ?? 0} / ${summary.skipped ?? 0} / ${summary.errors ?? 0}</td>
          <td class="muted">${job.started_at || "-"}<br>${job.completed_at || ""}</td>
        </tr>`;
    })
    .join("");
  el("jobs").innerHTML = `
    <table>
      <thead><tr><th>Status</th><th>Mode</th><th>Downloaded / Skipped / Errors</th><th>Timestamps</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function refresh() {
  const [status, tasks, jobs] = await Promise.all([
    api("/api/status"),
    api("/api/tasks"),
    api("/api/jobs"),
  ]);
  renderStatus(status);
  renderTasks(tasks.tasks || []);
  renderJobs(jobs.jobs || []);
}

el("loginStart").addEventListener("click", async () => {
  try {
    const data = await api("/api/login/start", { method: "POST" });
    el("loginHelp").hidden = false;
    el("loginHelp").textContent =
      data.message ||
      `Go to ${data.verification_uri} and enter code ${data.user_code}, then click Complete login.`;
  } catch (error) {
    alert(error.message);
  }
});

el("loginComplete").addEventListener("click", async () => {
  try {
    await api("/api/login/complete", { method: "POST" });
    el("loginHelp").hidden = false;
    el("loginHelp").textContent = "Login completed.";
    await refresh();
  } catch (error) {
    alert(error.message);
  }
});

el("runBackup").addEventListener("click", async () => {
  try {
    await api("/api/backup", { method: "POST" });
    await refresh();
  } catch (error) {
    alert(error.message);
  }
});

refresh();
setInterval(refresh, 10000);
