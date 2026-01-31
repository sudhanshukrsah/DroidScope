/**
 * DroidScope v2 - Frontend JavaScript
 * Handles UI interactions, SSE streaming, and data visualization
 */

// ============== Global State ==============
let logStartTime = null;
let progressEventSource = null;
let logsEventSource = null;
let stagesEventSource = null;
let chartInstances = {};

// ============== Initialization ==============
document.addEventListener('DOMContentLoaded', () => {
    checkDeviceStatus();
    loadSettings();
    loadCategories();
    loadPersonas();
    
    // Check device status periodically
    setInterval(checkDeviceStatus, 10000);
});

// ============== Device Status ==============
async function checkDeviceStatus() {
    try {
        const response = await fetch('/api/device-status');
        const data = await response.json();
        
        const indicator = document.getElementById('deviceIndicator');
        const status = document.getElementById('deviceStatus');
        
        if (data.connected) {
            indicator.className = 'device-indicator p-2 connected';
            status.textContent = 'Device Connected';
            status.className = 'text-xs text-green-500';
        } else {
            indicator.className = 'device-indicator p-2 disconnected';
            status.textContent = 'Device Disconnected';
            status.className = 'text-xs text-red-500';
        }
    } catch (error) {
        console.error('Error checking device status:', error);
    }
}

// ============== Settings ==============
function openSettings() {
    document.getElementById('settingsModal').classList.remove('hidden');
}

function closeSettings() {
    document.getElementById('settingsModal').classList.add('hidden');
}

async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();
        
        if (settings.api_key) {
            document.getElementById('settingsApiKey').value = settings.api_key;
        }
        if (settings.llm_model) {
            document.getElementById('settingsModel').value = settings.llm_model;
        }
        if (settings.api_base) {
            document.getElementById('settingsApiBase').value = settings.api_base;
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

async function saveSettings() {
    const settings = {
        api_key: document.getElementById('settingsApiKey').value,
        llm_model: document.getElementById('settingsModel').value,
        api_base: document.getElementById('settingsApiBase').value
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            closeSettings();
            appendLog('Settings saved successfully', 'success');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        appendLog('Failed to save settings', 'error');
    }
}

// ============== Navigation ==============
function showSection(sectionName) {
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.section === sectionName) {
            btn.classList.add('active');
        }
    });
    
    // Update sections
    document.querySelectorAll('.section').forEach(section => {
        section.classList.remove('active');
    });
    document.getElementById(`${sectionName}Section`).classList.add('active');
    
    // Load data for specific sections
    if (sectionName === 'results') {
        loadResults();
    } else if (sectionName === 'library') {
        loadLibrary();
    } else if (sectionName === 'compare') {
        loadCompareData();
    }
}

// ============== Logging ==============
function clearLogs() {
    const terminal = document.getElementById('terminalOutput');
    terminal.innerHTML = '<div class="log-info text-zinc-500">Logs cleared</div>';
    logStartTime = null;
}

function appendLog(message, type = 'info') {
    if (!logStartTime) logStartTime = Date.now();
    
    const terminal = document.getElementById('terminalOutput');
    const elapsed = Date.now() - logStartTime;
    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    const timestamp = `[${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}]`;
    
    // Handle multi-line messages
    const lines = message.split('\n');
    lines.forEach(line => {
        if (line.trim()) {
            const entry = document.createElement('div');
            entry.className = `log-${type}`;
            entry.innerHTML = `<span class="text-zinc-600">${timestamp}</span> ${escapeHtml(line)}`;
            terminal.appendChild(entry);
        }
    });
    
    terminal.scrollTop = terminal.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============== Exploration ==============
async function startExploration() {
    const appName = document.getElementById('appName').value.trim();
    const category = document.getElementById('category').value;
    const persona = document.getElementById('persona').value;
    const customNavigation = document.getElementById('customNavigation').value.trim();
    const saveToMemory = document.getElementById('saveToMemory').checked;
    
    // Validation
    if (!appName) {
        alert('Please enter an application name');
        return;
    }
    if (!category) {
        alert('Please select a category');
        return;
    }
    
    // Reset UI
    logStartTime = null;
    clearLogs();
    resetStageCards();
    updateProgress(0, 'Starting exploration...');
    
    // Show scan section
    showSection('scan');
    
    // Disable start button, show stop button
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').classList.remove('hidden');
    
    try {
        appendLog(`Starting exploration for ${appName}...`, 'info');
        
        const response = await fetch('/api/run-test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                app_name: appName,
                category: category,
                persona: persona,
                custom_navigation: customNavigation,
                save_to_memory: saveToMemory
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        appendLog(`Exploration started for ${appName}`, 'success');
        
        // Start SSE listeners
        listenForProgress();
        listenForLogs();
        listenForStages();
        
    } catch (error) {
        console.error('Error starting exploration:', error);
        appendLog(`Error: ${error.message}`, 'error');
        resetExplorationUI();
    }
}

async function stopAgent() {
    if (!confirm('Are you sure you want to stop the exploration?')) return;
    
    try {
        appendLog('Stopping agent...', 'warning');
        
        const response = await fetch('/api/stop-agent', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            appendLog('Agent stopped', 'info');
            closeEventSources();
            resetExplorationUI();
        } else {
            appendLog(`Failed to stop: ${data.error}`, 'error');
        }
    } catch (error) {
        appendLog(`Error stopping agent: ${error.message}`, 'error');
    }
}

function resetExplorationUI() {
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').classList.add('hidden');
}

function resetStageCards() {
    for (let i = 1; i <= 4; i++) {
        const card = document.getElementById(`stage${i}Card`);
        const status = document.getElementById(`stage${i}Status`);
        card.className = 'bg-stone-900 border border-neutral-500 items-center flex rounded-2xl p-5 stage-card justify-between ';
        status.textContent = 'Pending';
        status.className = 'text-xs text-zinc-600';
    }
}

// ============== SSE Listeners ==============
function listenForProgress() {
    if (progressEventSource) progressEventSource.close();
    
    progressEventSource = new EventSource('/api/progress');
    
    progressEventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.keepalive) return;
        
        updateProgress(data.percentage, data.message);
        
        if (data.percentage >= 100) {
            closeEventSources();
            resetExplorationUI();
            setTimeout(() => {
                showSection('results');
                loadResults();
            }, 1500);
        } else if (data.percentage < 0) {
            closeEventSources();
            resetExplorationUI();
        }
    };
    
    progressEventSource.onerror = () => {
        progressEventSource.close();
    };
}

function listenForLogs() {
    if (logsEventSource) logsEventSource.close();
    
    logsEventSource = new EventSource('/api/logs');
    
    logsEventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.keepalive) return;
        
        appendLog(data.message, data.type || 'info');
    };
    
    logsEventSource.onerror = () => {
        logsEventSource.close();
    };
}

function listenForStages() {
    if (stagesEventSource) stagesEventSource.close();
    
    stagesEventSource = new EventSource('/api/stages');
    
    stagesEventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.keepalive) return;
        
        updateStageCard(data.stage, data.status);
    };
    
    stagesEventSource.onerror = () => {
        stagesEventSource.close();
    };
}

function closeEventSources() {
    if (progressEventSource) { progressEventSource.close(); progressEventSource = null; }
    if (logsEventSource) { logsEventSource.close(); logsEventSource = null; }
    if (stagesEventSource) { stagesEventSource.close(); stagesEventSource = null; }
}

// ============== Progress & Stages ==============
function updateProgress(percentage, message) {
    document.getElementById('progressBar').style.width = `${Math.max(0, percentage)}%`;
    document.getElementById('progressPercent').textContent = `${Math.max(0, percentage)}%`;
    document.getElementById('progressMessage').textContent = message;
}

function updateStageCard(stageNum, status) {
    const card = document.getElementById(`stage${stageNum}Card`);
    const statusEl = document.getElementById(`stage${stageNum}Status`);
    
    card.className = `bg-stone-900 border border-neutral-500 items-center flex rounded-2xl p-5 stage-card justify-between  ${status}`;
    
    const statusText = {
        'pending': 'Pending',
        'running': 'Running...',
        'completed': 'Completed ✓',
        'failed': 'Failed ✗'
    };
    
    statusEl.textContent = statusText[status] || status;
    statusEl.className = `text-xs ${status === 'completed' ? 'text-green-500' : status === 'failed' ? 'text-red-500' : status === 'running' ? 'text-amber-500' : 'text-zinc-600'}`;
}

// ============== Results ==============
async function loadResults() {
    try {
        const response = await fetch('/api/results');
        const data = await response.json();
        
        if (data.error) {
            console.log('No results yet:', data.error);
            return;
        }
        
        displayResults(data);
    } catch (error) {
        console.error('Error loading results:', error);
    }
}

function displayResults(data) {
    // Summary
    document.getElementById('summaryContent').innerHTML = marked.parse(data.summary || 'No summary available.');
    
    // Overall Rating
    const overall = data.overall_rating || {};
    document.getElementById('overallScore').textContent = overall.score || '-';
    document.getElementById('overallGrade').textContent = overall.grade || '-';
    document.getElementById('overallSummary').textContent = overall.summary || '';
    
    // Charts
    displayCharts(data);
    
    // Metrics Grid
    displayMetricsGrid(data);
    
    // Positive Findings
    displayPositive(data.positive || []);
    
    // Issues
    displayIssues(data.issues || []);
    
    // Dark Patterns
    if (data.dark_patterns && data.dark_patterns.length > 0) {
        document.getElementById('darkPatternsPanel').classList.remove('hidden');
        displayDarkPatterns(data.dark_patterns);
    } else {
        document.getElementById('darkPatternsPanel').classList.add('hidden');
    }
    
    // Recommendations
    displayRecommendations(data.recommendations || []);
}

function displayCharts(data) {
    // Destroy existing charts
    Object.values(chartInstances).forEach(chart => chart.destroy());
    chartInstances = {};
    
    const graphData = data.graph_data || {};
    
    // Radar Chart
    const radarMetrics = graphData.radar_metrics || {};
    chartInstances.radar = new Chart(document.getElementById('radarChart'), {
        type: 'radar',
        data: {
            labels: ['Navigation', 'Feedback', 'Consistency', 'Accessibility', 'Error Handling', 'Visual Design'],
            datasets: [{
                label: 'Score',
                data: [
                    radarMetrics.navigation || 0,
                    radarMetrics.feedback || 0,
                    radarMetrics.consistency || 0,
                    radarMetrics.accessibility || 0,
                    radarMetrics.error_handling || 0,
                    radarMetrics.visual_design || 0
                ],
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                borderColor: 'rgba(255, 255, 255, 0.8)',
                pointBackgroundColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                r: {
                    beginAtZero: true,
                    max: 10,
                    ticks: { color: '#71717a', stepSize: 2 },
                    grid: { color: '#27272a' },
                    angleLines: { color: '#27272a' },
                    pointLabels: { color: '#a1a1aa', font: { size: 10 } }
                }
            },
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'UX Dimensions', color: '#e4e4e7' }
            }
        }
    });
    
    // Severity Distribution
    const severity = graphData.severity_distribution || {};
    chartInstances.severity = new Chart(document.getElementById('severityChart'), {
        type: 'doughnut',
        data: {
            labels: ['Critical', 'High', 'Medium', 'Low'],
            datasets: [{
                data: [
                    severity.critical || 0,
                    severity.high || 0,
                    severity.medium || 0,
                    severity.low || 0
                ],
                backgroundColor: ['#ef4444', '#f97316', '#fbbf24', '#4ade80']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#a1a1aa', font: { size: 10 } } },
                title: { display: true, text: 'Issue Severity', color: '#e4e4e7' }
            }
        }
    });
    
    // Confidence Score Gauge
    const uxScore = data.ux_confidence_score?.score || 0;
    chartInstances.confidence = new Chart(document.getElementById('confidenceChart'), {
        type: 'doughnut',
        data: {
            labels: ['Score', 'Remaining'],
            datasets: [{
                data: [uxScore, 10 - uxScore],
                backgroundColor: [
                    uxScore >= 7 ? '#4ade80' : uxScore >= 5 ? '#fbbf24' : '#ef4444',
                    '#27272a'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            circumference: 180,
            rotation: -90,
            plugins: {
                legend: { display: false },
                title: { display: true, text: `UX Confidence: ${uxScore}/10`, color: '#e4e4e7' }
            }
        }
    });
}

function displayMetricsGrid(data) {
    const nav = data.navigation_metrics || {};
    const interaction = data.interaction_feedback || {};
    const visual = data.visual_hierarchy || {};
    const coverage = data.exploration_coverage || {};
    const stress = data.stress_test_results || {};
    
    const metrics = [
        { label: 'Screens', value: coverage.screens_discovered || 0 },
        { label: 'Max Depth', value: nav.max_depth || 0 },
        { label: 'Feedback Rate', value: `${interaction.visible_feedback_rate_pct || 0}%` },
        { label: 'CTA Clarity', value: visual.cta_visibility || '-' },
        { label: 'Dead Elements', value: `${coverage.dead_elements_pct || 0}%` },
        { label: 'Silent Failures', value: interaction.silent_failures || 0 },
        { label: 'Breakability', value: `${stress.breakability_score || '-'}/10` },
        { label: 'Complexity', value: `${data.complexity_score || '-'}/10` }
    ];
    
    document.getElementById('metricsGrid').innerHTML = metrics.map(m => `
        <div class="metric-card">
            <div class="metric-value">${m.value}</div>
            <div class="metric-label">${m.label}</div>
        </div>
    `).join('');
}

function displayPositive(items) {
    const container = document.getElementById('positiveContent');
    
    if (!items.length) {
        container.innerHTML = '<p class="text-zinc-500">No positive findings documented.</p>';
        return;
    }
    
    container.innerHTML = items.map(item => `
        <div class="result-card">
            <div class="flex items-center justify-between mb-2">
                <span class="font-medium">${item.aspect || 'Positive Finding'}</span>
                <span class="badge badge-good">Good</span>
            </div>
            <p class="text-zinc-400 text-sm">${item.description || ''}</p>
            ${item.location ? `<p class="text-xs text-zinc-600 mt-2">📍 ${item.location}</p>` : ''}
        </div>
    `).join('');
}

function displayIssues(items) {
    const container = document.getElementById('issuesContent');
    
    if (!items.length) {
        container.innerHTML = '<p class="text-zinc-500">No issues found.</p>';
        return;
    }
    
    container.innerHTML = items.map(item => {
        const severity = (item.severity || 'Medium').toLowerCase();
        return `
            <div class="result-card">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-medium">${item.category || 'Issue'}</span>
                    <span class="badge badge-${severity}">${item.severity || 'Medium'}</span>
                </div>
                <p class="text-zinc-400 text-sm mb-2">${item.description || ''}</p>
                <div class="text-xs text-zinc-600 space-y-1">
                    ${item.location ? `<p>📍 ${item.location}</p>` : ''}
                    ${item.impact ? `<p>💥 ${item.impact}</p>` : ''}
                    ${item.effort ? `<p>🔧 Effort: ${item.effort}</p>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function displayDarkPatterns(items) {
    const container = document.getElementById('darkPatternsContent');
    
    container.innerHTML = items.map(item => `
        <div class="result-card border-red-900">
            <div class="flex items-center justify-between mb-2">
                <span class="font-medium text-red-400">${item.type || 'Dark Pattern'}</span>
                <span class="badge badge-${(item.severity || 'medium').toLowerCase()}">${item.severity || 'Medium'}</span>
            </div>
            <p class="text-zinc-400 text-sm">${item.description || ''}</p>
            ${item.location ? `<p class="text-xs text-zinc-600 mt-2">📍 ${item.location}</p>` : ''}
        </div>
    `).join('');
}

function displayRecommendations(items) {
    const container = document.getElementById('recommendationsContent');
    
    if (!items.length) {
        container.innerHTML = '<p class="text-zinc-500">No recommendations available.</p>';
        return;
    }
    
    container.innerHTML = items.map(item => {
        const priority = (item.priority || 'Medium').toLowerCase();
        const impact = item.expected_impact || {};
        
        return `
            <div class="result-card">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-medium">${item.recommendation || 'Recommendation'}</span>
                    <span class="badge badge-${priority}">${item.priority || 'Medium'}</span>
                </div>
                <p class="text-zinc-400 text-sm mb-2">${item.rationale || ''}</p>
                <div class="flex gap-4 text-xs text-zinc-500">
                    ${item.effort ? `<span>🔧 ${item.effort} effort</span>` : ''}
                    ${impact.task_success_increase_pct ? `<span>📈 +${impact.task_success_increase_pct}% success</span>` : ''}
                    ${impact.error_reduction_pct ? `<span>🐛 -${impact.error_reduction_pct}% errors</span>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function downloadReport() {
    fetch('/api/results')
        .then(res => res.json())
        .then(data => {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `ux-analysis-${Date.now()}.json`;
            a.click();
            URL.revokeObjectURL(url);
        });
}

// ============== Library ==============
async function loadCategories() {
    try {
        const response = await fetch('/api/library/categories');
        const categories = await response.json();
        
        const selects = ['libraryCategory', 'compareCategory', 'category'];
        selects.forEach(id => {
            const select = document.getElementById(id);
            if (select && id !== 'category') {
                categories.forEach(cat => {
                    const option = document.createElement('option');
                    option.value = cat;
                    option.textContent = cat;
                    select.appendChild(option);
                });
            }
        });
    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

async function loadPersonas() {
    try {
        const response = await fetch('/api/library/personas');
        const personas = await response.json();
        
        const selects = ['libraryPersona', 'comparePersona'];
        selects.forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                personas.forEach(p => {
                    const option = document.createElement('option');
                    option.value = p;
                    option.textContent = p;
                    select.appendChild(option);
                });
            }
        });
    } catch (error) {
        console.error('Error loading personas:', error);
    }
}

async function loadLibrary() {
    const category = document.getElementById('libraryCategory').value;
    const persona = document.getElementById('libraryPersona').value;
    
    let url = '/api/library?';
    if (category) url += `category=${encodeURIComponent(category)}&`;
    if (persona) url += `persona=${encodeURIComponent(persona)}`;
    
    try {
        const response = await fetch(url);
        const explorations = await response.json();
        
        displayLibrary(explorations);
    } catch (error) {
        console.error('Error loading library:', error);
    }
}

function filterLibrary() {
    loadLibrary();
}

function displayLibrary(explorations) {
    const grid = document.getElementById('libraryGrid');
    
    if (!explorations.length) {
        grid.innerHTML = '<div class="col-span-2 text-center text-zinc-500 py-12">No explorations found</div>';
        return;
    }
    
    grid.innerHTML = explorations.map(exp => `
        <div class="panel p-4 cursor-pointer hover:border-zinc-500" onclick="viewExploration('${exp.id}')">
            <div class="flex items-center justify-between mb-2">
                <span class="font-medium">${exp.app_name}</span>
                ${exp.ux_score ? `<span class="text-lg font-bold">${exp.ux_score}/10</span>` : ''}
            </div>
            <div class="flex gap-2 mb-2">
                <span class="badge badge-medium">${exp.category}</span>
                <span class="badge badge-low">${exp.persona}</span>
            </div>
            <div class="text-xs text-zinc-500">
                ${exp.status === 'completed' ? '✓ Completed' : exp.status}
                • ${new Date(exp.created_at).toLocaleDateString()}
            </div>
        </div>
    `).join('');
}

async function viewExploration(explorationId) {
    try {
        const response = await fetch(`/api/results/${explorationId}`);
        const data = await response.json();
        
        if (data.error) {
            alert('Results not available for this exploration');
            return;
        }
        
        showSection('results');
        displayResults(data);
    } catch (error) {
        console.error('Error viewing exploration:', error);
    }
}

// ============== Compare ==============
async function loadCompareData() {
    const category = document.getElementById('compareCategory').value;
    const persona = document.getElementById('comparePersona').value;
    
    if (!category && !persona) {
        document.getElementById('compareTable').innerHTML = '<p class="text-zinc-500">Select a category or persona to compare results</p>';
        return;
    }
    
    let url = '/api/compare?';
    if (category) url += `category=${encodeURIComponent(category)}&`;
    if (persona) url += `persona=${encodeURIComponent(persona)}`;
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        displayCompareChart(data);
        displayCompareTable(data);
    } catch (error) {
        console.error('Error loading compare data:', error);
    }
}

function displayCompareChart(data) {
    if (chartInstances.compare) {
        chartInstances.compare.destroy();
    }
    
    const labels = data.map(d => d.app_name || 'Unknown');
    const scores = data.map(d => d.ux_score || 0);
    const complexity = data.map(d => d.complexity_score || 0);
    
    chartInstances.compare = new Chart(document.getElementById('compareChart'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'UX Score',
                    data: scores,
                    backgroundColor: 'rgba(74, 222, 128, 0.8)'
                },
                {
                    label: 'Complexity',
                    data: complexity,
                    backgroundColor: 'rgba(251, 191, 36, 0.8)'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 10,
                    ticks: { color: '#71717a' },
                    grid: { color: '#27272a' }
                },
                x: {
                    ticks: { color: '#a1a1aa' },
                    grid: { color: '#27272a' }
                }
            },
            plugins: {
                legend: { labels: { color: '#e4e4e7' } }
            }
        }
    });
}

function displayCompareTable(data) {
    const table = document.getElementById('compareTable');
    
    if (!data.length) {
        table.innerHTML = '<p class="text-zinc-500">No comparison data available</p>';
        return;
    }
    
    table.innerHTML = `
        <table class="w-full text-sm">
            <thead>
                <tr class="border-b border-zinc-800">
                    <th class="text-left py-2 px-3 text-zinc-400">App</th>
                    <th class="text-left py-2 px-3 text-zinc-400">Category</th>
                    <th class="text-left py-2 px-3 text-zinc-400">Persona</th>
                    <th class="text-center py-2 px-3 text-zinc-400">UX Score</th>
                    <th class="text-center py-2 px-3 text-zinc-400">Complexity</th>
                    <th class="text-left py-2 px-3 text-zinc-400">Date</th>
                </tr>
            </thead>
            <tbody>
                ${data.map(d => `
                    <tr class="border-b border-zinc-800 hover:bg-zinc-900">
                        <td class="py-2 px-3 font-medium">${d.app_name || 'Unknown'}</td>
                        <td class="py-2 px-3 text-zinc-400">${d.category || '-'}</td>
                        <td class="py-2 px-3 text-zinc-400">${d.persona || '-'}</td>
                        <td class="py-2 px-3 text-center">
                            <span class="font-bold ${d.ux_score >= 7 ? 'text-green-400' : d.ux_score >= 5 ? 'text-amber-400' : 'text-red-400'}">
                                ${d.ux_score || '-'}
                            </span>
                        </td>
                        <td class="py-2 px-3 text-center text-zinc-300">${d.complexity_score || '-'}</td>
                        <td class="py-2 px-3 text-zinc-500">${new Date(d.created_at).toLocaleDateString()}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}
