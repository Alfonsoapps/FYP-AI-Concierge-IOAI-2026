/* ============================================================
   Team Leader + Safety - shared frontend helpers
   Vanilla JS, fetch-based (consistent with the rest of the app).
   ============================================================ */
window.TeamSafety = (function () {
    // Escape user-supplied text before inserting into innerHTML.
    function escape(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Format an ISO timestamp into a short, readable local string.
    function formatTime(iso) {
        if (!iso) return 'No check-in recorded';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return escape(iso);
        return d.toLocaleString([], {
            month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    }

    // Map a status string to a colored badge span.
    function statusBadge(status) {
        const map = {
            'Safe': 'status-safe',
            'Pending Check-in': 'status-pending',
            'SOS Active': 'status-sos',
            'New': 'status-new',
            'In Progress': 'status-progress',
            'Resolved': 'status-resolved',
        };
        const cls = map[status] || 'status-pending';
        return `<span class="status-badge ${cls}">${escape(status)}</span>`;
    }

    async function getJSON(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error('Request failed: ' + res.status);
        return res.json();
    }

    async function sendJSON(url, method, body) {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const msg = (data && data.detail) ? data.detail : ('Request failed: ' + res.status);
            throw new Error(msg);
        }
        return data;
    }

    // Read the current participant role from localStorage.
    function role() { return localStorage.getItem('participant_role') || ''; }
    function name() { return localStorage.getItem('participant_name') || ''; }

    // Restrict Team Leader pages to the Team Leader role. Non-leaders are
    // redirected home. If onboarding was skipped, we allow through so the
    // demo remains usable.
    function requireLeader() {
        const r = role();
        if (r && r !== 'Team Leader') {
            window.location.href = '/';
        }
    }

    // Simple toast notification.
    let toastEl = null;
    let toastTimer = null;
    function toast(message, type) {
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.className = 'toast';
            document.body.appendChild(toastEl);
        }
        toastEl.textContent = message;
        toastEl.className = 'toast show' + (type ? ' ' + type : '');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { toastEl.className = 'toast'; }, 3000);
    }

    return {
        escape: escape,
        formatTime: formatTime,
        statusBadge: statusBadge,
        getJSON: getJSON,
        sendJSON: sendJSON,
        role: role,
        name: name,
        requireLeader: requireLeader,
        toast: toast,
    };
})();
