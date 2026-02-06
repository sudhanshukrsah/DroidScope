// DroidScope Frontend JavaScript

// Global state
let logStartTime = null;
let eventSources = {};
let charts = {};
let currentSection = 'scan';
let latestResultData = null;

// Log optimization
const MAX_LOG_ENTRIES = 500; // Keep only last 500 log entries
let logQueue = []; // Queue for batching log renders
let logRenderTimer = null;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    // Check device status
    checkDeviceStatus();
    setInterval(checkDeviceStatus, 10000);
    
    // Load settings
    loadSettings();
});

// Section Navigation
function showSection(section, clickedElement) {
    currentSection = section;
    
    // Hide all sections
    document.getElementById('scanSection').classList.add('hidden');
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('librarySection').classList.add('hidden');
    document.getElementById('compareSection').classList.add('hidden');
    
    // Show selected section
    document.getElementById(section + 'Section').classList.remove('hidden');
    
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    if (clickedElement) {
        clickedElement.classList.add('active');
    } else {
        // Find and activate the button by section name
        const navButton = document.querySelector(`[onclick*="showSection('${section}"`);
        if (navButton) navButton.classList.add('active');
    }
    
    // Load data for section
    if (section === 'library') loadLibrary();
    if (section === 'results') loadResults();
}

// Device Status
async function checkDeviceStatus() {
    try {
        const response = await fetch('/api/device-status');
        const data = await response.json();
        const indicator = document.getElementById('deviceIndicator');
        const statusText = document.getElementById('deviceStatusText');
        
        if (!indicator || !statusText) {
            console.warn('Device indicator elements not found');
            return;
        }
        
        if (data.connected) {
            indicator.classList.remove('device-disconnected');
            indicator.classList.add('device-connected');
            statusText.textContent = 'Device connected';
            statusText.className = 'text-xs whitespace-nowrap text-green-400';
        } else {
            indicator.classList.remove('device-connected');
            indicator.classList.add('device-disconnected');
            statusText.textContent = 'Device not connected';
            statusText.className = 'text-xs whitespace-nowrap text-red-400';
        }
    } catch (error) {
        console.error('Device status check failed:', error);
        const indicator = document.getElementById('deviceIndicator');
        const statusText = document.getElementById('deviceStatusText');
        
        if (indicator) {
            indicator.classList.remove('device-connected');
            indicator.classList.add('device-disconnected');
        }
        if (statusText) {
            statusText.textContent = 'Device not connected';
            statusText.className = 'text-xs whitespace-nowrap text-red-400';
        }
    }
}

// Logging
function appendLog(message, type = 'info') {
    if (!logStartTime) logStartTime = Date.now();
    
    // Add to queue instead of rendering immediately
    logQueue.push({ message, type, time: Date.now() });
    
    // Debounce rendering - render every 100ms max
    if (!logRenderTimer) {
        logRenderTimer = setTimeout(() => {
            renderLogQueue();
            logRenderTimer = null;
        }, 100);
    }
}

function renderLogQueue() {
    if (logQueue.length === 0) return;
    
    // Use requestAnimationFrame for smoother rendering
    requestAnimationFrame(() => {
        try {
            const terminalOutput = document.getElementById('terminalOutput');
            if (!terminalOutput) return;
            
            const fragment = document.createDocumentFragment();
            
            const colors = {
                info: 'text-zinc-400',
                success: 'text-green-400',
                warning: 'text-yellow-400',
                error: 'text-red-400',
                agent: 'text-blue-400'
            };
            
            // Process queued logs (limit to 100 per batch to avoid blocking)
            const logsToProcess = logQueue.splice(0, 100);
            
            logsToProcess.forEach(({ message, type, time }) => {
                const elapsed = time - logStartTime;
                const seconds = Math.floor(elapsed / 1000);
                const minutes = Math.floor(seconds / 60);
                const hours = Math.floor(minutes / 60);
                
                const timestamp = `[${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}]`;
                
                const lines = message.split('\n');
                lines.forEach(line => {
                    if (line.trim()) {
                        const entry = document.createElement('div');
                        entry.className = `${colors[type] || 'text-zinc-400'}`;
                        entry.innerHTML = `<span class="text-zinc-600">${timestamp}</span> ${escapeHtml(line)}`;
                        fragment.appendChild(entry);
                    }
                });
            });
            
            // Append all at once
            terminalOutput.appendChild(fragment);
            
            // Limit total entries - remove old ones if exceeds limit
            const entries = terminalOutput.children;
            if (entries.length > MAX_LOG_ENTRIES) {
                const toRemove = entries.length - MAX_LOG_ENTRIES;
                for (let i = 0; i < toRemove; i++) {
                    terminalOutput.removeChild(entries[0]);
                }
            }
            
            // Scroll to bottom (throttled)
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
            
            // If there are still logs in queue, schedule another render
            if (logQueue.length > 0) {
                logRenderTimer = setTimeout(() => {
                    renderLogQueue();
                    logRenderTimer = null;
                }, 50);
            }
        } catch (err) {
            console.error('Error rendering logs:', err);
            logQueue = []; // Clear queue on error to prevent infinite loop
        }
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function clearLogs() {
    const terminalOutput = document.getElementById('terminalOutput');
    terminalOutput.innerHTML = '<div class="text-zinc-500">[00:00:00] Logs cleared</div>';
    logStartTime = null;
    logQueue = [];
    if (logRenderTimer) {
        clearTimeout(logRenderTimer);
        logRenderTimer = null;
    }
}

// Start Test
async function startTest() {
    const appName = document.getElementById('appName').value.trim();
    const category = document.getElementById('category').value;
    const persona = document.getElementById('persona').value;
    const customNavigation = document.getElementById('customNavigation').value.trim();
    const maxDepth = parseInt(document.getElementById('maxDepth').value);
    const saveToMemory = document.getElementById('saveToMemory').checked;
    
    if (!appName) {
        alert('Please enter an app name');
        return;
    }
    if (!category) {
        alert('Please select a category');
        return;
    }
    
    logStartTime = null;
    clearLogs();
    resetStageIndicators();
    
    // Show stop button
    document.getElementById('stopBtn').classList.remove('hidden');
    document.getElementById('startBtn').disabled = true;
    document.getElementById('startBtn').classList.add('opacity-50');
    
    // Start listening for updates BEFORE starting the test to avoid missing logs
    listenForProgress();
    listenForLogs();
    listenForStages();
    
    try {
        appendLog('Starting exploration...', 'info');
        
        const response = await fetch('/api/run-test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                app_name: appName,
                category: category,
                persona: persona,
                custom_navigation: customNavigation,
                max_depth: maxDepth,
                save_to_memory: saveToMemory
            })
        });
        
        const data = await response.json();
        appendLog(`Exploration started for ${appName}`, 'success');
        
    } catch (error) {
        appendLog('Error: ' + error.message, 'error');
        resetExploration();
    }
}

// SSE Listeners
function listenForProgress() {
    if (eventSources.progress) {
        try {
            eventSources.progress.close();
        } catch (e) {
            // Ignore
        }
    }
    
    const source = new EventSource('/api/progress');
    eventSources.progress = source;
    
    source.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.keepalive) return;
            
            updateProgress(data.message, data.percentage);
            
            if (data.percentage >= 100) {
                source.close();
                // Immediately load and display results
                loadResultsAndShow().catch(err => console.error('Error loading results:', err));
            } else if (data.percentage < 0) {
                source.close();
                appendLog('Exploration failed', 'error');
                resetExploration();
            }
        } catch (err) {
            console.error('Error processing progress:', err);
        }
    };
    
    source.onerror = () => {
        try {
            source.close();
        } catch (e) {
            // Ignore
        }
    };
}

async function loadResultsAndShow() {
    // Small delay to ensure backend has saved results
    await new Promise(resolve => setTimeout(resolve, 500));
    
    try {
        const response = await fetch('/api/results');
        if (response.ok) {
            latestResultData = await response.json();
            displayResults(latestResultData);
            showSectionDirect('results');
        }
    } catch (error) {
        console.error('Error loading results after completion:', error);
    }
    
    resetExploration();
}

function showSectionDirect(section) {
    currentSection = section;
    
    // Hide all sections
    document.getElementById('scanSection').classList.add('hidden');
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('librarySection').classList.add('hidden');
    document.getElementById('compareSection').classList.add('hidden');
    
    // Show selected section
    document.getElementById(section + 'Section').classList.remove('hidden');
    
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(btn => {
        if (btn.textContent.toLowerCase().includes(section.substring(0, 4))) {
            btn.classList.add('active');
        }
    });
}

function listenForLogs() {
    if (eventSources.logs) {
        try {
            eventSources.logs.close();
        } catch (e) {
            // Ignore close errors
        }
    }
    
    console.log('[SSE] Connecting to /api/logs...');
    const source = new EventSource('/api/logs');
    eventSources.logs = source;
    
    source.onopen = () => {
        console.log('[SSE] Logs connection opened');
    };
    
    source.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.keepalive) return;
            
            // Display log immediately (backend already batched it)
            appendLog(data.message, data.type || 'info');
            
        } catch (err) {
            console.error('[SSE] Error parsing log:', err);
        }
    };
    
    source.onerror = (err) => {
        // Render any pending logs before closing
        if (logRenderTimer) {
            clearTimeout(logRenderTimer);
            logRenderTimer = null;
        }
        renderLogQueue();
        try {
            source.close();
        } catch (e) {
            // Ignore close errors
        }
    };
}

function listenForStages() {
    if (eventSources.stages) {
        try {
            eventSources.stages.close();
        } catch (e) {
            // Ignore
        }
    }
    
    const source = new EventSource('/api/stages');
    eventSources.stages = source;
    
    source.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.keepalive) return;
            updateStageIndicator(data.stage, data.status);
            
            const stageInfo = document.getElementById('currentStageInfo');
            const stageDesc = document.getElementById('stageDescription');
            if (stageInfo) stageInfo.classList.remove('hidden');
            if (stageDesc) stageDesc.textContent = data.message || `Stage ${data.stage} ${data.status}`;
        } catch (err) {
            console.error('Error processing stage update:', err);
        }
    };
    
    source.onerror = () => {
        try {
            source.close();
        } catch (e) {
            // Ignore
        }
    };
}

// Progress & Stage Updates
function updateProgress(message, percentage) {
    document.getElementById('progressBar').style.width = percentage + '%';
    document.getElementById('progressPercent').textContent = percentage + '%';
    document.getElementById('progressMessage').textContent = message;
}

function updateStageIndicator(stage, status) {
    const indicator = document.getElementById('stage' + stage);
    if (!indicator) return;
    
    indicator.classList.remove('stage-pending', 'stage-running', 'stage-completed', 'stage-failed');
    indicator.classList.add('stage-' + status);
}

function resetStageIndicators() {
    for (let i = 1; i <= 4; i++) {
        const indicator = document.getElementById('stage' + i);
        indicator.classList.remove('stage-running', 'stage-completed', 'stage-failed');
        indicator.classList.add('stage-pending');
    }
    document.getElementById('currentStageInfo').classList.add('hidden');
    updateProgress('Ready to start...', 0);
}

// Stop Agent
async function stopAgent() {
    if (!confirm('Stop the exploration?')) return;
    
    try {
        appendLog('Stopping agent...', 'warning');
        const response = await fetch('/api/stop-agent', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            appendLog('Agent stopped', 'info');
        } else {
            appendLog('Failed to stop: ' + data.error, 'error');
        }
    } catch (error) {
        appendLog('Error: ' + error.message, 'error');
    }
}

// Reset
function resetExploration() {
    try {
        document.getElementById('stopBtn').classList.add('hidden');
        document.getElementById('startBtn').disabled = false;
        document.getElementById('startBtn').classList.remove('opacity-50');
    } catch (e) {
        console.error('Error updating buttons:', e);
    }
    
    // Render any pending logs before closing
    if (logRenderTimer) {
        clearTimeout(logRenderTimer);
        logRenderTimer = null;
    }
    renderLogQueue();
    
    // Close all event sources safely
    Object.values(eventSources).forEach(source => {
        if (source) {
            try {
                source.close();
            } catch (e) {
                // Ignore close errors
            }
        }
    });
    eventSources = {};
    
    resetStageIndicators();
}

// Load Results
async function loadResults() {
    try {
        const response = await fetch('/api/results');
        if (!response.ok) {
            document.getElementById('resultsSection').innerHTML = '<p class="text-zinc-500 p-6">No results available yet. Run an exploration first.</p>';
            return;
        }
        
        const data = await response.json();
        displayResults(data);
        
    } catch (error) {
        console.error('Error loading results:', error);
    }
}

function displayResults(data) {
    // Store latest result data
    latestResultData = data;
    
    console.log('[DEBUG] Displaying results:', {
        hasData: !!data,
        hasSummary: !!data?.summary,
        exploration_id: data?.exploration_id || 'unknown',
        source: 'database'
    });
    
    // Summary
    document.getElementById('summaryContent').innerHTML = marked.parse(data.summary || 'No summary available.');
    
    // Metrics Grid
    const navMetrics = data.navigation_metrics || {};
    const appMetadata = data.app_metadata || {};
    const uxScore = data.ux_confidence_score || {};
    const feedbackMetrics = data.interaction_feedback || {};
    
    document.getElementById('metricsGrid').innerHTML = `
        <div class="metric-stat-card">
            <div class="text-2xl font-bold text-white">${appMetadata.screens_discovered || 0}</div>
            <div class="text-xs text-zinc-500 uppercase">Screens</div>
        </div>
        <div class="metric-stat-card">
            <div class="text-2xl font-bold text-white">${navMetrics.max_depth || 0}</div>
            <div class="text-xs text-zinc-500 uppercase">Max Depth</div>
        </div>
        <div class="metric-stat-card">
            <div class="text-2xl font-bold ${getScoreColor(uxScore.score || 0)}">${uxScore.score || 0}/10</div>
            <div class="text-xs text-zinc-500 uppercase">UX Score</div>
        </div>
        <div class="metric-stat-card">
            <div class="text-2xl font-bold text-white">${(data.issues || []).length}</div>
            <div class="text-xs text-zinc-500 uppercase">Issues</div>
        </div>
        <div class="metric-stat-card">
            <div class="text-2xl font-bold text-white">${(data.positive || []).length}</div>
            <div class="text-xs text-zinc-500 uppercase">Strengths</div>
        </div>
        <div class="metric-stat-card">
            <div class="text-2xl font-bold text-white">${feedbackMetrics.visible_feedback_rate_pct || 0}%</div>
            <div class="text-xs text-zinc-500 uppercase">Feedback Rate</div>
        </div>
        <div class="metric-stat-card">
            <div class="text-2xl font-bold text-white">${data.complexity_score || 0}/10</div>
            <div class="text-xs text-zinc-500 uppercase">Complexity</div>
        </div>
        <div class="metric-stat-card">
            <div class="text-2xl font-bold text-white">${navMetrics.hub_screen_count || 0}</div>
            <div class="text-xs text-zinc-500 uppercase">Hub Screens</div>
        </div>
    `;
    
    // Charts
    renderCharts(data);
    
    // Positive findings
    const positiveHtml = (data.positive || []).map(item => `
        <div class="result-card">
            <div class="flex justify-between items-start mb-2">
                <span class="font-semibold text-white">${item.aspect || 'Positive'}</span>
                <span class="badge badge-good">Good</span>
            </div>
            <p class="text-gray-400 text-sm">${item.description || ''}</p>
            ${item.location ? `<p class="text-zinc-600 text-xs mt-2">📍 ${item.location}</p>` : ''}
        </div>
    `).join('') || '<p class="text-zinc-500">No positive findings documented.</p>';
    document.getElementById('positiveContent').innerHTML = positiveHtml;
    
    // Issues
    const issuesHtml = (data.issues || []).map(item => {
        const severity = item.severity || 'Medium';
        return `
            <div class="result-card">
                <div class="flex justify-between items-start mb-2">
                    <span class="font-semibold text-white">${item.category || 'Issue'}</span>
                    <span class="badge badge-${severity.toLowerCase()}">${severity}</span>
                </div>
                <p class="text-gray-400 text-sm">${item.description || ''}</p>
                ${item.location ? `<p class="text-zinc-600 text-xs mt-2">📍 ${item.location}</p>` : ''}
                ${item.impact ? `<p class="text-zinc-600 text-xs">💥 Impact: ${item.impact}</p>` : ''}
            </div>
        `;
    }).join('') || '<p class="text-zinc-500">No issues found.</p>';
    document.getElementById('issuesContent').innerHTML = issuesHtml;
    
    // Recommendations
    const recsHtml = (data.recommendations || []).map(item => {
        const priority = item.priority || 'Medium';
        return `
            <div class="result-card">
                <div class="flex justify-between items-start mb-2">
                    <span class="font-semibold text-white">${item.recommendation || 'Recommendation'}</span>
                    <div class="flex gap-2">
                        <span class="badge badge-${priority.toLowerCase()}">${priority}</span>
                        ${item.effort ? `<span class="text-xs text-zinc-500">Effort: ${item.effort}</span>` : ''}
                    </div>
                </div>
                <p class="text-gray-400 text-sm">${item.rationale || ''}</p>
            </div>
        `;
    }).join('') || '<p class="text-zinc-500">No recommendations available.</p>';
    document.getElementById('recommendationsContent').innerHTML = recsHtml;
    
    // Dark Patterns - only show if any detected
    const darkPatterns = data.dark_patterns_detected || [];
    const darkPatternsSection = document.getElementById('darkPatternsSection');
    if (darkPatterns.length > 0) {
        darkPatternsSection.classList.remove('hidden');
        document.getElementById('darkPatternsContent').innerHTML = darkPatterns.map(pattern => `
            <div class="flex items-start gap-2 mb-2">
                <span class="text-red-400">⚠️</span>
                <span class="text-red-200">${pattern}</span>
            </div>
        `).join('');
    } else {
        darkPatternsSection.classList.add('hidden');
    }
    
    // Persona Insights
    const personaInsights = data.persona_insights || {};
    const personaHtml = `
        <div class="flex items-center justify-between mb-4">
            <span class="text-white font-medium">${personaInsights.persona || 'Unknown'} Perspective</span>
            <span class="text-lg font-bold ${getScoreColor(personaInsights.alignment_score || 0)}">${personaInsights.alignment_score || 0}/10</span>
        </div>
        ${(personaInsights.key_observations || []).length > 0 ? `
            <ul class="list-disc list-inside text-gray-400 space-y-1">
                ${personaInsights.key_observations.map(obs => `<li>${obs}</li>`).join('')}
            </ul>
        ` : '<p class="text-zinc-500">No specific observations recorded.</p>'}
    `;
    document.getElementById('personaInsightsContent').innerHTML = personaHtml;
    
    resetExploration();
}

function getScoreColor(score) {
    if (score >= 7) return 'text-green-400';
    if (score >= 5) return 'text-yellow-400';
    return 'text-red-400';
}

function renderCharts(data) {
    // Destroy existing charts
    Object.values(charts).forEach(chart => chart && chart.destroy());
    
    const navMetrics = data.navigation_metrics || {};
    const appMetadata = data.app_metadata || {};
    
    // Depth Chart - changed to polar area
    charts.depth = new Chart(document.getElementById('depthChart'), {
        type: 'polarArea',
        data: {
            labels: ['Screens', 'Max Depth', 'Avg Depth', 'Hub Screens'],
            datasets: [{
                data: [
                    appMetadata.screens_discovered || 0,
                    navMetrics.max_depth || 0,
                    navMetrics.avg_depth || 0,
                    navMetrics.hub_screen_count || 0
                ],
                backgroundColor: [
                    'rgba(59, 130, 246, 0.6)',
                    'rgba(139, 92, 246, 0.6)',
                    'rgba(236, 72, 153, 0.6)',
                    'rgba(245, 158, 11, 0.6)'
                ],
                borderColor: [
                    'rgba(59, 130, 246, 1)',
                    'rgba(139, 92, 246, 1)',
                    'rgba(236, 72, 153, 1)',
                    'rgba(245, 158, 11, 1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: 'Navigation Metrics', color: '#a1a1aa' },
                legend: { labels: { color: '#a1a1aa' }, position: 'bottom' }
            },
            scales: {
                r: {
                    ticks: { color: '#71717a', backdropColor: 'transparent' },
                    grid: { color: '#3f3f46' }
                }
            }
        }
    });
    
    // Severity Chart
    const issues = data.issues || [];
    const severityCounts = { High: 0, Medium: 0, Low: 0 };
    issues.forEach(i => severityCounts[i.severity || 'Medium']++);
    
    charts.severity = new Chart(document.getElementById('severityChart'), {
        type: 'doughnut',
        data: {
            labels: Object.keys(severityCounts),
            datasets: [{
                data: Object.values(severityCounts),
                backgroundColor: ['#ef4444', '#f59e0b', '#22c55e']
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: 'Issue Severity', color: '#a1a1aa' },
                legend: { labels: { color: '#a1a1aa' } }
            }
        }
    });
    
    // Score Chart
    const uxScore = data.ux_confidence_score || {};
    charts.score = new Chart(document.getElementById('scoreChart'), {
        type: 'radar',
        data: {
            labels: ['Coverage', 'Consistency', 'Feedback', 'Recovery'],
            datasets: [{
                label: 'UX Factors',
                data: [
                    (uxScore.factors || {}).exploration_coverage || 5,
                    (uxScore.factors || {}).interaction_consistency || 5,
                    (uxScore.factors || {}).feedback_reliability || 5,
                    (uxScore.factors || {}).recovery_robustness || 5
                ],
                backgroundColor: 'rgba(255, 255, 255, 0.2)',
                borderColor: 'rgba(255, 255, 255, 0.8)'
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: 'UX Factors', color: '#a1a1aa' },
                legend: { display: false }
            },
            scales: {
                r: {
                    beginAtZero: true,
                    max: 10,
                    ticks: { color: '#71717a', backdropColor: 'transparent' },
                    grid: { color: '#3f3f46' },
                    pointLabels: { color: '#a1a1aa' }
                }
            }
        }
    });
}

// Download Report
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

// Library
async function loadLibrary() {
    const category = document.getElementById('libraryCategory').value;
    const persona = document.getElementById('libraryPersona').value;
    
    try {
        const params = new URLSearchParams();
        if (category) params.append('category', category);
        if (persona) params.append('persona', persona);
        
        const response = await fetch('/api/library?' + params.toString());
        const data = await response.json();
        
        const tbody = document.getElementById('libraryTable');
        
        if (!data.items || data.items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-zinc-500 py-8">No explorations found</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.items.map(item => {
            const hasResults = item.ux_score !== null;
            return `
                <tr class="hover:bg-zinc-800/50">
                    <td class="text-white">${item.app_name}</td>
                    <td class="text-zinc-400">${item.category}</td>
                    <td class="text-zinc-400">${item.persona || '-'}</td>
                    <td class="text-white font-semibold">${item.ux_score ? item.ux_score.toFixed(1) : '<span class="text-zinc-600">N/A</span>'}</td>
                    <td class="text-zinc-500">${item.completed_at ? new Date(item.completed_at).toLocaleDateString() : '-'}</td>
                    <td class="flex gap-2">
                        ${hasResults 
                            ? `<button onclick="viewResult(${item.id})" class="text-blue-400 hover:text-blue-300 text-sm">View</button>`
                            : `<span class="text-zinc-600 text-sm">No Results</span>`
                        }
                        <button onclick="deleteResult(${item.id})" class="text-red-400 hover:text-red-300 text-sm">Delete</button>
                    </td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Error loading library:', error);
    }
}

async function viewResult(explorationId) {
    try {
        const response = await fetch(`/api/results/${explorationId}`);
        
        if (!response.ok) {
            appendLog('No results found for this exploration. The analysis may not have completed successfully.', 'warning');
            return;
        }
        
        const data = await response.json();
        
        if (data.error) {
            appendLog('Error: ' + data.error, 'warning');
            console.error('View result error:', data.error);
            return;
        }
        
        // Use showSectionDirect to avoid event issues
        showSectionDirect('results');
        displayResults(data);
        appendLog(`Loaded results for exploration #${explorationId}`, 'success');
    } catch (error) {
        console.error('Error viewing result:', error);
        appendLog('Error loading results: ' + error.message, 'error');
    }
}

async function deleteResult(explorationId) {
    if (!confirm('Are you sure you want to delete this result? This cannot be undone.')) return;
    
    try {
        const response = await fetch(`/api/results/${explorationId}`, { method: 'DELETE' });
        const data = await response.json();
        
        if (data.success) {
            appendLog('Result deleted successfully', 'success');
            loadLibrary(); // Refresh the library
        } else {
            appendLog('Failed to delete: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error deleting result:', error);
        appendLog('Error deleting result', 'error');
    }
}

// Comparison
async function loadComparison() {
    const category = document.getElementById('compareCategory').value;
    const persona = document.getElementById('comparePersona').value;
    
    if (!category || !persona) {
        document.getElementById('comparisonContent').innerHTML = '<p class="text-zinc-500 text-center py-12">Select category and persona to compare results</p>';
        return;
    }
    
    try {
        const response = await fetch(`/api/compare?category=${encodeURIComponent(category)}&persona=${encodeURIComponent(persona)}`);
        const data = await response.json();
        
        if (!data.items || data.items.length < 2) {
            document.getElementById('comparisonContent').innerHTML = '<p class="text-zinc-500 text-center py-12">Need at least 2 results to compare</p>';
            return;
        }
        
        // Build comparison view
        const items = data.items.slice(0, 5); // Max 5 for comparison
        const summary = data.comparison_summary || {};
        
        let html = `
            <!-- UX Score Comparison Chart -->
            <div class="bg-zinc-900 border border-zinc-700 rounded-lg p-6 mb-6">
                <h3 class="text-lg font-semibold text-white mb-4">UX Score Comparison</h3>
                <div class="comparison-chart">
                    <canvas id="comparisonChart"></canvas>
                </div>
            </div>
            
            <!-- Common Features -->
            ${summary.common_features && summary.common_features.length > 0 ? `
            <div class="bg-zinc-900 border border-zinc-700 rounded-lg p-6 mb-6">
                <h3 class="text-lg font-semibold text-white mb-4">
                    <span class="text-green-400">✓</span> Common Features Across All Apps
                </h3>
                <div class="flex flex-wrap gap-2">
                    ${summary.common_features.map(feature => `
                        <span class="px-3 py-1 bg-green-900/30 text-green-400 rounded-full text-sm border border-green-700/50">
                            ${feature}
                        </span>
                    `).join('')}
                </div>
            </div>
            ` : ''}
            
            <!-- Detailed App Comparison -->
            <div class="grid grid-cols-1 lg:grid-cols-${Math.min(items.length, 3)} gap-6 mb-6">
        `;
        
        items.forEach(item => {
            const analysis = item.analysis_json || {};
            const issues = item.issues || [];
            const positives = item.positives || [];
            const distinctFeatures = item.distinct_features || [];
            
            // Categorize issues by severity
            const highIssues = issues.filter(i => i.severity === 'High');
            const mediumIssues = issues.filter(i => i.severity === 'Medium');
            const lowIssues = issues.filter(i => i.severity === 'Low');
            
            html += `
                <div class="bg-zinc-900 border border-zinc-700 rounded-lg p-5">
                    <!-- App Header -->
                    <div class="mb-4 pb-4 border-b border-zinc-700">
                        <h4 class="font-bold text-white text-lg mb-1">${item.app_name}</h4>
                        <p class="text-zinc-500 text-sm">${new Date(item.completed_at).toLocaleDateString()}</p>
                    </div>
                    
                    <!-- UX Score Badge -->
                    <div class="mb-4">
                        <div class="flex items-center justify-between mb-2">
                            <span class="text-zinc-400 text-sm">UX Score</span>
                            <span class="text-2xl font-bold ${
                                item.ux_score >= 8 ? 'text-green-400' : 
                                item.ux_score >= 6 ? 'text-yellow-400' : 'text-red-400'
                            }">${item.ux_score || '-'}<span class="text-sm text-zinc-500">/10</span></span>
                        </div>
                        <div class="h-2 bg-zinc-800 rounded-full overflow-hidden">
                            <div class="h-full ${
                                item.ux_score >= 8 ? 'bg-green-500' : 
                                item.ux_score >= 6 ? 'bg-yellow-500' : 'bg-red-500'
                            }" style="width: ${(item.ux_score || 0) * 10}%"></div>
                        </div>
                    </div>
                    
                    <!-- Key Metrics -->
                    <div class="grid grid-cols-2 gap-2 mb-4 p-3 bg-zinc-800/50 rounded">
                        <div>
                            <div class="text-xs text-zinc-500">Complexity</div>
                            <div class="text-white font-semibold">${item.complexity_score || '-'}/10</div>
                        </div>
                        <div>
                            <div class="text-xs text-zinc-500">Screens</div>
                            <div class="text-white font-semibold">${item.screens_discovered || '-'}</div>
                        </div>
                        <div>
                            <div class="text-xs text-zinc-500">Avg Depth</div>
                            <div class="text-white font-semibold">${item.navigation_depth || '-'}</div>
                        </div>
                        <div>
                            <div class="text-xs text-zinc-500">Max Depth</div>
                            <div class="text-white font-semibold">${item.max_depth || '-'}</div>
                        </div>
                    </div>
                    
                    <!-- What Went Good -->
                    ${positives.length > 0 ? `
                    <div class="mb-4">
                        <h5 class="text-green-400 font-semibold text-sm mb-2 flex items-center">
                            <span class="mr-1">✓</span> What Went Good (${positives.length})
                        </h5>
                        <div class="space-y-2 max-h-40 overflow-y-auto">
                            ${positives.slice(0, 3).map(pos => `
                                <div class="p-2 bg-green-900/10 border border-green-700/30 rounded text-xs">
                                    <div class="text-green-300 font-medium">${pos.aspect || 'Positive aspect'}</div>
                                    <div class="text-zinc-400 mt-1">${pos.description || ''}</div>
                                </div>
                            `).join('')}
                            ${positives.length > 3 ? `
                                <div class="text-xs text-zinc-500 text-center">+${positives.length - 3} more</div>
                            ` : ''}
                        </div>
                    </div>
                    ` : ''}
                    
                    <!-- What's Bad (Issues) -->
                    ${issues.length > 0 ? `
                    <div class="mb-4">
                        <h5 class="text-red-400 font-semibold text-sm mb-2 flex items-center">
                            <span class="mr-1">✗</span> Issues Found (${issues.length})
                        </h5>
                        <div class="space-y-1 mb-2">
                            ${highIssues.length > 0 ? `
                                <div class="flex items-center text-xs">
                                    <span class="w-2 h-2 bg-red-500 rounded-full mr-2"></span>
                                    <span class="text-red-400">High: ${highIssues.length}</span>
                                </div>
                            ` : ''}
                            ${mediumIssues.length > 0 ? `
                                <div class="flex items-center text-xs">
                                    <span class="w-2 h-2 bg-yellow-500 rounded-full mr-2"></span>
                                    <span class="text-yellow-400">Medium: ${mediumIssues.length}</span>
                                </div>
                            ` : ''}
                            ${lowIssues.length > 0 ? `
                                <div class="flex items-center text-xs">
                                    <span class="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                                    <span class="text-green-400">Low: ${lowIssues.length}</span>
                                </div>
                            ` : ''}
                        </div>
                        <div class="space-y-2 max-h-40 overflow-y-auto">
                            ${issues.slice(0, 3).map(issue => `
                                <div class="p-2 bg-red-900/10 border border-red-700/30 rounded text-xs">
                                    <div class="flex items-start justify-between mb-1">
                                        <span class="text-red-300 font-medium">${issue.category || 'Issue'}</span>
                                        <span class="badge badge-${issue.severity === 'High' ? 'high' : issue.severity === 'Medium' ? 'medium' : 'low'} text-xs px-1 py-0">
                                            ${issue.severity}
                                        </span>
                                    </div>
                                    <div class="text-zinc-400">${issue.description || ''}</div>
                                </div>
                            `).join('')}
                            ${issues.length > 3 ? `
                                <div class="text-xs text-zinc-500 text-center">+${issues.length - 3} more</div>
                            ` : ''}
                        </div>
                    </div>
                    ` : ''}
                    
                    <!-- Distinct Features -->
                    ${distinctFeatures.length > 0 ? `
                    <div class="mb-2">
                        <h5 class="text-blue-400 font-semibold text-sm mb-2">Unique Features</h5>
                        <div class="flex flex-wrap gap-1">
                            ${distinctFeatures.map(feature => `
                                <span class="px-2 py-0.5 bg-blue-900/30 text-blue-400 rounded text-xs border border-blue-700/50">
                                    ${feature}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                    ` : ''}
                    
                    <!-- Error Handling Rating -->
                    <div class="mt-3 pt-3 border-t border-zinc-700">
                        <div class="flex items-center justify-between text-xs">
                            <span class="text-zinc-500">Error Handling</span>
                            <span class="px-2 py-1 rounded ${
                                item.error_handling_rating === 'good' ? 'bg-green-900/30 text-green-400' :
                                item.error_handling_rating === 'fair' ? 'bg-yellow-900/30 text-yellow-400' :
                                'bg-zinc-700 text-zinc-400'
                            }">${item.error_handling_rating || 'unknown'}</span>
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        
        // Add summary statistics
        const avgScore = items.reduce((sum, item) => sum + (item.ux_score || 0), 0) / items.length;
        const totalIssues = items.reduce((sum, item) => sum + (item.issues || []).length, 0);
        const totalPositives = items.reduce((sum, item) => sum + (item.positives || []).length, 0);
        
        html += `
            <div class="bg-zinc-900 border border-zinc-700 rounded-lg p-6">
                <h3 class="text-lg font-semibold text-white mb-4">Overall Summary</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div class="text-center p-4 bg-zinc-800/50 rounded">
                        <div class="text-2xl font-bold text-white">${avgScore.toFixed(1)}</div>
                        <div class="text-sm text-zinc-400">Avg UX Score</div>
                    </div>
                    <div class="text-center p-4 bg-zinc-800/50 rounded">
                        <div class="text-2xl font-bold text-red-400">${totalIssues}</div>
                        <div class="text-sm text-zinc-400">Total Issues</div>
                    </div>
                    <div class="text-center p-4 bg-zinc-800/50 rounded">
                        <div class="text-2xl font-bold text-green-400">${totalPositives}</div>
                        <div class="text-sm text-zinc-400">Total Positives</div>
                    </div>
                    <div class="text-center p-4 bg-zinc-800/50 rounded">
                        <div class="text-2xl font-bold text-blue-400">${summary.common_features ? summary.common_features.length : 0}</div>
                        <div class="text-sm text-zinc-400">Common Features</div>
                    </div>
                </div>
            </div>
        `;
        
        document.getElementById('comparisonContent').innerHTML = html;
        
        // Render comparison chart
        if (charts.comparison) charts.comparison.destroy();
        charts.comparison = new Chart(document.getElementById('comparisonChart'), {
            type: 'bar',
            data: {
                labels: items.map(i => i.app_name),
                datasets: [{
                    label: 'UX Score',
                    data: items.map(i => i.ux_score || 0),
                    backgroundColor: items.map(i => 
                        i.ux_score >= 8 ? 'rgba(74, 222, 128, 0.8)' : 
                        i.ux_score >= 6 ? 'rgba(250, 204, 21, 0.8)' : 
                        'rgba(248, 113, 113, 0.8)'
                    ),
                    borderColor: items.map(i => 
                        i.ux_score >= 8 ? 'rgb(34, 197, 94)' : 
                        i.ux_score >= 6 ? 'rgb(234, 179, 8)' : 
                        'rgb(239, 68, 68)'
                    ),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    title: { 
                        display: false
                    },
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.9)',
                        titleColor: '#fff',
                        bodyColor: '#a1a1aa',
                        padding: 12,
                        displayColors: false
                    }
                },
                scales: {
                    y: { 
                        beginAtZero: true, 
                        max: 10, 
                        ticks: { color: '#71717a', font: { size: 12 } }, 
                        grid: { color: '#27272a' },
                        title: {
                            display: true,
                            text: 'UX Score',
                            color: '#a1a1aa'
                        }
                    },
                    x: { 
                        ticks: { color: '#a1a1aa', font: { size: 12 } }, 
                        grid: { color: '#27272a' }
                    }
                }
            }
        });
        
    } catch (error) {
        console.error('Error loading comparison:', error);
        document.getElementById('comparisonContent').innerHTML = '<p class="text-red-500 text-center py-12">Error loading comparison data</p>';
    }
}

// Settings
function openSettings() {
    document.getElementById('settingsModal').classList.remove('hidden');
}

function closeSettings() {
    document.getElementById('settingsModal').classList.add('hidden');
}

async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.api_key) document.getElementById('settingsApiKey').value = data.api_key;
        if (data.llm_model) document.getElementById('settingsModel').value = data.llm_model;
        if (data.api_base) document.getElementById('settingsApiBase').value = data.api_base;
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

async function saveSettings() {
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: document.getElementById('settingsApiKey').value,
                llm_model: document.getElementById('settingsModel').value,
                api_base: document.getElementById('settingsApiBase').value
            })
        });
        
        const data = await response.json();
        if (data.success) {
            closeSettings();
            appendLog('Settings saved', 'success');
        } else {
            alert('Error saving settings');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
    }
}
