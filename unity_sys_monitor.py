#!/usr/bin/env python3
"""
Unity System Monitor
-------------------
A lightweight system monitoring indicator for Ubuntu/Unity desktop environments.
Displays CPU, GPU, memory, disk, and network usage in the system tray.

Features:
- Real-time system resource monitoring
- Support for AMD GPU monitoring (via radeontop)
- CPU power profile control
- Configurable update intervals
- Monospace font display to prevent UI jumping

License: MIT License
Copyright (c) 2023-2024 Kevin Hinds

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Version: 1.0.0
Author: Kevin Hinds
GitHub: https://github.com/khinds10/Unity-Desktop-System-Tray-Monitor
"""

import gi
import psutil
import signal
import os
import time
import subprocess
import re
import threading
from threading import Thread

gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, GLib, AppIndicator3

class UnitySysMonitor:
    def __init__(self):
        # Initialize running state first
        self.running = True
        
        # Get the path to the icon file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "icon.png")
        
        # Create the app indicator with the original icon
        self.indicator = AppIndicator3.Indicator.new(
            "unity-sys-monitor",
            icon_path,  # Use the original icon.png file
            AppIndicator3.IndicatorCategory.SYSTEM_SERVICES
        )
        
        # Set indicator properties
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        
        # Check for radeontop first
        self.has_radeontop = self.check_radeontop()
        self.radeontop_process = None
        self.radeontop_lock = threading.Lock()
        self.gpu_percent = 0
        
        # Check for power-profiles-daemon
        self.has_power_profiles = self.check_power_profiles()
        self.current_power_profile = "balanced"  # Default assumption
        if self.has_power_profiles:
            self.current_power_profile = self.get_current_power_profile()
        
        # Unicode symbols for the panel display
        self.cpu_symbol = "💻"  # Computer/CPU symbol
        self.gpu_symbol = "🎞️"  # Gaming/GPU symbol
        self.net_symbol = "🌐"  # Network/Globe symbol
        self.mem_symbol = "💻"  # Brain/Memory symbol
        self.disk_symbol = "💾"  # Floppy/Disk symbol
        
        # Create a menu
        self.menu = Gtk.Menu()
        
        # CPU label item with icon
        self.cpu_item = self.create_monospace_menu_item(f"{self.cpu_symbol} CPU: Initializing...")
        self.cpu_item.set_sensitive(False)
        self.menu.append(self.cpu_item)
        
        # GPU label item with icon - only if radeontop is installed
        if self.has_radeontop:
            self.gpu_item = self.create_monospace_menu_item(f"{self.gpu_symbol} GPU: Initializing...")
            self.gpu_item.set_sensitive(False)
            self.menu.append(self.gpu_item)
        
        # Memory label item with icon
        self.mem_item = self.create_monospace_menu_item(f"{self.mem_symbol} Memory: Initializing...")
        self.mem_item.set_sensitive(False)
        self.menu.append(self.mem_item)
        
        # Disk usage item with icon
        self.disk_item = self.create_monospace_menu_item(f"{self.disk_symbol} Disk: Initializing...")
        self.disk_item.set_sensitive(False)
        self.menu.append(self.disk_item)
        
        # Network item with icon
        self.net_item = self.create_monospace_menu_item(f"{self.net_symbol} Network: Initializing...")
        self.net_item.set_sensitive(False)
        self.menu.append(self.net_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # CPU Power Profile submenu
        if self.has_power_profiles:
            power_item = Gtk.MenuItem(label="CPU Power Profile")
            power_submenu = Gtk.Menu()
            
            # Create power profile radio items
            self.profile_items = {}
            
            # Create the first item - needed to create the radio group
            profiles = ["performance", "balanced", "power-saver"]
            first_profile = profiles[0]
            first_item = Gtk.RadioMenuItem(label=first_profile.capitalize())
            first_item.set_active(first_profile == self.current_power_profile)
            first_item.connect("toggled", self.on_profile_toggled, first_profile)
            self.profile_items[first_profile] = first_item
            power_submenu.append(first_item)
            
            # Create the rest of the radio items in the same group
            for profile in profiles[1:]:
                item = Gtk.RadioMenuItem.new_with_label_from_widget(first_item, profile.capitalize())
                item.set_active(profile == self.current_power_profile)
                item.connect("toggled", self.on_profile_toggled, profile)
                self.profile_items[profile] = item
                power_submenu.append(item)
            
            power_item.set_submenu(power_submenu)
            self.menu.append(power_item)
            
            # Separator
            self.menu.append(Gtk.SeparatorMenuItem())
        
        # Preferences submenu
        prefs_item = Gtk.MenuItem(label="Preferences")
        prefs_submenu = Gtk.Menu()
        
        # Update interval
        interval_item = Gtk.MenuItem(label="Update Interval")
        interval_submenu = Gtk.Menu()
        
        # Update interval options
        interval_group = None
        for interval in [1, 2, 5]:
            if interval_group is None:
                item = Gtk.RadioMenuItem(label=f"{interval} seconds")
                interval_group = item
            else:
                item = Gtk.RadioMenuItem.new_with_label_from_widget(interval_group, f"{interval} seconds")
            item.set_active(interval == 1)  # Default is 1
            item.connect("toggled", self.on_interval_toggled, interval)
            interval_submenu.append(item)
        
        interval_item.set_submenu(interval_submenu)
        prefs_submenu.append(interval_item)
        prefs_item.set_submenu(prefs_submenu)
        self.menu.append(prefs_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Quit item
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.quit)
        self.menu.append(quit_item)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        
        # Initialize update interval
        self.update_interval = 1
        
        # Previous network stats for calculating rate
        self.prev_net_io = psutil.net_io_counters()
        self.prev_net_time = time.time()
        
        # Start the GPU monitoring subprocess if radeontop is available
        if self.has_radeontop:
            self.start_radeontop()
        
        # Start the update thread
        self.update_thread = Thread(target=self.update_stats)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def create_monospace_menu_item(self, text):
        """Create a menu item with monospace font"""
        item = Gtk.MenuItem()
        label = Gtk.Label()
        label.set_markup(f'<span font_family="monospace">{text}</span>')
        label.set_xalign(0.0)  # Left-align text
        item.add(label)
        return item
    
    def update_monospace_menu_item(self, item, text):
        """Update the label of a monospace menu item"""
        label = item.get_child()
        label.set_markup(f'<span font_family="monospace">{text}</span>')
    
    def check_radeontop(self):
        """Check if radeontop is installed"""
        try:
            subprocess.run(["which", "radeontop"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def check_power_profiles(self):
        """Check if power-profiles-daemon is installed and running"""
        try:
            result = subprocess.run(
                ["powerprofilesctl", "list"], 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            return "balanced" in result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def get_current_power_profile(self):
        """Get the current power profile"""
        try:
            result = subprocess.run(
                ["powerprofilesctl", "get"], 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            # Remove leading/trailing whitespace
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "balanced"
    
    def on_profile_toggled(self, widget, profile):
        """Handle radio menu item toggled signal for power profiles"""
        if widget.get_active() and profile != self.current_power_profile:
            try:
                subprocess.run(
                    ["pkexec", "powerprofilesctl", "set", profile], 
                    check=True,
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE
                )
                self.current_power_profile = profile
            except subprocess.CalledProcessError:
                # If it fails, reset UI without triggering signals
                GLib.idle_add(self.update_power_profile_ui)
    
    def on_interval_toggled(self, widget, interval):
        """Handle radio menu item toggled signal for update interval"""
        if widget.get_active():
            self.update_interval = interval
    
    def start_radeontop(self):
        """Start radeontop as a continuous process"""
        try:
            # Use pkexec to get root privileges, but only once
            self.radeontop_process = subprocess.Popen(
                ["pkexec", "radeontop", "-d", "-", "-t", "1"],
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Start thread to continuously read from radeontop's output
            radeontop_thread = Thread(target=self.read_radeontop_output)
            radeontop_thread.daemon = True
            radeontop_thread.start()
            
            return True
        except subprocess.SubprocessError as e:
            print(f"Failed to start radeontop: {e}")
            self.has_radeontop = False
            return False
    
    def read_radeontop_output(self):
        """Continuously read from radeontop output"""
        if not self.radeontop_process:
            return
            
        while self.running and self.radeontop_process.poll() is None:
            try:
                line = self.radeontop_process.stdout.readline()
                if not line:
                    break
                    
                # Extract the GPU usage from the output
                match = re.search(r'gpu\s+(\d+\.\d+)', line)
                if match:
                    with self.radeontop_lock:
                        self.gpu_percent = float(match.group(1))
            except Exception as e:
                print(f"Error reading radeontop output: {e}")
                break
                
        # If we get here, radeontop has stopped
        if self.running:
            with self.radeontop_lock:
                self.has_radeontop = False
    
    def update_stats(self):
        """Background thread to update system stats"""
        while self.running:
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # GPU usage is updated in the radeontop thread
            gpu_percent = 0
            if self.has_radeontop:
                with self.radeontop_lock:
                    gpu_percent = self.gpu_percent
            
            # Get memory usage
            mem = psutil.virtual_memory()
            mem_percent = mem.percent
            
            # Get disk usage (root filesystem)
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Get network usage
            current_net_io = psutil.net_io_counters()
            current_time = time.time()
            
            # Calculate network speeds
            time_delta = current_time - self.prev_net_time
            recv_speed = (current_net_io.bytes_recv - self.prev_net_io.bytes_recv) / time_delta
            sent_speed = (current_net_io.bytes_sent - self.prev_net_io.bytes_sent) / time_delta
            
            # Update previous values
            self.prev_net_io = current_net_io
            self.prev_net_time = current_time
            
            # Check if power profile has changed (every 10 seconds)
            if self.has_power_profiles and hasattr(self, 'update_count'):
                self.update_count += 1
                if self.update_count >= 5:
                    self.update_count = 0
                    new_profile = self.get_current_power_profile()
                    if new_profile != self.current_power_profile:
                        self.current_power_profile = new_profile
                        GLib.idle_add(self.update_power_profile_ui)
            else:
                self.update_count = 0
            
            # Update labels in the main thread
            GLib.idle_add(self.update_labels, cpu_percent, gpu_percent, mem_percent, disk_percent, recv_speed, sent_speed)
            
            time.sleep(self.update_interval)
    
    def update_power_profile_ui(self):
        """Update the power profile radio items"""
        if hasattr(self, 'profile_items') and self.current_power_profile in self.profile_items:
            for profile, item in self.profile_items.items():
                # Temporarily block the "toggled" signal
                handlers = []
                for handler_id in item.handler_get_connections():
                    if handler_id.callback_name == "on_profile_toggled":
                        handlers.append(handler_id)
                
                for handler_id in handlers:
                    item.handler_block(handler_id)
                
                # Set the active state based on current profile
                item.set_active(profile == self.current_power_profile)
                
                # Unblock the signals
                for handler_id in handlers:
                    item.handler_unblock(handler_id)
        
        return False
    
    def format_bytes(self, bytes):
        """Format bytes to human-readable form"""
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} TB/s"
    
    def format_bytes_fixed(self, bytes):
        """Format bytes to a truly fixed width string regardless of value magnitude"""
        # Convert to appropriate unit
        unit = 'B'
        for u in ['B', 'K', 'M', 'G', 'T']:
            if bytes < 1024 or u == 'T':
                unit = u
                break
            bytes /= 1024
        
        # Set an extra wide fixed format with 8 characters total width
        # Format is "XXX.XY" where Y is the unit and spaces for padding
        if bytes < 10:
            return f"    {bytes:.1f}{unit}"  # 4 spaces
        elif bytes < 100:
            return f"   {bytes:.1f}{unit}"   # 3 spaces
        else:
            # Cap at 999.9 for consistency
            return f"  {min(bytes, 999.9):.1f}{unit}"  # 2 spaces
    
    def format_percent(self, value):
        """Format a percentage value with fixed width to prevent UI jumping"""
        # Cap at 99.9%
        value = min(value, 99.9)
        return f"{value:5.1f}%"  # Will allocate 5 characters for the number plus 1 for the decimal point
    
    def update_labels(self, cpu_percent, gpu_percent, mem_percent, disk_percent, recv_speed, sent_speed):
        """Update indicator label and menu items"""
        # Cap CPU and GPU usage at 99.9%
        cpu_percent = min(cpu_percent, 99.9)
        gpu_percent = min(gpu_percent, 99.9)
        
        # Format network speeds with truly fixed width
        recv_fixed = self.format_bytes_fixed(recv_speed)
        sent_fixed = self.format_bytes_fixed(sent_speed)
        
        # Format percentages with fixed width
        cpu_formatted = self.format_percent(cpu_percent)
        
        # Update the indicator label with ONLY CPU and power profile indicator
        panel_text = f"   {self.cpu_symbol} {cpu_formatted}"
        
        # Add power profile indicator if available
        if self.has_power_profiles:
            # Use symbols to indicate power profile
            profile_symbol = "⚡" if self.current_power_profile == "performance" else \
                            "⚖️" if self.current_power_profile == "balanced" else "🔋"
            panel_text += f" {profile_symbol}"
        
        # Set the indicator label (no markup support)
        self.indicator.set_label(panel_text, "")
        
        # Update menu items with monospace font
        self.update_monospace_menu_item(self.cpu_item, f"{self.cpu_symbol} CPU: {self.format_percent(cpu_percent)}")
        
        if self.has_radeontop:
            self.update_monospace_menu_item(self.gpu_item, f"{self.gpu_symbol} GPU: {self.format_percent(gpu_percent)}")
            
        self.update_monospace_menu_item(self.mem_item, f"{self.mem_symbol} Memory: {self.format_percent(mem_percent)}")
        self.update_monospace_menu_item(self.disk_item, f"{self.disk_symbol} Disk: {self.format_percent(disk_percent)}")
        
        # Use more detailed format for the menu
        recv_formatted = self.format_bytes(recv_speed)
        sent_formatted = self.format_bytes(sent_speed)
        self.update_monospace_menu_item(self.net_item, f"{self.net_symbol} Network: ↓ {recv_formatted} ↑ {sent_formatted}")
        
        return False  # Required for GLib.idle_add
    
    def quit(self, widget):
        """Handle quit event"""
        self.running = False
        
        # Terminate radeontop process if running
        if self.radeontop_process:
            self.radeontop_process.terminate()
            try:
                self.radeontop_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.radeontop_process.kill()
        
        Gtk.main_quit()

if __name__ == "__main__":
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Create and start the indicator
    indicator = UnitySysMonitor()
    Gtk.main() 
