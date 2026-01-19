// Depth slider value update
document.getElementById('maxDepth').addEventListener('input', function(e) {
    document.getElementById('depthValue').textContent = e.target.value;
});

// Clear logs function
function clearLogs() {
    const terminalOutput = document.getElementById('terminalOutput');
    terminalOutput.innerHTML = '<div class="log-entry log-info"><span class="log-timestamp">[00:00:00]</span><span class="log-message">Logs cleared</span></div>';
}

// Append log to terminal
let logStartTime = null;

function appendLog(message, type = 'info') {
    if (!logStartTime) {
        logStartTime = Date.now();
    }
    
    const terminalOutput = document.getElementById('terminalOutput');
    const elapsed = Date.now() - logStartTime;
    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    const timestamp = `[${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}]`;
    
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.innerHTML = `<span class="log-timestamp">${timestamp}</span><span class="log-message">${message}</span>`;
    
    terminalOutput.appendChild(logEntry);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// Start test
async function startTest() {
    const appName = document.getElementById('appName').value.trim();
    const category = document.getElementById('category').value;
    const maxDepth = parseInt(document.getElementById('maxDepth').value);
    
    // Validation
    if (!appName) {
        alert('Please enter an application name');
        return;
    }
    
    if (!category) {
        alert('Please select a category');
        return;
    }
    
    // Reset log start time
    logStartTime = null;
    clearLogs();
    
    // Hide config, show progress
    document.getElementById('configPanel').classList.add('hidden');
    document.getElementById('progressPanel').classList.remove('hidden');
    document.getElementById('resultsPanel').classList.add('hidden');
    
    try {
        appendLog('Starting test configuration...', 'info');
        
        // Start the test
        const response = await fetch('/api/run-test', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                app_name: appName,
                category: category,
                max_depth: maxDepth
            })
        });
        
        const data = await response.json();
        console.log('Test started:', data);
        appendLog(`Test initiated for ${appName}`, 'success');
        
        // Listen for progress updates and logs
        listenForProgress();
        listenForLogs();
        
    } catch (error) {
        console.error('Error starting test:', error);
        appendLog('Error: ' + error.message, 'error');
        alert('Error starting test: ' + error.message);
        resetTest();
    }
}

// Listen for SSE log updates
function listenForLogs() {
    const logSource = new EventSource('/api/logs');
    
    logSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        // Skip keepalive messages
        if (data.keepalive) return;
        
        // Display log message
        appendLog(data.message, data.type || 'info');
    };
    
    logSource.onerror = function(error) {
        console.error('Log SSE Error:', error);
        logSource.close();
    };
    
    // Store reference for cleanup
    window.logEventSource = logSource;
}

// Listen for SSE progress updates
function listenForProgress() {
    const eventSource = new EventSource('/api/progress');
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        // Skip keepalive messages
        if (data.keepalive) return;
        
        // Update progress
        updateProgress(data.message, data.percentage);
        
        // If complete, load results
        if (data.percentage >= 100) {
            eventSource.close();
            setTimeout(loadResults, 1000);
        } else if (data.percentage < 0) {
            // Error occurred
            eventSource.close();
            alert('Test failed: ' + data.message);
            resetTest();
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE Error:', error);
        eventSource.close();
    };
}

// Update progress bar and message
function updateProgress(message, percentage) {
    const progressBar = document.getElementById('progressBar');
    const progressMessage = document.getElementById('progressMessage');
    
    progressBar.style.width = percentage + '%';
    progressMessage.textContent = message;
}

// Load and display results
async function loadResults() {
    try {
        const response = await fetch('/api/results');
        const data = await response.json();
        
        if (data.error) {
            alert('Error loading results: ' + data.error);
            resetTest();
            return;
        }
        
        // Hide progress, show results
        document.getElementById('progressPanel').classList.add('hidden');
        document.getElementById('resultsPanel').classList.remove('hidden');
        
        // Display results
        displaySummary(data.summary);
        displayMetrics(data.metrics);
        displayPositive(data.positive);
        displayIssues(data.issues);
        displaySuggestions(data.suggestions);
        
    } catch (error) {
        console.error('Error loading results:', error);
        alert('Error loading results: ' + error.message);
        resetTest();
    }
}

// Display summary
function displaySummary(summary) {
    const summaryContent = document.getElementById('summaryContent');
    summaryContent.innerHTML = marked.parse(summary || 'No summary available.');
}

// Display positive findings
function displayPositive(positive) {
    const positiveContent = document.getElementById('positiveContent');
    if (!positive || positive.length === 0) {
        positiveContent.innerHTML = '<p>No positive findings documented.</p>';
        return;
    }
    
    const html = positive.map(item => `
        <div class="issue-card low">
            <div class="issue-header">
                <strong>${item.aspect || 'Positive Finding'}</strong>
                <span class="badge low">✓ Good</span>
            </div>
            <p>${item.description}</p>
        </div>
    `).join('');
    
    positiveContent.innerHTML = html;
}

// Display metrics with charts
function displayMetrics(metrics) {
    // Depth Chart
    new Chart(document.getElementById('depthChart'), {
        type: 'bar',
        data: {
            labels: ['Total Screens', 'Max Depth', 'Avg Depth', 'Hub Screens'],
            datasets: [{
                label: 'Navigation Metrics',
                data: [
                    metrics.total_screens || 0,
                    metrics.max_depth || 0,
                    metrics.avg_depth || 0,
                    metrics.hub_screen_count || 0
                ],
                backgroundColor: [
                    'rgba(79, 70, 229, 0.7)',
                    'rgba(99, 102, 241, 0.7)',
                    'rgba(16, 185, 129, 0.7)',
                    'rgba(245, 158, 11, 0.7)'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Navigation Depth',
                    color: '#e0e0e0'
                },
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#a0a0a0' },
                    grid: { color: '#333333' }
                },
                x: {
                    ticks: { color: '#a0a0a0' },
                    grid: { color: '#333333' }
                }
            }
        }
    });
    
    // Complexity Chart (Gauge-style)
    new Chart(document.getElementById('complexityChart'), {
        type: 'doughnut',
        data: {
            labels: ['Complexity', 'Remaining'],
            datasets: [{
                data: [metrics.complexity_score || 0, 10 - (metrics.complexity_score || 0)],
                backgroundColor: [
                    metrics.complexity_score > 7 ? 'rgba(239, 68, 68, 0.7)' :
                    metrics.complexity_score > 4 ? 'rgba(245, 158, 11, 0.7)' :
                    'rgba(16, 185, 129, 0.7)',
                    'rgba(42, 42, 42, 0.3)'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                title: {
                    display: true,
                    text: `Complexity Score: ${metrics.complexity_score || 0}/10`,
                    color: '#e0e0e0'
                },
                legend: { display: false }
            }
        }
    });
}

// Display issues
function displayIssues(issues) {
    const issuesContent = document.getElementById('issuesContent');
    
    if (!issues || issues.length === 0) {
        issuesContent.innerHTML = '<p>No issues found.</p>';
        
        // Update severity chart with no data
        new Chart(document.getElementById('severityChart'), {
            type: 'pie',
            data: {
                labels: ['No Issues'],
                datasets: [{
                    data: [1],
                    backgroundColor: ['rgba(16, 185, 129, 0.7)']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Issue Severity Distribution',
                        color: '#e0e0e0'
                    }
                }
            }
        });
        return;
    }
    
    // Count severities
    const severityCounts = {
        High: 0,
        Medium: 0,
        Low: 0
    };
    
    issues.forEach(issue => {
        severityCounts[issue.severity] = (severityCounts[issue.severity] || 0) + 1;
    });
    
    // Severity Chart
    new Chart(document.getElementById('severityChart'), {
        type: 'pie',
        data: {
            labels: Object.keys(severityCounts),
            datasets: [{
                data: Object.values(severityCounts),
                backgroundColor: [
                    'rgba(239, 68, 68, 0.7)',
                    'rgba(245, 158, 11, 0.7)',
                    'rgba(16, 185, 129, 0.7)'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Issue Severity Distribution',
                    color: '#e0e0e0'
                },
                legend: {
                    labels: { color: '#e0e0e0' }
                }
            }
        }
    });
    
    // Display issues
    const html = issues.map(issue => `
        <div class="issue-card ${issue.severity.toLowerCase()}">
            <div class="issue-header">
                <strong>${issue.category}</strong>
                <span class="badge ${issue.severity.toLowerCase()}">${issue.severity}</span>
            </div>
            <p>${issue.description}</p>
        </div>
    `).join('');
    
    issuesContent.innerHTML = html;
}

// Display suggestions
function displaySuggestions(suggestions) {
    const suggestionsContent = document.getElementById('suggestionsContent');
    
    if (!suggestions || suggestions.length === 0) {
        suggestionsContent.innerHTML = '<p>No suggestions available.</p>';
        return;
    }
    
    const html = suggestions.map(suggestion => `
        <div class="suggestion-card ${suggestion.priority.toLowerCase()}">
            <div class="suggestion-header">
                <strong>${suggestion.recommendation}</strong>
                <span class="badge ${suggestion.priority.toLowerCase()}">${suggestion.priority} Priority</span>
            </div>
            <p><strong>Impact:</strong> ${suggestion.impact}</p>
        </div>
    `).join('');
    
    suggestionsContent.innerHTML = html;
}

// Download report
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

// Reset test
function resetTest() {
    // Close event sources if they exist
    if (window.logEventSource) {
        window.logEventSource.close();
        window.logEventSource = null;
    }
    
    document.getElementById('configPanel').classList.remove('hidden');
    document.getElementById('progressPanel').classList.add('hidden');
    document.getElementById('resultsPanel').classList.add('hidden');
    
    // Reset form
    document.getElementById('appName').value = '';
    document.getElementById('category').value = '';
    document.getElementById('maxDepth').value = 6;
    document.getElementById('depthValue').textContent = '6';
    
    // Reset logs
    logStartTime = null;
    clearLogs();
}
