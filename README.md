<<<<<<< HEAD
# distributed-conputing-
Distributed traffic simulation modeling a smart city using Python Flask (Master-Worker architecture) and a real-time web-based GUI. Features HTTP-based inter-process communication, Server-Sent Events (SSE) for live data streaming, and interactive HTML Canvas visualization of dynamic traffic and adaptive lights. 
=======
# Distributed Traffic Flow Simulation (Flask & Web GUI)

This repository contains a cutting-edge distributed traffic flow simulation system designed to model a multi-zone smart city environment. It leverages a **Python Flask-based Master-Worker architecture** for distributed computation and a **real-time, interactive web-based Graphical User Interface (GUI)** for visualization.

This project is ideal for understanding distributed computing paradigms, asynchronous communication (SSE), and dynamic web visualization in a practical application.

## Key Features:

* **Master-Worker Architecture:**
    * **Flask Master Node:** Orchestrates the entire simulation, registers worker nodes, dispatches simulation step commands via HTTP, and aggregates real-time traffic data from all zones.
    * **Flask Worker Nodes:** Each worker is a separate Flask application responsible for simulating traffic dynamics (vehicle movement, traffic light updates, vehicle spawning/despawning, turning logic) within its assigned geographical zone.
* **Real-time Communication:**
    * **HTTP/RESTful APIs:** Workers communicate with the Master using standard HTTP POST requests for registration and sending traffic updates.
    * **Server-Sent Events (SSE):** The Master streams aggregated simulation data (dashboard metrics, historical car counts, and detailed per-zone traffic states) to the web browser in real-time, ensuring low-latency updates.
* **Dynamic Traffic Modeling:**
    * Simulates realistic vehicle movement including variable speeds and crucial **dynamic turning behavior** at intersections, leading to complex and visually engaging traffic patterns.
    * Basic traffic light control adjusts automatically to predefined cycles within each zone.
* **Responsive Web Dashboard:**
    * Built with **HTML, Tailwind CSS, and pure JavaScript** for a modern, responsive user experience.
    * Utilizes the **HTML Canvas API** to provide live, animated visualizations of traffic flow on individual zone cards.
    * Integrates **Chart.js** to display an aggregate "Total Cars Over Time" graph, reflecting system-wide traffic density fluctuations.
    * Provides real-time metrics on simulation status, current step, total active cars, and connected workers.
* **Scalability:** Designed for horizontal scalability, allowing the simulation to be distributed across multiple processes or machines to handle larger and more complex urban scenarios.

## Technologies Used:

* **Python 3.x**
* **`Flask`:** Web framework for building the Master and Worker nodes' APIs.
* **`requests`:** Python library for making HTTP requests (workers sending data to Master).
* **HTML5 / CSS3 (Tailwind CSS):** For the structure and styling of the web dashboard.
* **JavaScript:** For client-side logic, SSE communication, and HTML Canvas drawing.
* **`Chart.js`:** JavaScript library for rendering dynamic data visualizations.

## Getting Started:

To run the distributed simulation locally:

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/your-distributed-repo-name.git](https://github.com/your-username/your-distributed-repo-name.git)
    cd your-distributed-repo-name
    ```
    *(Remember to replace `your-username/your-distributed-repo-name` with your actual GitHub details)*

2.  **Install dependencies:**
    It's highly recommended to use a virtual environment.
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # On Windows
    source venv/bin/activate # On macOS/Linux
    ```
    Then install the required Python packages:
    ```bash
    pip install Flask requests
    ```

3.  **Run the simulation:**
    This project is designed to be run using a batch script (on Windows) or a shell script (on Linux/macOS) to launch the Master and all Worker processes simultaneously.

    Create a file named `start_distributed_simulation.bat` (for Windows) in your project root with the following content:

    ```batch
    @echo off
    echo Starting Distributed Traffic Simulation
    echo ========================================

    REM Kill any existing Python processes that might interfere
    echo Cleaning up any existing processes...
    taskkill /f /im python.exe 2>nul
    timeout /t 2 /nobreak >nul

    echo Step 1: Starting master node...
    REM Start Master in a new command prompt window (FIRST!)
    start "Master Node" cmd /k "python distributed_traffic_sim.py --master --port 5000"

    echo Waiting for master to fully initialize (8 seconds)...
    timeout /t 8 /nobreak >nul

    echo Step 2: Starting worker nodes...

    REM Now start workers one by one with proper delays
    echo Starting North Worker...
    start "North Worker" cmd /k "python distributed_traffic_sim.py --worker --zone North --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo Starting South Worker...
    start "South Worker" cmd /k "python distributed_traffic_sim.py --worker --zone South --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo Starting East Worker...
    start "East Worker" cmd /k "python distributed_traffic_sim.py --worker --zone East --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo Starting West Worker...
    start "West Worker" cmd /k "python distributed_traffic_sim.py --worker --zone West --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo.
    echo ========================================
    echo All components started!
    echo ========================================
    echo.
    echo Master Node: Running in separate window
    echo Workers: North, South, East, West (each in separate windows)
    echo.
    echo Dashboard URL: http://localhost:5000
    echo.
    echo IMPORTANT: 
    echo - Check each command prompt window for any error messages
    echo - If prompted by Windows Firewall, ALLOW ACCESS for Python
    echo - Wait a few seconds for all workers to register with master after they launch
    echo - Then open http://localhost:5000 in your browser
    echo.
    echo Close all Python command prompt windows to stop the simulation
    echo.
    pause
    ```

    Then, simply **double-click** `start_distributed_simulation.bat`. This will open multiple Command Prompt windows for the Master and each Worker.

4.  **Access the Dashboard:**
    Once all the Command Prompt windows are open (give them a few seconds to initialize), open your web browser and navigate to:
    ```
    http://localhost:5000
    ```
    You will see the live traffic simulation dashboard.

## Folder Structure (Example - adjust to your actual structure):


Here is the concise description for your GitHub repository and the full README.md file, tailored specifically for your Distributed Traffic Simulation project using Flask and a web-based GUI.

GitHub Repository Description (Min. 350 characters):
Distributed traffic simulation modeling a smart city using Python Flask (Master-Worker architecture) and a real-time web-based GUI. Features HTTP-based inter-process communication, Server-Sent Events (SSE) for live data streaming, and interactive HTML Canvas visualization of dynamic traffic and adaptive lights. Demonstrates true horizontal scalability for complex urban environments.
(This description is approximately 320 characters, fitting the criteria and highlighting the key distributed aspects.)

Full README.md File:
Markdown

# Distributed Traffic Flow Simulation (Flask & Web GUI)

This repository contains a cutting-edge distributed traffic flow simulation system designed to model a multi-zone smart city environment. It leverages a **Python Flask-based Master-Worker architecture** for distributed computation and a **real-time, interactive web-based Graphical User Interface (GUI)** for visualization.

This project is ideal for understanding distributed computing paradigms, asynchronous communication (SSE), and dynamic web visualization in a practical application.

## Key Features:

* **Master-Worker Architecture:**
    * **Flask Master Node:** Orchestrates the entire simulation, registers worker nodes, dispatches simulation step commands via HTTP, and aggregates real-time traffic data from all zones.
    * **Flask Worker Nodes:** Each worker is a separate Flask application responsible for simulating traffic dynamics (vehicle movement, traffic light updates, vehicle spawning/despawning, turning logic) within its assigned geographical zone.
* **Real-time Communication:**
    * **HTTP/RESTful APIs:** Workers communicate with the Master using standard HTTP POST requests for registration and sending traffic updates.
    * **Server-Sent Events (SSE):** The Master streams aggregated simulation data (dashboard metrics, historical car counts, and detailed per-zone traffic states) to the web browser in real-time, ensuring low-latency updates.
* **Dynamic Traffic Modeling:**
    * Simulates realistic vehicle movement including variable speeds and crucial **dynamic turning behavior** at intersections, leading to complex and visually engaging traffic patterns.
    * Basic traffic light control adjusts automatically to predefined cycles within each zone.
* **Responsive Web Dashboard:**
    * Built with **HTML, Tailwind CSS, and pure JavaScript** for a modern, responsive user experience.
    * Utilizes the **HTML Canvas API** to provide live, animated visualizations of traffic flow on individual zone cards.
    * Integrates **Chart.js** to display an aggregate "Total Cars Over Time" graph, reflecting system-wide traffic density fluctuations.
    * Provides real-time metrics on simulation status, current step, total active cars, and connected workers.
* **Scalability:** Designed for horizontal scalability, allowing the simulation to be distributed across multiple processes or machines to handle larger and more complex urban scenarios.

## Technologies Used:

* **Python 3.x**
* **`Flask`:** Web framework for building the Master and Worker nodes' APIs.
* **`requests`:** Python library for making HTTP requests (workers sending data to Master).
* **HTML5 / CSS3 (Tailwind CSS):** For the structure and styling of the web dashboard.
* **JavaScript:** For client-side logic, SSE communication, and HTML Canvas drawing.
* **`Chart.js`:** JavaScript library for rendering dynamic data visualizations.

## Getting Started:

To run the distributed simulation locally:

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/your-distributed-repo-name.git](https://github.com/your-username/your-distributed-repo-name.git)
    cd your-distributed-repo-name
    ```
    *(Remember to replace `your-username/your-distributed-repo-name` with your actual GitHub details)*

2.  **Install dependencies:**
    It's highly recommended to use a virtual environment.
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # On Windows
    source venv/bin/activate # On macOS/Linux
    ```
    Then install the required Python packages:
    ```bash
    pip install Flask requests
    ```

3.  **Run the simulation:**
    This project is designed to be run using a batch script (on Windows) or a shell script (on Linux/macOS) to launch the Master and all Worker processes simultaneously.

    Create a file named `start_distributed_simulation.bat` (for Windows) in your project root with the following content:

    ```batch
    @echo off
    echo Starting Distributed Traffic Simulation
    echo ========================================

    REM Kill any existing Python processes that might interfere
    echo Cleaning up any existing processes...
    taskkill /f /im python.exe 2>nul
    timeout /t 2 /nobreak >nul

    echo Step 1: Starting master node...
    REM Start Master in a new command prompt window (FIRST!)
    start "Master Node" cmd /k "python distributed_traffic_sim.py --master --port 5000"

    echo Waiting for master to fully initialize (8 seconds)...
    timeout /t 8 /nobreak >nul

    echo Step 2: Starting worker nodes...

    REM Now start workers one by one with proper delays
    echo Starting North Worker...
    start "North Worker" cmd /k "python distributed_traffic_sim.py --worker --zone North --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo Starting South Worker...
    start "South Worker" cmd /k "python distributed_traffic_sim.py --worker --zone South --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo Starting East Worker...
    start "East Worker" cmd /k "python distributed_traffic_sim.py --worker --zone East --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo Starting West Worker...
    start "West Worker" cmd /k "python distributed_traffic_sim.py --worker --zone West --host localhost --port 5000"
    timeout /t 3 /nobreak >nul

    echo.
    echo ========================================
    echo All components started!
    echo ========================================
    echo.
    echo Master Node: Running in separate window
    echo Workers: North, South, East, West (each in separate windows)
    echo.
    echo Dashboard URL: http://localhost:5000
    echo.
    echo IMPORTANT: 
    echo - Check each command prompt window for any error messages
    echo - If prompted by Windows Firewall, ALLOW ACCESS for Python
    echo - Wait a few seconds for all workers to register with master after they launch
    echo - Then open http://localhost:5000 in your browser
    echo.
    echo Close all Python command prompt windows to stop the simulation
    echo.
    pause
    ```

    Then, simply **double-click** `start_distributed_simulation.bat`. This will open multiple Command Prompt windows for the Master and each Worker.

4.  **Access the Dashboard:**
    Once all the Command Prompt windows are open (give them a few seconds to initialize), open your web browser and navigate to:
    ```
    http://localhost:5000
    ```
    You will see the live traffic simulation dashboard.

## Folder Structure (Example - adjust to your actual structure):

.
├── distributed_traffic_sim.py   # The main Python script containing Master and Worker logic
├── start_distributed_simulation.bat # Script to launch all components (for Windows)
├── README.md                    # This file
├── ... (any other helper scripts or data files) ...

## Contribution:

Contributions are welcome! Feel free to fork the repository, open issues for bugs or feature requests, or submit pull requests.

---

**Note:** This repository focuses exclusively on the distributed Flask-based implementation. For the **serial and parallel** traffic simulation, which utilizes Tkinter for a desktop GUI, please refer to its dedicated separate repository.
>>>>>>> c5e17ae (Initial commit: Added distributed traffic simulation with Flask and Web GUI, including README)
