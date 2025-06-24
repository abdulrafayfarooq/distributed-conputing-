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