# Unity Desktop System Tray Monitor

A simple system resource monitor for the Unity desktop environment on Ubuntu.

## Features

- Shows CPU, GPU, and network usage in the panel indicator
- Displays detailed information in a dropdown menu:
  - CPU usage percentage (with icon)
  - GPU usage percentage (with icon, AMD Radeon cards)
  - Memory usage percentage (with icon)
  - Disk usage percentage (with icon)
  - Network download/upload speeds (with icon)
- Configurable update interval (1, 2, or 5 seconds)
- Lightweight and minimal resource usage

## Installation

### Prerequisites

First, install the required dependencies:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-gi gir1.2-appindicator3-0.1 python3-psutil
```

For GPU monitoring (AMD Radeon cards only):

```bash
sudo apt install radeontop
```

### Installation Steps

1. Clone or download this repository:

```bash
git clone https://github.com/khinds10/Unity-Desktop-System-Tray-Monitor
cd unity-sys-monitor
```

2. Make the script executable:

```bash
chmod +x unity_sys_monitor.py
```

## Usage

Run the script:

```bash
./unity_sys_monitor.py
```

The indicator will appear in your Unity desktop panel showing CPU, GPU (if available), and network usage.
Click on the indicator to see more detailed information about system resources.

Note: GPU monitoring requires the `radeontop` package and will request your password (via `pkexec`) once when the application starts. The application only requests root privileges once per session.

### Preferences

You can configure the update interval by selecting Preferences → Update Interval from the menu.

## Autostart

To have the monitor start automatically when you log in:

1. Create a desktop entry file:

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/unity-sys-monitor.desktop << EOF
[Desktop Entry]
Type=Application
Exec=/path/to/unity_sys_monitor.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Unity System Monitor
Comment=System Resource Monitor for Unity Desktop
EOF
```

2. Replace `/path/to/` with the absolute path to the script.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
