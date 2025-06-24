#!/usr/bin/env python3
"""
Distributed Traffic Simulation - Master and Worker Nodes (FINAL FIXES)

This script implements a simplified distributed traffic simulation.
- A Master node orchestrates the simulation, receives updates from workers, and aggregates results.
- Worker nodes simulate traffic within their assigned "zones" and send updates to the master.

FIXES:
1. Fixed live dashboard updates by improving SSE implementation (Chart.js and metrics)
2. Ensured traffic on all 4 zones by robust canvas creation and data processing.
3. Added proper startup script and zone management.
4. **NEW**: Tuned parameters for more visible traffic (faster cars, more cars, faster lights).
5. **NEW**: Added targeted JavaScript console logs to debug traffic visualization and chart updates.
"""

import argparse
import time
import threading
import json
import random
import os
import sys
import statistics
from datetime import datetime
import collections
import queue

# For finding a unique port for each worker's Flask app
import socket

try:
    from flask import Flask, request, jsonify, render_template_string, Response
    import requests
except ImportError:
    print("Error: Flask and/or requests library not found.")
    print("Please install them using: pip install Flask requests")
    sys.exit(1)

# Import the network latency simulator if available
try:
    from simulate_network_latency import NetworkSimulator
    net_sim = NetworkSimulator(latency_ms=15.0, jitter_ms=8.0, packet_loss=0.01)
    print("Network latency simulation enabled.")
except ImportError:
    print("Warning: simulate_network_latency.py not found. Network simulation will be disabled.")
    class DummyNetworkSimulator:
        def __init__(self, *args, **kwargs): pass
        def simulate_delay(self): pass
        def network_call(self, func): return func
    net_sim = DummyNetworkSimulator()


# =============================================================================
# Global Configuration and Data Structures
# =============================================================================
app = Flask(__name__)

# Master Node Data
registered_workers = {} # {zone: {'url': 'http://host:port', 'last_seen': timestamp, 'car_count': 0, 'current_zone_data': {}}}
total_cars_in_sim = 0
simulation_step = 0
simulation_active = True
simulation_start_time = 0
step_start_time = 0
step_times = []

# Data structures for real-time graphing (for aggregate total cars)
graph_data_history = collections.deque(maxlen=100) # Keep last 100 data points
graph_data_lock = threading.Lock() # To protect access to graph_data_history

# Global state for the entire simulation grid data for live visualization
full_simulation_grid_data = {} # {zone_name: {'vehicles': [], 'traffic_light': {}}}
full_simulation_grid_data_lock = threading.Lock() # To protect concurrent access

# Worker Node Data
worker_zone = None
master_host = None
master_port = 5000
worker_id = f"worker_{os.getpid()}"

# Worker-specific simulation parameters and vehicle/traffic light models
ZONE_SIZE = 200 # Pixels for a square zone in the visualization
ROAD_WIDTH = 20 # Pixels
CAR_SIZE = 5 # Pixels (square car)
CAR_SPEED = 7 # Increased car speed for faster movement (WAS 5)
MAX_CARS_PER_ZONE = 80 # Increased maximum cars per zone (WAS 40)

class Vehicle:
    def __init__(self, x, y, direction, zone_bounds, id):
        self.x = x
        self.y = y
        self.direction = direction # 'N', 'S', 'E', 'W'
        self.zone_bounds = zone_bounds # (min_x, min_y, max_x, max_y)
        self.id = id

    def move(self):
        min_x, min_y, max_x, max_y = self.zone_bounds
        if self.direction == 'E':
            self.x += CAR_SPEED
            if self.x > max_x + CAR_SIZE: self.x = min_x - CAR_SIZE # Wrap around, slightly off-screen to disappear
        elif self.direction == 'W':
            self.x -= CAR_SPEED
            if self.x < min_x - CAR_SIZE: self.x = max_x + CAR_SIZE # Wrap around
        elif self.direction == 'S':
            self.y += CAR_SPEED
            if self.y > max_y + CAR_SIZE: self.y = min_y - CAR_SIZE # Wrap around
        elif self.direction == 'N':
            self.y -= CAR_SPEED
            if self.y < min_y - CAR_SIZE: self.y = max_y + CAR_SIZE # Wrap around

    def get_state(self):
        return {'id': self.id, 'x': self.x, 'y': self.y, 'direction': self.direction}

class TrafficLight:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.state = 'red' # 'red', 'green'
        self.last_change_time = time.time()
        self.cycle_time = 2 # Slightly faster traffic light cycle (e.g., 2 seconds per state, WAS 3)

    def update(self):
        if time.time() - self.last_change_time > self.cycle_time:
            self.state = 'green' if self.state == 'red' else 'red'
            self.last_change_time = time.time()

    def get_state(self):
        return {'x': self.x, 'y': self.y, 'state': self.state}

# =============================================================================
# Master Node Logic
# =============================================================================

@app.route('/')
def index():
    """Master UI with live canvas visualization."""
    status_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Traffic Simulation Master Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #f0f4f8; margin: 0; padding: 0; display: flex; flex-direction: column; min-height: 100vh;}
            .header { background-color: #1e3a8a; color: white; padding: 1rem; text-align: center; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
            .container { max-width: 1200px; margin: 20px auto; padding: 30px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1); flex-grow: 1; display: flex; flex-direction: column;}
            h1 { color: #ffffff; font-size: 2.5rem; }
            h2 { color: #3b82f6; border-bottom: 2px solid #eff6ff; padding-bottom: 10px; margin-bottom: 20px; font-size: 1.8rem; }
            .status-item { background-color: #f9fafb; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; }
            .status-label { font-weight: 600; color: #4b5563; }
            .status-value { color: #1f2937; font-weight: 700; font-size: 1.1rem; }
            .worker-list { list-style: none; padding: 0; }
            .worker-item { background-color: #ecfdf5; padding: 12px 15px; border-radius: 6px; margin-bottom: 8px; border-left: 5px solid #10b981; }
            /* Styles for the chart container */
            .chart-container { position: relative; height: 300px; width: 100%; margin-top: 30px; }
            /* NEW: Styles for the simulation canvas */
            .simulation-container { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; margin-top: 30px; }
            .zone-canvas-wrapper { border: 2px solid #cbd5e1; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
            canvas { background-color: #f0fdf4; display: block; border-radius: 6px; } /* Light green background for roads */
            .footer { text-align: center; padding: 1rem; color: #64748b; font-size: 0.9rem; margin-top: auto; }
            .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
            .status-active { background-color: #22c55e; }
            .status-inactive { background-color: #ef4444; }

            @media (max-width: 768px) {
                .grid-cols-2 { grid-template-columns: 1fr; }
                .container { margin: 10px auto; padding: 15px; }
                h1 { font-size: 2rem; }
                h2 { font-size: 1.5rem; }
                .simulation-container { flex-direction: column; align-items: center; }
                canvas { width: 100%; height: auto; } /* Ensure canvas scales */
            }
        </style>
        <!-- Chart.js CDN -->
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body class="p-4">
        <div class="header">
            <h1 class="font-bold">🚀 Distributed Traffic Simulation Master</h1>
            <p class="text-white opacity-90">Real-time Dashboard</p>
        </div>
        
        <div class="container">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div class="status-item">
                    <p><span class="status-label">Simulation Status:</span> 
                    <span id="simStatus" class="status-value">
                        <span class="status-indicator"></span> <!-- Indicator will be added by JS -->
                        <span id="simStatusText"></span> <!-- Text part for status -->
                    </span></p>
                </div>
                <div class="status-item">
                    <p><span class="status-label">Current Step:</span> <span id="currentStep" class="status-value"></span></p>
                </div>
                <div class="status-item">
                    <p><span class="status-label">Total Cars:</span> <span id="totalCars" class="status-value"></span></p>
                </div>
                <div class="status-item">
                    <p><span class="status-label">Registered Workers:</span> <span id="numWorkers" class="status-value"></span></p>
                </div>
            </div>

            <h2 class="text-2xl font-semibold mt-8 mb-4">Aggregate Total Cars Over Time:</h2>
            <div class="chart-container">
                <canvas id="totalCarsChart"></canvas>
            </div>

            <h2 class="text-2xl font-semibold mt-8 mb-4">Live Traffic Simulation:</h2>
            <!-- Container for the zone canvases -->
            <div class="simulation-container" id="simulation-canvases">
                <p id="loadingMessage" class="text-gray-600">Waiting for worker data to start visualization...</p>
            </div>

            <h2 class="text-2xl font-semibold mt-8 mb-4">Connected Workers (Details):</h2>
            <div id="workersList" class="worker-list">
                <!-- Worker details will be dynamically added here by JavaScript -->
            </div>
        </div>
        <div class="footer">
            <p id="lastUpdated"></p>
            <p>&copy; 2025 Traffic Simulation Project</p>
        </div>

        <!-- JavaScript for Chart.js, SSE, and Live Simulation Canvas -->
        <script>
            // --- General Dashboard Update Function ---
            function updateDashboardMetrics(data) {
                const statusTextSpan = document.getElementById('simStatusText');
                const indicatorSpan = document.getElementById('simStatus').querySelector('.status-indicator');

                statusTextSpan.textContent = data.status;
                if (indicatorSpan) {
                    indicatorSpan.className = `status-indicator ${data.status === 'Active' ? 'status-active' : 'status-inactive'}`;
                }

                document.getElementById('currentStep').textContent = data.step;
                document.getElementById('totalCars').textContent = data.total_cars;
                document.getElementById('numWorkers').textContent = `${data.num_workers}/4`;
                document.getElementById('lastUpdated').textContent = `Last updated: ${new Date().toLocaleString()}`;
            }

            function updateWorkersList(workers_data) {
                const workersListDiv = document.getElementById('workersList');
                workersListDiv.innerHTML = ''; // Clear previous list
                if (Object.keys(workers_data).length === 0) {
                    workersListDiv.innerHTML = '<p class="text-gray-600 pl-4">No workers currently registered.</p>';
                } else {
                    let html = '';
                    for (const zoneName in workers_data) {
                        const worker = workers_data[zoneName];
                        html += `
                            <div class="worker-item">
                                <span class="font-bold">${zoneName} Zone:</span> 
                                URL: ${worker.url}, 
                                Last Seen: ${new Date(worker.last_seen * 1000).toLocaleTimeString()}, 
                                Cars: ${worker.car_count}
                            </div>
                        `;
                    }
                    workersListDiv.innerHTML = html;
                }
            }


            // --- Aggregate Chart Logic ---
            const ctx = document.getElementById('totalCarsChart').getContext('2d');
            let totalCarsChart = null; // Initialize to null to indicate no chart is present yet

            function createOrUpdateChart(labels, data) {
                if (!totalCarsChart) {
                    // Create the chart instance only once
                    totalCarsChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [{
                                label: 'Total Cars in Simulation',
                                data: data,
                                borderColor: 'rgb(75, 192, 192)',
                                tension: 0.1,
                                fill: false
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: {
                                duration: 0 // Disable animation for faster real-time updates
                            },
                            scales: {
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Simulation Step'
                                    }
                                },
                                y: {
                                    beginAtZero: true,
                                    title: {
                                        display: true,
                                        text: 'Number of Cars'
                                    }
                                }
                            }
                        }
                    });
                } else {
                    // If chart already exists, update its data and refresh
                    totalCarsChart.data.labels = labels;
                    totalCarsChart.data.datasets[0].data = data;
                    totalCarsChart.update();
                }
            }

            // This function now just pushes new data to an existing chart
            function addDataToChart(newLabel, newData) {
                if (totalCarsChart) { // Only add data if chart exists
                    totalCarsChart.data.labels.push(newLabel);
                    totalCarsChart.data.datasets[0].data.push(newData);
                    
                    const maxPoints = 100;
                    if (totalCarsChart.data.labels.length > maxPoints) {
                        totalCarsChart.data.labels.shift();
                        totalCarsChart.data.datasets[0].data.shift();
                    }
                    totalCarsChart.update();
                    console.log(`Chart updated: Step ${newLabel}, Cars: ${newData}`); // NEW: Log chart updates
                } else {
                    console.warn("Chart not initialized when addDataToChart was called.");
                }
            }

            // --- Live Simulation Canvas Logic ---
            const ZONE_SIZE = 200; // Must match Python constant for consistent rendering
            const ROAD_WIDTH = 20;
            const CAR_SIZE = 5;
            const trafficLightRadius = 5;

            const canvasMap = {}; // {zone_name: canvas_context}
            let loadingMessageRemoved = false; // Flag to ensure message is removed only once

            function getOrCreateCanvas(zoneName) {
                let canvasWrapper = document.getElementById(`zone-${zoneName}-wrapper`);
                if (!canvasWrapper) {
                    const container = document.getElementById('simulation-canvases');
                    if (!loadingMessageRemoved) {
                        const loadingMessage = document.getElementById('loadingMessage');
                        if (loadingMessage) {
                            loadingMessage.remove(); // Remove the "Waiting for worker data..." message
                            loadingMessageRemoved = true;
                            // Also clear any previous canvases if they somehow persisted
                            container.innerHTML = ''; 
                        }
                    }
                    
                    canvasWrapper = document.createElement('div');
                    canvasWrapper.id = `zone-${zoneName}-wrapper`;
                    canvasWrapper.className = 'zone-canvas-wrapper';
                    
                    const zoneLabel = document.createElement('div');
                    zoneLabel.className = 'text-center text-lg font-semibold py-2 bg-gray-100 border-b border-gray-200';
                    zoneLabel.textContent = `${zoneName} Zone`;
                    
                    const canvas = document.createElement('canvas');
                    canvas.id = `canvas-${zoneName}`;
                    canvas.width = ZONE_SIZE;
                    canvas.height = ZONE_SIZE;
                    
                    canvasWrapper.appendChild(zoneLabel);
                    canvasWrapper.appendChild(canvas);
                    container.appendChild(canvasWrapper);

                    canvasMap[zoneName] = canvas.getContext('2d');
                    console.log(`Created canvas for zone: ${zoneName}`); // NEW: Log canvas creation
                }
                return canvasMap[zoneName];
            }

            function drawZone(ctx, vehicles, trafficLight) {
                ctx.clearRect(0, 0, ZONE_SIZE, ZONE_SIZE); // Clear previous frame

                // Draw roads (a simple crossroad)
                ctx.fillStyle = '#6b7280'; // Dark grey for roads
                ctx.fillRect(0, ZONE_SIZE / 2 - ROAD_WIDTH / 2, ZONE_SIZE, ROAD_WIDTH); // Horizontal road
                ctx.fillRect(ZONE_SIZE / 2 - ROAD_WIDTH / 2, 0, ROAD_WIDTH, ZONE_SIZE); // Vertical road

                // Draw vehicles
                ctx.fillStyle = '#ef4444'; // Red cars
                if (vehicles && vehicles.length > 0) {
                    vehicles.forEach(car => {
                        ctx.fillRect(car.x, car.y, CAR_SIZE, CAR_SIZE);
                        // Optional: Direction indicator for debugging/visual
                        ctx.fillStyle = 'white';
                        if (car.direction === 'E') ctx.fillRect(car.x + CAR_SIZE - 2, car.y + CAR_SIZE / 2 - 1, 2, 2);
                        else if (car.direction === 'W') ctx.fillRect(car.x, car.y + CAR_SIZE / 2 - 1, 2, 2);
                        else if (car.direction === 'S') ctx.fillRect(car.x + CAR_SIZE / 2 - 1, car.y + CAR_SIZE - 2, 2, 2);
                        else if (car.direction === 'N') ctx.fillRect(car.x + CAR_SIZE / 2 - 1, car.y, 2, 2);
                    });
                    // console.log(`Drew ${vehicles.length} cars for zone: ${ctx.canvas.id.replace('canvas-', '')}`); // NEW: Log car drawing
                } else {
                    // console.log(`No vehicles to draw for zone: ${ctx.canvas.id.replace('canvas-', '')}`); // NEW: Log if no cars
                }


                // Draw traffic light
                if (trafficLight) {
                    ctx.beginPath();
                    ctx.arc(trafficLight.x, trafficLight.y, trafficLightRadius, 0, Math.PI * 2);
                    ctx.fillStyle = trafficLight.state === 'red' ? '#dc2626' : '#16a34a'; // Red or Green
                    ctx.fill();
                    ctx.strokeStyle = '#1f2937';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }
            }


            // --- Server-Sent Events (SSE) Listener ---
            let eventSource;
            let reconnectAttempts = 0;
            const maxReconnectAttempts = 5;

            function connectSSE() {
                // Ensure any old connection is properly closed before creating a new one
                if (eventSource && eventSource.readyState !== EventSource.CLOSED) {
                    eventSource.close();
                    console.log("Closed existing SSE connection before reconnecting.");
                }

                eventSource = new EventSource('/stream_data');

                eventSource.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        console.log("Received SSE update (data.type:", data.type, "):", data); // IMPORTANT: Keep this log for debugging

                        // Update main dashboard metrics with every update
                        updateDashboardMetrics({
                            status: data.status,
                            step: data.step,
                            total_cars: data.total_cars,
                            num_workers: data.num_workers
                        });
                        updateWorkersList(data.registered_workers);

                        // Handle chart: on initial_data (or reconnect), re-initialize/reset with full history.
                        // On 'update', just add the latest data point.
                        if (data.type === 'initial_data') {
                            if (data.history && data.history.length > 0) {
                                createOrUpdateChart(data.history.map(item => item[0]), data.history.map(item => item[1]));
                            } else {
                                // If initial_data has no history, ensure chart is cleared or initialized empty
                                createOrUpdateChart([], []);
                            }
                        } else if (data.type === 'update') {
                            if (totalCarsChart) { // Only update if chart exists
                                addDataToChart(data.step, data.total_cars);
                            } else { // Fallback if chart somehow wasn't initialized on initial_data
                                createOrUpdateChart([data.step], [data.total_cars]);
                            }
                        }

                        // Update live simulation visualization for each zone
                        // console.log("Processing zone data:", data.zone_data); // Keep this log for debugging
                        if (data.zone_data) {
                            for (const zoneName in data.zone_data) {
                                const ctx = getOrCreateCanvas(zoneName);
                                drawZone(ctx, data.zone_data[zoneName].vehicles, data.zone_data[zoneName].traffic_light);
                            }
                        } else {
                            console.warn("No zone_data received in SSE update.");
                        }

                    } catch (error) {
                        console.error('Error parsing or processing SSE data:', error);
                    }
                };

                eventSource.onerror = function(error) {
                    console.error('SSE error:', error); // IMPORTANT: Keep this log for debugging
                    eventSource.close(); // Explicitly close the faulty connection
                    
                    if (reconnectAttempts < maxReconnectAttempts) {
                        reconnectAttempts++;
                        console.log(`Attempting to reconnect SSE in 3 seconds (${reconnectAttempts}/${maxReconnectAttempts})...`);
                        setTimeout(connectSSE, 3000); // Try to reconnect after 3 seconds
                    } else {
                        console.error('Max SSE reconnection attempts reached. Please check server logs or network.');
                        // Optionally display a user-facing message here
                    }
                };

                eventSource.onopen = function() {
                    console.log("SSE connection opened successfully.");
                    reconnectAttempts = 0; // Reset attempts on successful open
                };
            }

            // Initial SSE connection attempt when the script loads
            document.addEventListener('DOMContentLoaded', connectSSE);

            window.addEventListener('resize', () => {
                // For Chart.js, responsive: true usually handles resizing.
                // If you had a single large canvas that should scale dynamically,
                // you'd add its resize logic here.
            });

            // Added cleanup on page unload
            window.addEventListener('beforeunload', function() {
                if (eventSource) {
                    eventSource.close();
                }
            });

        </script>
    </body>
    </html>
    """
    # The Python side's index() route no longer needs to pass initial values,
    # as the JavaScript handles all dynamic rendering via SSE.
    return render_template_string(status_html,
        status="Inactive", # Initial status, will be overwritten by JS
        status_class="status-inactive", # Initial class
        current_step=0, # Initial values, overwritten by JS
        total_cars=0,
        num_workers=0,
        workers_html='<p class="text-gray-600 pl-4">No workers currently registered.</p>', # Initial HTML
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


# SSE Endpoint for streaming data to the browser
@app.route('/stream_data')
def stream_data():
    def generate_data():
        last_step_sent = -1
        while True:
            # Acquire locks for consistent data access
            with graph_data_lock, full_simulation_grid_data_lock:
                current_total_cars = sum(data['car_count'] for data in registered_workers.values())
                current_simulation_step = simulation_step
                current_status = "Active" if simulation_active else "Inactive"
                current_num_workers = len(registered_workers)
                
                # Create a copy of the registered_workers details for JSON serialization
                current_registered_workers_details = {zone: {
                    'url': data['url'],
                    'last_seen': data['last_seen'],
                    'car_count': data['car_count'],
                    'id': data['id']
                } for zone, data in registered_workers.items()}

            # Only send if the global simulation step has advanced since last sent
            # or if it's the very first time sending (step 0 or initial_data)
            if current_simulation_step > last_step_sent or (current_simulation_step == 0 and last_step_sent == -1):
                latest_total_cars_data = graph_data_history[-1] if graph_data_history else (0,0)
                
                payload = {
                    'type': 'update', # Default to update
                    'status': current_status,
                    'step': current_simulation_step,
                    'total_cars': current_total_cars,
                    'num_workers': current_num_workers,
                    'history': list(graph_data_history), # Always send full history for potential client reconnects
                    'zone_data': dict(full_simulation_grid_data), # Send current state of all zones
                    'registered_workers': current_registered_workers_details
                }
                
                if last_step_sent == -1: # This is the first data payload sent over this specific SSE connection
                    payload['type'] = 'initial_data'
                    
                yield f"data: {json.dumps(payload)}\n\n"
                last_step_sent = current_simulation_step
            time.sleep(0.5) # Send updates twice per second for smoother animation

    return Response(generate_data(), mimetype='text/event-stream', 
                    headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'})


@app.route('/register_worker', methods=['POST'])
def register_worker():
    """Endpoint for workers to register with the master."""
    data = request.json
    zone = data.get('zone')
    worker_url = data.get('worker_url')
    worker_id = data.get('worker_id')

    if not zone or not worker_url or not worker_id:
        return jsonify({"error": "Missing zone, worker_url, or worker_id"}), 400

    registered_workers[zone] = {
        'url': worker_url,
        'last_seen': time.time(),
        'car_count': 0,
        'id': worker_id,
        'current_zone_data': {'vehicles': [], 'traffic_light': None} # Initialize detailed zone data
    }
    print(f"Master: Registered worker {worker_id} for zone {zone} at {worker_url}")
    return jsonify({"message": f"Worker {worker_id} registered successfully"})

@app.route('/traffic_update', methods=['POST'])
def traffic_update():
    """Endpoint for workers to send traffic updates to the master."""
    global total_cars_in_sim
    data = request.json
    zone = data.get('zone')
    car_count = data.get('car_count', 0)
    worker_id_from_update = data.get('worker_id')
    
    zone_vehicles = data.get('vehicles', [])
    zone_traffic_light = data.get('traffic_light')

    if not zone or 'car_count' not in data or not worker_id_from_update:
        return jsonify({"error": "Missing zone, car_count, or worker_id"}), 400

    if zone in registered_workers and registered_workers[zone]['id'] == worker_id_from_update:
        old_car_count = registered_workers[zone]['car_count']
        registered_workers[zone]['car_count'] = car_count
        registered_workers[zone]['last_seen'] = time.time()
        
        registered_workers[zone]['current_zone_data'] = {
            'vehicles': zone_vehicles,
            'traffic_light': zone_traffic_light
        }

        # Ensure total_cars_in_sim is updated accurately
        # It's safer to re-sum all worker car counts than to do a delta if updates can be missed/out of order
        # For simplicity, we stick to delta as it's typically faster, but acknowledge its limitations.
        total_cars_in_sim += (car_count - old_car_count) 

        # Update simulation grid data with proper locking
        with full_simulation_grid_data_lock:
            full_simulation_grid_data[zone] = {
                'vehicles': zone_vehicles,
                'traffic_light': zone_traffic_light
            }

        return jsonify({"message": "Update received"})
    else:
        print(f"Master: Received update from unknown/mismatched worker {worker_id_from_update} for zone {zone}")
        return jsonify({"error": "Worker not registered or ID mismatch"}), 404

def master_simulation_loop(duration=None, test_mode=False):
    """Main simulation loop for the master node."""
    global simulation_step, total_cars_in_sim, simulation_active, simulation_start_time, step_start_time, step_times

    print("Master: Starting simulation loop...")
    simulation_start_time = time.time()
    end_time = simulation_start_time + duration if duration else float('inf')

    # Better worker waiting logic
    print("Master: Waiting for workers to register...")
    expected_zones = ['North', 'South', 'East', 'West']
    initial_wait_timeout = 30 # Give workers up to 30 seconds to register
    start_wait_time = time.time()
    
    while len(registered_workers) < len(expected_zones):
        if time.time() - start_wait_time > initial_wait_timeout:
            print(f"Master: Timeout waiting for all workers. Got {len(registered_workers)}/{len(expected_zones)}. Starting with available workers.")
            break
        time.sleep(1) # Check every second for new registrations
    
    if not registered_workers:
        print("Master: No workers registered. Exiting simulation.")
        simulation_active = False
        return

    print(f"Master: Starting simulation with {len(registered_workers)} workers: {list(registered_workers.keys())}")

    while simulation_active and time.time() < end_time:
        simulation_step += 1
        step_start_time = time.time()
        # print(f"\nMaster: Simulation Step {simulation_step}") # Commented out for less console spam

        # Send step commands to all workers
        for zone, worker_info in list(registered_workers.items()):
            worker_url = worker_info['url']
            try:
                response = requests.post(
                    f"{worker_url}/simulate_step",
                    json={"step": simulation_step, "master_id": "master_123"},
                    timeout=3 # Short timeout for worker response
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Master: Error communicating with worker {zone} at {worker_url}: {e}")
                # Consider logic to mark worker as down or remove it
                
        # Calculate total cars and update graph data
        current_total_cars = sum(data['car_count'] for data in registered_workers.values())
        
        with graph_data_lock:
            graph_data_history.append((simulation_step, current_total_cars))

        step_end_time = time.time()
        step_duration = step_end_time - step_start_time
        step_times.append(step_duration)

        # print(f"Master: Step {simulation_step} completed. Total cars: {current_total_cars}") # Commented out for less console spam
        time.sleep(0.5) # Master orchestrates steps every 0.5 seconds

    simulation_active = False
    print("Master: Simulation loop finished.")

    if test_mode and step_times:
        avg_step_time = statistics.mean(step_times)
        print(f"Performance Metrics: avg_step_time: {avg_step_time:.4f}")
    elif test_mode:
        print("Performance Metrics: No step times recorded for test mode.")

# =============================================================================
# Worker Node Logic
# =============================================================================
worker_vehicles = []
worker_traffic_light = None
current_zone_bounds = (0, 0, ZONE_SIZE, ZONE_SIZE) # Fixed bounds for worker visualization

@app.route('/simulate_step', methods=['POST'])
def worker_simulate_step():
    """Endpoint for the master to tell a worker to perform a simulation step."""
    global simulation_step, worker_vehicles, worker_traffic_light
    
    data = request.json
    master_step = data.get('step')
    
    simulation_step = master_step

    # Update traffic light
    if worker_traffic_light:
        worker_traffic_light.update()

    # Move vehicles
    for vehicle in worker_vehicles:
        vehicle.move()

    # Better vehicle management: Add vehicles with higher probability, remove occasionally
    if random.random() < 0.4 and len(worker_vehicles) < MAX_CARS_PER_ZONE:
        direction = random.choice(['E', 'W', 'N', 'S'])
        # Spawn points slightly outside the edge to make full "enter" visible
        if direction == 'E': x,y = -CAR_SIZE, ZONE_SIZE/2 - CAR_SIZE/2
        elif direction == 'W': x,y = ZONE_SIZE, ZONE_SIZE/2 - CAR_SIZE/2
        elif direction == 'S': x,y = ZONE_SIZE/2 - CAR_SIZE/2, -CAR_SIZE
        elif direction == 'N': x,y = ZONE_SIZE/2 - CAR_SIZE/2, ZONE_SIZE
        else: x,y = random.randint(0, ZONE_SIZE - CAR_SIZE), random.randint(0, ZONE_SIZE - CAR_SIZE) # Fallback random
        
        new_car_id = f"{worker_id}_car_{simulation_step}_{random.randint(0,1000)}"
        worker_vehicles.append(Vehicle(x, y, direction, current_zone_bounds, new_car_id))

    # Remove vehicles occasionally to prevent infinite growth / simulate exiting
    if random.random() < 0.02 and len(worker_vehicles) > 20: # Decreased removal probability, increased min cars (WAS 0.05, 10)
        # Only remove if there are enough cars to maintain some traffic
        worker_vehicles.pop(random.randint(0, len(worker_vehicles) - 1))

    # Get states for master
    vehicles_state = [v.get_state() for v in worker_vehicles]
    traffic_light_state = worker_traffic_light.get_state() if worker_traffic_light else None

    # Send update to master
    try:
        response = requests.post(
            f"http://{master_host}:{master_port}/traffic_update",
            json={
                "zone": worker_zone,
                "car_count": len(worker_vehicles), # Report current count of vehicles in this zone
                "worker_id": worker_id,
                "vehicles": vehicles_state,       # Include detailed vehicle states
                "traffic_light": traffic_light_state # Include traffic light state
            },
            timeout=5
        )
        response.raise_for_status()
        print(f"Worker {worker_id}: Sent update to master. Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Worker {worker_id}: Error sending update to master: {e}")

    return jsonify({"status": "acknowledged", "worker_id": worker_id})

def worker_startup(zone, host, port=5000):
    """Initialize and register the worker with the master."""
    global worker_zone, master_host, master_port, worker_traffic_light, worker_vehicles
    worker_zone = zone
    master_host = host
    master_port = port
    
    # Better initial vehicle setup: more cars, distributed on roads
    initial_car_count = random.randint(20, 35) # More initial cars (WAS 15-25)
    for i in range(initial_car_count):
        direction = random.choice(['E', 'W', 'N', 'S'])
        x, y = 0, 0 # Initialize, will be set based on direction
        # Initial placement to distribute cars on roads
        if direction == 'E': x,y = random.uniform(0, ZONE_SIZE * 0.4), ZONE_SIZE/2 - CAR_SIZE/2
        elif direction == 'W': x,y = random.uniform(ZONE_SIZE * 0.6, ZONE_SIZE), ZONE_SIZE/2 - CAR_SIZE/2
        elif direction == 'S': x,y = ZONE_SIZE/2 - CAR_SIZE/2, random.uniform(0, ZONE_SIZE * 0.4)
        elif direction == 'N': x,y = ZONE_SIZE/2 - CAR_SIZE/2, random.uniform(ZONE_SIZE * 0.6, ZONE_SIZE)
        
        worker_vehicles.append(Vehicle(x, y, direction, current_zone_bounds, f"car_{zone}_{i}"))
    
    # Create traffic light for this zone
    worker_traffic_light = TrafficLight(ZONE_SIZE/2, ZONE_SIZE/2)

    # Find available port for worker's Flask server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    base_port = master_port + 100 # Workers use ports starting from master_port + 100
    worker_self_port = None
    
    for p in range(base_port, base_port + 200): # Search for an available port in a range
        try:
            s.bind(("0.0.0.0", p))
            s.close()
            worker_self_port = p
            break
        except OSError:
            continue
    
    if worker_self_port is None:
        print("Worker: Could not find available port to bind its Flask server. Exiting.")
        sys.exit(1)

    # Use localhost for worker's self URL to ensure correct registration on the same machine
    worker_self_url = f"http://localhost:{worker_self_port}"

    # Register with master
    master_url = f"http://{master_host}:{master_port}"
    retries = 10 # More retries for robustness
    
    print(f"Worker {worker_id} ({worker_zone}): Attempting to register with master at {master_url}...")
    while retries > 0:
        try:
            response = requests.post(
                f"{master_url}/register_worker",
                json={
                    "zone": worker_zone,
                    "worker_url": worker_self_url,
                    "worker_id": worker_id
                },
                timeout=5
            )
            response.raise_for_status()
            print(f"Worker {worker_id} ({worker_zone}): Registered successfully with master! My URL: {worker_self_url}")
            break
        except requests.exceptions.ConnectionError:
            print(f"Worker {worker_id}: Master not reachable at {master_url}. Retrying ({retries} left)...")
            time.sleep(2)
            retries -= 1
        except requests.exceptions.RequestException as e:
            print(f"Worker {worker_id}: Registration error: {e}")
            retries -= 1
            time.sleep(2)
    else:
        print(f"Worker {worker_id}: Failed to register with master after multiple retries. Exiting.")
        sys.exit(1)

    # Start worker's Flask server in a daemon thread
    print(f"Worker {worker_id} ({worker_zone}): Starting Flask server on {worker_self_url.split('//')[1]}")
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=worker_self_port, debug=False, use_reloader=False), daemon=True).start()

    print(f"Worker {worker_id} ({worker_zone}): Worker ready and listening on port {worker_self_port}. Waiting for master commands.")
    
    try:
        # Keep worker alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"Worker {worker_id} ({worker_zone}): Shutting down...")

# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed Traffic Simulation Master/Worker")
    parser.add_argument("--master", action="store_true", help="Run as master node")
    parser.add_argument("--worker", action="store_true", help="Run as worker node")
    parser.add_argument("--zone", type=str, help="Zone for worker node (North, South, East, West)")
    parser.add_argument("--host", type=str, default="localhost", help="Host address of the master node (for workers)")
    parser.add_argument("--port", type=int, default=5000, help="Port for the master node's API")
    parser.add_argument("--test-mode", action="store_true", help="Run master in test mode (for performance_test.py)")
    parser.add_argument("--duration", type=int, default=60, help="Duration of simulation in seconds (for master, especially in test mode)")

    args = parser.parse_args()

    if args.master and args.worker:
        parser.error("Cannot run as both master and worker.")
    elif not args.master and not args.worker:
        parser.error("Must specify either --master or --worker.")

    if args.master:
        print(f"Starting Distributed Traffic Simulation Master on port {args.port}...")
        simulation_thread = threading.Thread(target=master_simulation_loop, args=(args.duration, args.test_mode), daemon=True)
        simulation_thread.start()
        
        app.run(host='0.0.0.0', port=args.port, debug=False, use_reloader=False)

    elif args.worker:
        if not args.zone:
            parser.error("Worker mode requires --zone argument.")
        print(f"Starting Distributed Traffic Simulation Worker for zone {args.zone}...")
        worker_startup(args.zone, args.host, args.port)
