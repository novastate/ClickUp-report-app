document.addEventListener('DOMContentLoaded', function() {
  // KPI-card filter behavior (unchanged)
  document.querySelectorAll('.kpi-card[data-filter]').forEach(card => {
    card.addEventListener('click', function() {
      const filter = this.dataset.filter;
      const isActive = this.classList.contains('active');
      document.querySelectorAll('.kpi-card').forEach(c => c.classList.remove('active'));
      if (isActive) {
        document.querySelectorAll('.task-table tr[data-filter]').forEach(row => row.classList.remove('filtered-out'));
      } else {
        this.classList.add('active');
        document.querySelectorAll('.task-table tr[data-filter]').forEach(row => {
          if (row.dataset.filter.includes(filter)) { row.classList.remove('filtered-out'); }
          else { row.classList.add('filtered-out'); }
        });
      }
    });
  });

  // Drain a pending toast (queued before location.reload)
  const pending = sessionStorage.getItem('pending_toast');
  if (pending) {
    sessionStorage.removeItem('pending_toast');
    try {
      const { message, kind } = JSON.parse(pending);
      showToast(message, kind);
    } catch (e) { /* malformed — ignore */ }
  }
});

function showToast(message, kind) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'toast ' + (kind || 'info');
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function deferToast(message, kind) {
  // Queue a toast that survives the next location.reload()
  try {
    sessionStorage.setItem('pending_toast', JSON.stringify({ message, kind: kind || 'success' }));
  } catch (e) { /* storage full / private mode — ignore */ }
}

async function refreshSprint(sprintId) {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = 'Refreshing...'; btn.disabled = true;
  try {
    const resp = await fetch(`/sprints/${sprintId}/refresh`, { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.json().then(d => d.detail).catch(() => 'unknown');
      showToast('Refresh misslyckades: ' + detail, 'error');
      btn.disabled = false; btn.textContent = 'Refresh Now';
      return;
    }
    deferToast('Refresh klar');
    location.reload();
  } catch (e) {
    showToast('Refresh misslyckades: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Refresh Now';
  }
}

async function closeForecast(sprintId) {
  if (!confirm('Close the forecast? This captures the baseline snapshot.')) return;
  try {
    const resp = await fetch(`/sprints/${sprintId}/close-forecast`, { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.json().then(d => d.detail).catch(() => 'unknown');
      showToast('Close forecast misslyckades: ' + detail, 'error');
      return;
    }
    deferToast('Forecast låst');
    location.reload();
  } catch (e) {
    showToast('Close forecast misslyckades: ' + e.message, 'error');
  }
}

async function closeSprint(sprintId) {
  if (!confirm('Close this sprint? The report will be frozen.')) return;
  try {
    const resp = await fetch(`/sprints/${sprintId}/close`, { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.json().then(d => d.detail).catch(() => 'unknown');
      showToast('Close sprint misslyckades: ' + detail, 'error');
      return;
    }
    deferToast('Sprint stängd');
    location.reload();
  } catch (e) {
    showToast('Close sprint misslyckades: ' + e.message, 'error');
  }
}

async function syncSprints(teamId) {
  const btn = document.getElementById('sync-btn');
  btn.textContent = 'Syncing...'; btn.disabled = true;
  try {
    const resp = await fetch(`/teams/${teamId}/sync-sprints`, { method: 'POST' });
    if (!resp.ok) {
      showToast('Sync misslyckades', 'error');
      btn.disabled = false; btn.textContent = 'Sync from ClickUp';
      return;
    }
    const data = await resp.json().catch(() => ({ synced: 0 }));
    const count = data.synced || 0;
    const msg = count === 0
      ? 'Inga nya sprintar hittades.'
      : 'Sync klar — ' + count + ' ' + (count === 1 ? 'sprint' : 'sprintar') + ' synkade.';
    deferToast(msg);
    location.reload();
  } catch (e) {
    showToast('Sync misslyckades: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Sync from ClickUp';
  }
}
