document.addEventListener('DOMContentLoaded', function() {
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
});

async function refreshSprint(sprintId) {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = 'Refreshing...'; btn.disabled = true;
  try {
    const resp = await fetch(`/sprints/${sprintId}/refresh`, { method: 'POST' });
    if (resp.ok) { location.reload(); } else { alert('Refresh failed: ' + (await resp.json()).detail); }
  } catch(e) { alert('Refresh failed: ' + e.message); }
  btn.disabled = false; btn.textContent = '🔄 Refresh Now';
}

async function closeForecast(sprintId) {
  if (!confirm('Close the forecast? This captures the baseline snapshot.')) return;
  const resp = await fetch(`/sprints/${sprintId}/close-forecast`, { method: 'POST' });
  if (resp.ok) { location.reload(); } else { alert('Failed: ' + (await resp.json()).detail); }
}

async function closeSprint(sprintId) {
  if (!confirm('Close this sprint? The report will be frozen.')) return;
  const resp = await fetch(`/sprints/${sprintId}/close`, { method: 'POST' });
  if (resp.ok) { location.reload(); } else { alert('Failed: ' + (await resp.json()).detail); }
}

async function syncSprints(teamId) {
  const btn = document.getElementById('sync-btn');
  btn.textContent = 'Syncing...'; btn.disabled = true;
  const resp = await fetch(`/teams/${teamId}/sync-sprints`, { method: 'POST' });
  if (resp.ok) { location.reload(); } else { alert('Sync failed'); }
}
