#!/usr/bin/env python3

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
        
        # Create the app indicator with a system icon
        self.indicator = AppIndicator3.Indicator.new(
            "unity-sys-monitor",
            "utilities-system-monitor",  # Use a system icon that's guaranteed to exist
            AppIndicator3.IndicatorCategory.SYSTEM_SERVICES
        )
        
        # If icon doesn't exist, use a fallback
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        
        # Check for radeontop first
        self.has_radeontop = self.check_radeontop()
        self.radeontop_process = None
        self.radeontop_lock = threading.Lock()
        self.gpu_percent = 0
        
        # Unicode symbols for the panel display
        self.cpu_symbol = "💻"  # Computer/CPU symbol
        self.gpu_symbol = "🎞️"  # Gaming/GPU symbol
        self.net_symbol = "🌐"  # Network/Globe symbol
        self.mem_symbol = "💻"  # Brain/Memory symbol
        self.disk_symbol = "💾"  # Floppy/Disk symbol
        
        # Create a menu
        self.menu = Gtk.Menu()
        
        # CPU label item with icon
        self.cpu_item = Gtk.MenuItem()
        self.cpu_item.set_label(f"{self.cpu_symbol} CPU: Initializing...")
        self.cpu_item.set_sensitive(False)
        self.menu.append(self.cpu_item)
        
        # GPU label item with icon - only if radeontop is installed
        if self.has_radeontop:
            self.gpu_item = Gtk.MenuItem()
            self.gpu_item.set_label(f"{self.gpu_symbol} GPU: Initializing...")
            self.gpu_item.set_sensitive(False)
            self.menu.append(self.gpu_item)
        
        # Memory label item with icon
        self.mem_item = Gtk.MenuItem()
        self.mem_item.set_label(f"{self.mem_symbol} Memory: Initializing...")
        self.mem_item.set_sensitive(False)
        self.menu.append(self.mem_item)
        
        # Disk usage item with icon
        self.disk_item = Gtk.MenuItem()
        self.disk_item.set_label(f"{self.disk_symbol} Disk: Initializing...")
        self.disk_item.set_sensitive(False)
        self.menu.append(self.disk_item)
        
        # Network item with icon
        self.net_item = Gtk.MenuItem()
        self.net_item.set_label(f"{self.net_symbol} Network: Initializing...")
        self.net_item.set_sensitive(False)
        self.menu.append(self.net_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Preferences submenu
        prefs_item = Gtk.MenuItem(label="Preferences")
        prefs_submenu = Gtk.Menu()
        
        # Update interval
        interval_item = Gtk.MenuItem(label="Update Interval")
        interval_submenu = Gtk.Menu()
        
        # Update interval options
        for interval in [1, 2, 5]:
            item = Gtk.RadioMenuItem(label=f"{interval} seconds")
            item.set_active(interval == 2)  # Default is 2
            item.connect("activate", self.set_update_interval, interval)
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
        self.update_interval = 2
        
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
    
    def check_radeontop(self):
        """Check if radeontop is installed"""
        try:
            subprocess.run(["which", "radeontop"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            return False
    
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
    
    def set_update_interval(self, widget, interval):
        """Set the update interval"""
        if widget.get_active():
            self.update_interval = interval
    
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
            
            # Update labels in the main thread
            GLib.idle_add(self.update_labels, cpu_percent, gpu_percent, mem_percent, disk_percent, recv_speed, sent_speed)
            
            time.sleep(self.update_interval)
    
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
        
        # Update the indicator label with CPU, GPU (if available), and network stats with icons
        # Add extra space after main icon
        panel_text = f"   {self.cpu_symbol} {cpu_formatted}"
        
        if self.has_radeontop:
            gpu_formatted = self.format_percent(gpu_percent)
            panel_text += f"    |    {self.gpu_symbol} {gpu_formatted}"
            self.gpu_item.set_label(f"{self.gpu_symbol} GPU: {self.format_percent(gpu_percent)}")
        
        # Add extra space around network values and between download/upload
        panel_text += f"    |    {self.net_symbol} ↓{recv_fixed}     ↑{sent_fixed}"
        self.indicator.set_label(panel_text, "")
        
        # Update menu items
        self.cpu_item.set_label(f"{self.cpu_symbol} CPU: {self.format_percent(cpu_percent)}")
        self.mem_item.set_label(f"{self.mem_symbol} Memory: {self.format_percent(mem_percent)}")
        self.disk_item.set_label(f"{self.disk_symbol} Disk: {self.format_percent(disk_percent)}")
        
        # Use more detailed format for the menu
        recv_formatted = self.format_bytes(recv_speed)
        sent_formatted = self.format_bytes(sent_speed)
        self.net_item.set_label(f"{self.net_symbol} Network: ↓ {recv_formatted} ↑ {sent_formatted}")
        
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