#!/usr/bin/env python3
"""
Distributed Traffic Simulation - Master and Worker Nodes

This script implements a simplified distributed traffic simulation.
- A Master node orchestrates the simulation, receives updates from workers, and aggregates results.
- Worker nodes simulate traffic within their assigned "zones" and send updates to the master.

Communication is handled via a simple HTTP API using Flask for the master
and the `requests` library for the workers.
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
registered_workers = {}
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
full_simulation_grid_data = {}
full_simulation_grid_data_lock = threading.Lock()

# Worker Node Data
worker_zone = None
master_host = None
master_port = 5000
worker_id = f"worker_{os.getpid()}"

# Worker-specific simulation parameters and vehicle/traffic light models
ZONE_SIZE = 200 # Pixels for a square zone in the visualization
ROAD_WIDTH = 20 # Pixels
CAR_SIZE = 5 # Pixels (square car)
CAR_SPEED = 5 # NEW: Increased car speed for faster movement
MAX_CARS_PER_ZONE = 40 # NEW: Increased maximum cars per zone

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
        self.cycle_time = 3 # NEW: Slightly faster traffic light cycle (e.g., 3 seconds per state)

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
                    <p><span class="status-label">Simulation Status:</span> <span id="simStatus" class="status-value"></span></p>
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
                <p class="text-gray-600">Waiting for worker data to start visualization...</p>
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
                document.getElementById('simStatus').textContent = data.status;
                document.getElementById('currentStep').textContent = data.step;
                document.getElementById('totalCars').textContent = data.total_cars;
                document.getElementById('numWorkers').textContent = data.num_workers;
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
            let totalCarsChart;

            function initializeChart(labels, data) {
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
            }

            function updateChart(newLabel, newData) {
                if (!totalCarsChart) {
                    initializeChart([newLabel], [newData]);
                } else {
                    totalCarsChart.data.labels.push(newLabel);
                    totalCarsChart.data.datasets[0].data.push(newData);
                    
                    const maxPoints = 100;
                    if (totalCarsChart.data.labels.length > maxPoints) {
                        totalCarsChart.data.labels.shift();
                        totalCarsChart.data.datasets[0].data.shift();
                    }
                    totalCarsChart.update();
                }
            }

            // --- Live Simulation Canvas Logic ---
            const ZONE_SIZE = 200; // Must match Python constant for consistent rendering
            const ROAD_WIDTH = 20;
            const CAR_SIZE = 5;
            const trafficLightRadius = 5;

            const canvasMap = {}; // {zone_name: canvas_context}

            function getOrCreateCanvas(zoneName) {
                let canvasWrapper = document.getElementById(`zone-${zoneName}-wrapper`);
                if (!canvasWrapper) {
                    const container = document.getElementById('simulation-canvases');
                    if (container.querySelector('p')) { // Remove initial message
                        container.innerHTML = '';
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
                vehicles.forEach(car => {
                    ctx.fillRect(car.x, car.y, CAR_SIZE, CAR_SIZE);
                    // Optionally draw direction indicator
                    ctx.fillStyle = 'white';
                    // Draw a tiny white square at the front of the car based on direction
                    if (car.direction === 'E') ctx.fillRect(car.x + CAR_SIZE - 2, car.y + CAR_SIZE / 2 - 1, 2, 2);
                    else if (car.direction === 'W') ctx.fillRect(car.x, car.y + CAR_SIZE / 2 - 1, 2, 2);
                    else if (car.direction === 'S') ctx.fillRect(car.x + CAR_SIZE / 2 - 1, car.y + CAR_SIZE - 2, 2, 2);
                    else if (car.direction === 'N') ctx.fillRect(car.x + CAR_SIZE / 2 - 1, car.y, 2, 2);
                });

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
            const eventSource = new EventSource('/stream_data');

            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                // console.log("Received SSE update:", data); // IMPORTANT: Check this log in your browser console

                if (data.type === 'initial_data') {
                    // Update main dashboard metrics
                    updateDashboardMetrics({
                        status: data.status,
                        step: data.step,
                        total_cars: data.total_cars,
                        num_workers: data.num_workers
                    });
                    // Update workers list
                    updateWorkersList(data.registered_workers);

                    // Initialize aggregate chart with historical data
                    const labels = data.history.map(item => item[0]);
                    const carCounts = data.history.map(item => item[1]);
                    initializeChart(labels, carCounts);

                    // Initialize live simulation visualization with current state
                    // console.log("Initial simulation data:", data.full_sim_data); // IMPORTANT: Check this log
                    for (const zoneName in data.full_sim_data) {
                        const ctx = getOrCreateCanvas(zoneName);
                        drawZone(ctx, data.full_sim_data[zoneName].vehicles, data.full_sim_data[zoneName].traffic_light);
                    }

                } else if (data.type === 'update') {
                    // Update main dashboard metrics
                    updateDashboardMetrics({
                        status: data.status,
                        step: data.step,
                        total_cars: data.total_cars,
                        num_workers: data.num_workers
                    });
                    // Update workers list
                    updateWorkersList(data.registered_workers);

                    // Update aggregate chart
                    updateChart(data.step, data.total_cars);

                    // Update live simulation visualization for each zone
                    // console.log("Live update for zones:", data.zone_data); // IMPORTANT: Check this log
                    for (const zoneName in data.zone_data) {
                        const ctx = getOrCreateCanvas(zoneName);
                        drawZone(ctx, data.zone_data[zoneName].vehicles, data.zone_data[zoneName].traffic_light);
                    }
                }
            };

            eventSource.onerror = function(err) {
                console.error("EventSource failed:", err); // IMPORTANT: Check this log for connection errors
                // Attempt to reconnect after a delay, or show user message
                eventSource.close();
                // setTimeout(() => { eventSource = new EventSource('/stream_data'); }, 5000); // Reconnect logic
            };

            window.addEventListener('resize', () => {
                // Resize logic for Chart.js if needed (handled by responsive: true usually)
            });

        </script>
    </body>
    </html>
    """
    
    # We remove the Python-side rendering of static placeholders and worker HTML
    # as they will now be populated by JavaScript via SSE.
    # The return render_template_string now returns the template without Python-filled values.
    return render_template_string(status_html)


# SSE Endpoint for streaming data to the browser
@app.route('/stream_data')
def stream_data():
    def generate_data():
        # This function runs in a separate thread/context for SSE
        last_step_sent = -1
        while True:
            # We need to get the latest comprehensive state from the master's main simulation loop
            # This data will be sent regardless of whether it's initial data or an update
            with graph_data_lock, full_simulation_grid_data_lock:
                current_total_cars = sum(data['car_count'] for data in registered_workers.values())
                current_simulation_step = simulation_step
                current_status = "Active" if simulation_active else "Inactive"
                current_num_workers = len(registered_workers)
                
                # Get a copy of the actual registered workers dict for details
                current_registered_workers_details = {zone: {
                    'url': data['url'],
                    'last_seen': data['last_seen'],
                    'car_count': data['car_count'],
                    'id': data['id']
                } for zone, data in registered_workers.items()}

            # Only send if the global simulation step has advanced since last sent
            # or if it's the very first time sending (step 0 or initial_data)
            if current_simulation_step > last_step_sent or (current_simulation_step == 0 and last_step_sent == -1):
                # Get the most recent total cars data point for the aggregate chart
                latest_total_cars_data = graph_data_history[-1] if graph_data_history else (0,0)
                
                # Prepare the data payload
                payload = {
                    'type': 'update', # Default to update, initial_data handled below
                    'status': current_status,
                    'step': current_simulation_step,
                    'total_cars': current_total_cars,
                    'num_workers': current_num_workers,
                    'history': list(graph_data_history), # Send full history for chart initialization/reconnection
                    'zone_data': dict(full_simulation_grid_data),
                    'registered_workers': current_registered_workers_details
                }
                
                # Logic for initial data payload vs. subsequent updates
                # The client-side JS will distinguish using data.type
                if last_step_sent == -1: # First time sending data over this connection
                    payload['type'] = 'initial_data'
                    # full_sim_data is already in payload['zone_data'] for initial rendering.
                    
                yield f"data: {json.dumps(payload)}\n\n"
                last_step_sent = current_simulation_step # Mark the current global simulation step as sent
            time.sleep(0.5) # Send updates twice per second for smoother animation

    return Response(generate_data(), mimetype='text/event-stream')


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
        'car_count': 0, # Initialize car count for this worker
        'id': worker_id,
        'current_zone_data': {'vehicles': [], 'traffic_light': None}
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

        total_cars_in_sim += (car_count - old_car_count)

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
    """
    Main simulation loop for the master node.
    Orchestrates steps, communicates with workers, and aggregates data.
    """
    global simulation_step, total_cars_in_sim, simulation_active, simulation_start_time, step_start_time, step_times

    print("Master: Starting simulation loop...")
    simulation_start_time = time.time()
    end_time = simulation_start_time + duration if duration else float('inf')

    print("Master: Waiting for workers to register...")
    initial_wait_timeout = 60
    start_wait_time = time.time()
    while len(registered_workers) < 4:
        if time.time() - start_wait_time > initial_wait_timeout:
            print(f"Master: Timed out waiting for all 4 workers. Only {len(registered_workers)} registered. Starting simulation with available workers.")
            break
        time.sleep(1)
    
    if not registered_workers:
        print("Master: No workers registered. Exiting simulation.")
        simulation_active = False
        return

    while simulation_active and time.time() < end_time:
        simulation_step += 1
        step_start_time = time.time()
        print(f"\nMaster: Simulation Step {simulation_step}")

        worker_response_status = {}
        for zone, worker_info in list(registered_workers.items()):
            worker_url = worker_info['url']
            try:
                response = net_sim.network_call(requests.post)(
                    f"{worker_url}/simulate_step",
                    json={"step": simulation_step, "master_id": "master_123"},
                    timeout=5
                )
                response.raise_for_status()
                worker_response_status[zone] = "OK"
            except requests.exceptions.Timeout:
                worker_response_status[zone] = "TIMEOUT"
                print(f"Master: Worker {zone} at {worker_url} timed out after 5s for step {simulation_step}.")
            except requests.exceptions.ConnectionError:
                worker_response_status[zone] = "CONN_ERROR"
                print(f"Master: Connection error with worker {zone} at {worker_url} for step {simulation_step}. Is it still running?")
            except requests.exceptions.RequestException as e:
                worker_response_status[zone] = f"ERROR: {e}"
                print(f"Master: General error communicating with worker {zone} at {worker_url}: {e}")
                
        
        current_total_cars = sum(data['car_count'] for data in registered_workers.values())
        print(f"Master: Current total cars: {current_total_cars}")

        step_end_time = time.time()
        step_duration = step_end_time - step_start_time
        step_times.append(step_duration)

        with graph_data_lock:
            graph_data_history.append((simulation_step, current_total_cars))

        print(f"Master: Step {simulation_step} completed in {step_duration:.4f} seconds.")
        time.sleep(0.5) # NEW: Reduced delay between master steps for faster simulation progress

    simulation_active = False
    print("\nMaster: Simulation loop finished.")

    if test_mode and step_times:
        avg_step_time = statistics.mean(step_times)
        print(f"Performance Metrics: avg_step_time: {avg_step_time:.4f}")
    elif test_mode:
        print("Performance Metrics: No step times recorded for test mode.")

# =============================================================================
# Worker Node Logic
# =============================================================================
# Worker-specific simulation state
worker_vehicles = []
worker_traffic_light = None
current_zone_bounds = (0, 0, ZONE_SIZE, ZONE_SIZE) # Default bounds for a square zone

@app.route('/simulate_step', methods=['POST'])
def worker_simulate_step():
    """
    Endpoint for the master to tell a worker to perform a simulation step.
    This now includes detailed vehicle and traffic light simulation.
    """
    global total_cars_in_sim, simulation_step, worker_vehicles, worker_traffic_light
    
    data = request.json
    master_step = data.get('step')
    
    simulation_step = master_step

    if worker_traffic_light:
        worker_traffic_light.update()

    for vehicle in worker_vehicles:
        vehicle.move()

    # Randomly add/remove vehicles to simulate flow (simplistic)
    # NEW: Increased probability and max cars
    if random.random() < 0.4 and len(worker_vehicles) < MAX_CARS_PER_ZONE:
        direction = random.choice(['E', 'W', 'N', 'S'])
        # Spawn points slightly outside the edge to make full "enter" visible
        if direction == 'E': 
            x, y = -CAR_SIZE, ZONE_SIZE/2 - CAR_SIZE/2 # Spawn on left horizontal road
        elif direction == 'W': 
            x, y = ZONE_SIZE, ZONE_SIZE/2 - CAR_SIZE/2 # Spawn on right horizontal road
        elif direction == 'S': 
            x, y = ZONE_SIZE/2 - CAR_SIZE/2, -CAR_SIZE # Spawn on top vertical road
        elif direction == 'N': 
            x, y = ZONE_SIZE/2 - CAR_SIZE/2, ZONE_SIZE # Spawn on bottom vertical road
        else:
            x, y = random.randint(0, ZONE_SIZE - CAR_SIZE), random.randint(0, ZONE_SIZE - CAR_SIZE)
        
        new_car_id = f"{worker_id}_car_{time.time()}_{random.randint(0,1000)}"
        worker_vehicles.append(Vehicle(x, y, direction, current_zone_bounds, new_car_id))

    # Occasionally remove a random car to prevent infinite growth / simulate exiting
    if random.random() < 0.05 and len(worker_vehicles) > 10: # 5% chance to remove if more than 10
        worker_vehicles.pop(random.randint(0, len(worker_vehicles) - 1))

    total_cars_in_sim = len(worker_vehicles)

    vehicles_state = [v.get_state() for v in worker_vehicles]
    traffic_light_state = worker_traffic_light.get_state() if worker_traffic_light else None

    net_sim.network_call(_send_traffic_update_to_master)(
        total_cars_in_sim, vehicles_state, traffic_light_state
    )

    return jsonify({"status": "acknowledged", "worker_id": worker_id})

@net_sim.network_call
def _send_traffic_update_to_master(current_car_count, vehicles_state, traffic_light_state):
    """
    Sends the worker's current traffic data (including detailed visualization data) to the master.
    Decorated with network_sim.network_call to simulate network delay.
    """
    try:
        response = requests.post(
            f"http://{master_host}:{master_port}/traffic_update",
            json={
                "zone": worker_zone,
                "car_count": current_car_count,
                "worker_id": worker_id,
                "vehicles": vehicles_state,
                "traffic_light": traffic_light_state
            },
            timeout=5
        )
        response.raise_for_status()
        print(f"Worker {worker_id}: Sent update to master. Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Worker {worker_id}: Error sending update to master: {e}")

def worker_startup(zone, host, port=5000):
    """
    Initializes and registers the worker with the master.
    Also initializes worker's local simulation entities.
    """
    global worker_zone, master_host, master_port, total_cars_in_sim, worker_traffic_light, worker_vehicles
    worker_zone = zone
    master_host = host
    master_port = port
    
    # NEW: Increased initial car count
    total_cars_in_sim = random.randint(15, 25)
    for i in range(total_cars_in_sim):
        direction = random.choice(['E', 'W', 'N', 'S'])
        x, y = 0, 0 # Initialize, will be set based on direction
        # Initial placement to distribute cars on roads
        if direction == 'E': 
            x,y = random.uniform(0, ZONE_SIZE * 0.4), ZONE_SIZE/2 - CAR_SIZE/2
        elif direction == 'W': 
            x,y = random.uniform(ZONE_SIZE * 0.6, ZONE_SIZE), ZONE_SIZE/2 - CAR_SIZE/2
        elif direction == 'S': 
            x,y = ZONE_SIZE/2 - CAR_SIZE/2, random.uniform(0, ZONE_SIZE * 0.4)
        elif direction == 'N': 
            x,y = ZONE_SIZE/2 - CAR_SIZE/2, random.uniform(ZONE_SIZE * 0.6, ZONE_SIZE)
        
        worker_vehicles.append(Vehicle(x, y, direction, current_zone_bounds, f"car_{zone}_{i}"))
    
    worker_traffic_light = TrafficLight(ZONE_SIZE/2, ZONE_SIZE/2)


    master_url = f"http://{master_host}:{master_port}"
    
    print(f"Worker {worker_id} ({worker_zone}): Attempting to register with master at {master_url}...")
    
    retries = 5
    worker_self_port = None

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    base_worker_port_range = master_port + 100
    max_worker_port_range = base_worker_port_range + 200
    
    for p in range(base_worker_port_range, max_worker_port_range):
        try:
            s.bind(("0.0.0.0", p))
            s.close()
            worker_self_port = p
            break
        except OSError:
            continue
    
    if worker_self_port is None:
        print("Worker: Could not find an available port to bind its Flask server. Exiting.")
        sys.exit(1)

    worker_self_url = f"http://{socket.gethostname()}:{worker_self_port}"

    while retries > 0:
        try:
            response = net_sim.network_call(requests.post)(
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
            print(f"Worker {worker_id}: Error during registration: {e}")
            sys.exit(1)
    else:
        print(f"Worker {worker_id}: Failed to register with master after multiple retries. Exiting.")
        sys.exit(1)

    print(f"Worker {worker_id} ({worker_zone}): Starting Flask server on {worker_self_url.split('//')[1]}")
    
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=worker_self_port, debug=False, use_reloader=False), daemon=True).start()

    print(f"Worker {worker_id} ({worker_zone}): Worker ready and listening on port {worker_self_port}. Waiting for master commands.")
    
    try:
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
    parser.add_argument("--zone", type=str, help="Zone for worker node (e.g., North, South, East, West)")
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
