'use strict';

const SEV_NAMES = ['EMERGENCY', 'ALERT', 'CRITICAL', 'ERROR', 'WARNING', 'NOTICE', 'INFO', 'DEBUG'];
const MAX_LIVE_ROWS = 2000;

// Minutes back for each time range option
const TIME_RANGE_MINUTES = { '15m': 15, '1h': 60, '6h': 360, '24h': 1440, '7d': 10080, '30d': 43200 };

// ---------------------------------------------------------------------------
// Root app component
// ---------------------------------------------------------------------------
function syslogApp() {
  return {
    tabs: [
      { id: 'live',     label: 'Live' },
      { id: 'search',   label: 'Search' },
      { id: 'devices',  label: 'Devices' },
      { id: 'stats',    label: 'Stats' },
      { id: 'settings', label: 'Settings' },
    ],
    activeTab: 'live',

    // Live tab state
    wsConnected: false,
    liveMessages: [],
    liveCount: 0,
    livePaused: false,
    autoScroll: true,
    liveMinSev: '-1',
    liveIpFilter: '',

    // Time range / history state
    liveTimeRange: localStorage.getItem('syslog_timeRange') || '1h',
    historyLoading: false,
    historicalCount: 0,

    // Search tab state
    search: { keyword: '', source_ip: '', min_severity: '', max_severity: '',
               start_time: '', end_time: '', limit: '200' },
    searchResults: [],
    searchLoading: false,

    // Devices tab state
    devices: [],
    editingDevice: null,

    // Stats bar
    statsBar: '',
    _statsInterval: null,
    _ws: null,

    get filteredLiveMessages() {
      const minSev = parseInt(this.liveMinSev);
      const ipFilter = this.liveIpFilter.trim().toLowerCase();
      return this.liveMessages.filter(m => {
        if (minSev >= 0 && m.severity > minSev) return false;
        if (ipFilter && !m.source_ip.toLowerCase().includes(ipFilter)) return false;
        return true;
      });
    },

    init() {
      this.connectWs();
      this.loadDevices();
      this._statsInterval = setInterval(() => this.fetchStatsBar(), 5000);
      this.fetchStatsBar();
      // Load history based on saved/default time range on page load
      if (this.liveTimeRange !== 'live') {
        this.$nextTick(() => this.loadHistory());
      }
    },

    connectWs() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/ws/live`);
      this._ws = ws;

      ws.onopen = () => { this.wsConnected = true; };
      ws.onclose = () => {
        this.wsConnected = false;
        setTimeout(() => this.connectWs(), 3000);
      };
      ws.onerror = () => { ws.close(); };
      ws.onmessage = (ev) => {
        if (this.livePaused) return;
        try {
          const pkt = JSON.parse(ev.data);
          if (pkt.type === 'messages' && Array.isArray(pkt.data)) {
            this.liveMessages.push(...pkt.data);
            // Trim total rows but preserve historical — only trim live (non-historical) overflow
            const liveOnly = this.liveMessages.filter(m => !m._historical);
            if (liveOnly.length > MAX_LIVE_ROWS) {
              // Remove oldest live messages (those that appear first after historical block)
              let liveRemoved = 0;
              const toRemove = liveOnly.length - MAX_LIVE_ROWS;
              this.liveMessages = this.liveMessages.filter(m => {
                if (!m._historical && liveRemoved < toRemove) { liveRemoved++; return false; }
                return true;
              });
            }
            this.liveCount = this.liveMessages.length;
            if (this.autoScroll) {
              this.$nextTick(() => {
                const el = document.getElementById('live-scroll');
                if (el) el.scrollTop = el.scrollHeight;
              });
            }
          }
        } catch (_) {}
      };
    },

    // Called when user changes the time range dropdown
    onTimeRangeChange() {
      localStorage.setItem('syslog_timeRange', this.liveTimeRange);
      // Drop existing historical messages
      this.liveMessages = this.liveMessages.filter(m => !m._historical);
      this.historicalCount = 0;
      if (this.liveTimeRange !== 'live') {
        this.loadHistory();
      }
    },

    async loadHistory() {
      this.historyLoading = true;
      try {
        const params = new URLSearchParams({ limit: 2000 });
        if (this.liveTimeRange !== 'all') {
          const mins = TIME_RANGE_MINUTES[this.liveTimeRange];
          const startTime = new Date(Date.now() - mins * 60 * 1000);
          // DB stores timestamps in local time, so strip timezone offset before sending
          const startStr = new Date(startTime.getTime() - startTime.getTimezoneOffset() * 60000)
                             .toISOString().substring(0, 19);
          params.set('start_time', startStr);
        }
        const r = await fetch('/api/messages?' + params.toString());
        const data = await r.json();
        const msgs = (data.messages || []).reverse(); // API returns newest-first; we want oldest-first

        if (!msgs.length) { this.historyLoading = false; return; }

        // Normalize to match live message shape
        const historical = msgs.map(m => ({
          ...m,
          severity_name: SEV_NAMES[m.severity] ?? String(m.severity),
          received_at: m.received_at || m.timestamp,
          _historical: true,
        }));

        // Prepend historical before any existing live messages
        this.liveMessages = [...historical, ...this.liveMessages.filter(m => !m._historical)];
        this.historicalCount = historical.length;
        this.liveCount = this.liveMessages.length;

        // Scroll to bottom to show most recent (live) end
        if (this.autoScroll) {
          this.$nextTick(() => {
            const el = document.getElementById('live-scroll');
            if (el) el.scrollTop = el.scrollHeight;
          });
        }
      } catch (e) {
        console.error('Failed to load history', e);
      } finally {
        this.historyLoading = false;
      }
    },

    clearHistory() {
      this.liveMessages = this.liveMessages.filter(m => !m._historical);
      this.historicalCount = 0;
      this.liveTimeRange = 'live';
      localStorage.setItem('syslog_timeRange', 'live');
    },

    clearLive() {
      this.liveMessages = [];
      this.liveCount = 0;
      this.historicalCount = 0;
    },

    async runSearch() {
      this.searchLoading = true;
      try {
        const params = new URLSearchParams();
        if (this.search.keyword)     params.set('keyword', this.search.keyword);
        if (this.search.source_ip)   params.set('source_ip', this.search.source_ip);
        if (this.search.min_severity !== '') params.set('min_severity', this.search.min_severity);
        if (this.search.max_severity !== '') params.set('max_severity', this.search.max_severity);
        if (this.search.start_time)  params.set('start_time', this.search.start_time);
        if (this.search.end_time)    params.set('end_time', this.search.end_time);
        params.set('limit', this.search.limit);
        const r = await fetch('/api/messages?' + params.toString());
        const data = await r.json();
        this.searchResults = data.messages || [];
      } catch (e) {
        console.error('Search failed', e);
      } finally {
        this.searchLoading = false;
      }
    },

    exportSearchCsv() {
      if (!this.searchResults.length) return;
      const cols = ['timestamp', 'received_at', 'source_ip', 'severity', 'severity_name',
                    'facility', 'hostname', 'app_name', 'message', 'protocol'];
      const rows = [cols.join(',')];
      for (const m of this.searchResults) {
        rows.push(cols.map(c => JSON.stringify(m[c] ?? '')).join(','));
      }
      const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'syslog-export.csv';
      a.click();
    },

    async loadDevices() {
      const r = await fetch('/api/devices');
      const d = await r.json();
      this.devices = d.devices || [];
    },

    async saveDevice(dev) {
      await fetch(`/api/devices/${dev.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: dev.display_name,
          vendor: dev.vendor,
          color: dev.color,
          hostname: dev.hostname,
        }),
      });
      this.editingDevice = null;
    },

    async fetchStatsBar() {
      try {
        const r = await fetch('/api/stats');
        const s = await r.json();
        this.statsBar = `${(s.total_messages || 0).toLocaleString()} msgs | ${s.msgs_per_sec || 0}/s | ${s.total_devices || 0} devices`;
      } catch (_) {}
    },

    severityName(n) { return SEV_NAMES[n] || n; },
  };
}

// ---------------------------------------------------------------------------
// Stats tab component (nested Alpine component)
// ---------------------------------------------------------------------------
function statsTab() {
  return {
    cards: [],
    topDevices: [],
    listeners: {},
    _chart: null,
    _interval: null,

    init() {
      this.refresh();
      this._interval = setInterval(() => this.refresh(), 5000);
    },
    destroy() { clearInterval(this._interval); },

    async refresh() {
      try {
        const r = await fetch('/api/stats');
        const s = await r.json();
        this.cards = [
          { label: 'Total Messages', value: (s.total_messages || 0).toLocaleString() },
          { label: 'Messages / sec', value: (s.msgs_per_sec || 0).toFixed(1) },
          { label: 'Messages last hour', value: (s.messages_last_hour || 0).toLocaleString() },
          { label: 'Known Devices', value: s.total_devices || 0 },
        ];
        this.topDevices = s.top_devices || [];
        this.listeners = s.listeners || {};
        this.updateChart(s.severity_counts || {});
      } catch (_) {}
    },

    updateChart(counts) {
      const labels = SEV_NAMES;
      const data = labels.map((_, i) => counts[i] || 0);
      const colors = ['#7f1d1d','#7c2d12','#831843','#1e3a5f','#1c3a2b','#334155','#334155','#1e293b'];

      if (this._chart) {
        this._chart.data.datasets[0].data = data;
        this._chart.update();
        return;
      }
      const canvas = document.getElementById('sevChart');
      if (!canvas) return;
      this._chart = new Chart(canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [{ label: 'Messages', data, backgroundColor: colors, borderRadius: 3 }],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
            y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
          },
        },
      });
    },
  };
}

// ---------------------------------------------------------------------------
// Settings tab component
// ---------------------------------------------------------------------------
function settingsTab() {
  return {
    cfg: {
      listeners: { udp: { enabled: true, port: 1514, host: '0.0.0.0' }, tcp: { enabled: false, port: 514 } },
      storage: { retention_days: 0 },
      web: { port: 8080 },
      ntp: { enabled: false, host: '0.0.0.0', port: 123 },
      email: {
        enabled: false,
        smtp_host: '',
        smtp_port: 587,
        smtp_user: '',
        smtp_password: '',
        use_tls: true,
        from_address: '',
        recipients: [],
        recipients_text: '',   // UI-only: newline-separated list
      },
      email_alerts: {
        link_state: true,
        spanning_tree: true,
        login_failure: true,
        login_failure_threshold: 3,
        login_failure_window_secs: 300,
        new_device: true,
        config_change: true,
        power_supply: true,
        high_temperature: true,
        ntp_sync_failure: true,
        device_reboot: true,
        port_security: true,
        fan_failure: true,
        sfp_alarm: true,
        cooldown_minutes: 15,
      },
    },
    saveMsg: '',
    testEmailMsg: '',
    testEmailOk: true,

    async init() {
      try {
        const r = await fetch('/api/config');
        const data = await r.json();
        if (data.listeners) {
          if (data.listeners.udp) Object.assign(this.cfg.listeners.udp, data.listeners.udp);
          if (data.listeners.tcp) Object.assign(this.cfg.listeners.tcp, data.listeners.tcp);
        }
        if (data.storage) Object.assign(this.cfg.storage, data.storage);
        if (data.web) Object.assign(this.cfg.web, data.web);
        if (data.ntp) Object.assign(this.cfg.ntp, data.ntp);
        if (data.email) {
          Object.assign(this.cfg.email, data.email);
          // Convert recipients array -> textarea text
          const recip = data.email.recipients;
          this.cfg.email.recipients_text = Array.isArray(recip) ? recip.join('\n') : '';
        }
        if (data.email_alerts) Object.assign(this.cfg.email_alerts, data.email_alerts);
      } catch (_) {}
    },

    async saveSettings() {
      try {
        // Build payload: convert recipients_text -> recipients array, exclude UI-only field
        const payload = JSON.parse(JSON.stringify(this.cfg));
        payload.email.recipients = payload.email.recipients_text
          .split('\n')
          .map(s => s.trim())
          .filter(s => s.length > 0);
        delete payload.email.recipients_text;

        await fetch('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        this.saveMsg = 'Saved!';
        setTimeout(() => { this.saveMsg = ''; }, 3000);
      } catch (e) {
        this.saveMsg = 'Error saving.';
      }
    },

    async testEmail() {
      this.testEmailMsg = 'Sending…';
      this.testEmailOk = true;
      try {
        // Pass current form values so the test works before saving
        const smtpPayload = {
          smtp_host:     this.cfg.email.smtp_host,
          smtp_port:     this.cfg.email.smtp_port,
          smtp_user:     this.cfg.email.smtp_user,
          smtp_password: this.cfg.email.smtp_password,
          use_tls:       this.cfg.email.use_tls,
          from_address:  this.cfg.email.from_address,
          recipients:    this.cfg.email.recipients_text
                           .split('\n').map(s => s.trim()).filter(s => s.length > 0),
        };
        const r = await fetch('/api/config/test-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(smtpPayload),
        });
        const data = await r.json();
        if (data.ok) {
          this.testEmailMsg = 'Test email sent!';
          this.testEmailOk = true;
        } else {
          this.testEmailMsg = data.error || 'Failed to send.';
          this.testEmailOk = false;
        }
      } catch (e) {
        this.testEmailMsg = 'Request failed.';
        this.testEmailOk = false;
      }
      setTimeout(() => { this.testEmailMsg = ''; }, 6000);
    },
  };
}
