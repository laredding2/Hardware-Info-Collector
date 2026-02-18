#!/usr/bin/env python3
"""
hardware_info.py - Comprehensive System Hardware Information Tool

Gathers detailed hardware information and outputs a styled HTML report.

Covers:
- CPU: type, speed, cores, cache, temperature
- Memory: type, speed, capacity, usage
- GPU: type, speed, temperature, memory (NVIDIA / AMD / Intel)
- Disks: partitions, filesystem, usage, I/O counters, SMART data
- Network: interfaces, IPs, MAC addresses, speeds, I/O stats

Dependencies:
    pip install psutil py-cpuinfo GPUtil

Platform Notes:
    - CPU temperature: Linux (via lm-sensors), partial Windows support
    - GPU info: NVIDIA GPUs via nvidia-smi (GPUtil); AMD GPUs via rocm-smi
    - Memory type/speed: Linux (via dmidecode, may require sudo), Windows (via wmic)

Usage:
    python hardware_info.py              # Saves to ~/hardware_report.html
    python hardware_info.py -o report    # Saves to ~/report.html
"""

import argparse
import html
import platform
import re
import socket
import subprocess
import shutil
import json
import os
import webbrowser
from datetime import datetime

try:
    import psutil
except ImportError:
    psutil = None

try:
    import cpuinfo
except ImportError:
    cpuinfo = None

try:
    import GPUtil
except ImportError:
    GPUtil = None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def fmt_bytes(nbytes: int, suffix: str = "B") -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("", "K", "M", "G", "T", "P"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.2f} {unit}{suffix}"
        nbytes /= 1024
    return f"{nbytes:.2f} E{suffix}"


def run_cmd(cmd: list[str], timeout: int = 10) -> str | None:
    """Run a shell command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


def make_table(rows: list[list[str]], headers: list[str] | None = None) -> str:
    """Generate an HTML table string."""
    h = "<table>\n"
    if headers:
        h += "<thead><tr>"
        for hdr in headers:
            h += f"<th>{esc(hdr)}</th>"
        h += "</tr></thead>\n"
    h += "<tbody>\n"
    for row in rows:
        h += "<tr>"
        for cell in row:
            h += f"<td>{esc(str(cell))}</td>"
        h += "</tr>\n"
    h += "</tbody></table>\n"
    return h


def make_kv_table(rows: list[list[str]]) -> str:
    """Generate a key-value HTML table (2 columns, no header)."""
    h = '<table class="kv"><tbody>\n'
    for row in rows:
        key = esc(str(row[0])) if len(row) > 0 else ""
        val = esc(str(row[1])) if len(row) > 1 else ""
        h += f'<tr><td class="kv-key">{key}</td><td class="kv-val">{val}</td></tr>\n'
    h += "</tbody></table>\n"
    return h


def progress_bar(percent: float, color: str = "var(--accent)") -> str:
    """Generate an inline CSS progress bar."""
    clamped = max(0, min(100, percent))
    return (
        f'<div class="progress-bar">'
        f'<div class="progress-fill" style="width:{clamped:.1f}%;background:{color};"></div>'
        f'<span class="progress-label">{percent:.1f}%</span>'
        f'</div>'
    )


def make_card(title: str, icon: str, content: str, card_id: str = "") -> str:
    """Wrap content in a styled card with title and icon."""
    id_attr = f' id="{card_id}"' if card_id else ""
    return (
        f'<section class="card"{id_attr}>'
        f'<div class="card-header"><span class="card-icon">{icon}</span>'
        f'<h2>{esc(title)}</h2></div>'
        f'<div class="card-body">{content}</div>'
        f'</section>\n'
    )


def make_sub(title: str, content: str) -> str:
    """Sub-section within a card."""
    return f'<div class="sub-section"><h3>{esc(title)}</h3>{content}</div>\n'


# ──────────────────────────────────────────────
# Data Collectors
# ──────────────────────────────────────────────

def collect_system_summary() -> str:
    uname = platform.uname()
    rows = [
        ["Operating System", f"{uname.system} {uname.release}"],
        ["OS Version", uname.version],
        ["Machine Architecture", uname.machine],
        ["Node Name", uname.node],
        ["Python Version", platform.python_version()],
    ]
    if psutil:
        boot = datetime.fromtimestamp(psutil.boot_time())
        rows.append(["Boot Time", boot.strftime("%Y-%m-%d %H:%M:%S")])
    return make_kv_table(rows)


def collect_cpu_info() -> str:
    parts = []

    # ── Basic Info ──
    rows = []
    rows.append(["Processor", platform.processor() or "N/A"])
    rows.append(["Architecture", platform.machine()])

    if cpuinfo:
        info = cpuinfo.get_cpu_info()
        rows.append(["Brand", info.get("brand_raw", "N/A")])
        rows.append(["Vendor", info.get("vendor_id_raw", "N/A")])
        rows.append(["Family / Model / Stepping",
                      f"{info.get('family', '?')} / {info.get('model', '?')} / {info.get('stepping', '?')}"])
        rows.append(["Arch (detailed)", info.get("arch_string_raw", info.get("arch", "N/A"))])
        rows.append(["Base Frequency", info.get("hz_advertised_friendly", "N/A")])
        rows.append(["Current Frequency", info.get("hz_actual_friendly", "N/A")])
        l2 = info.get("l2_cache_size", "N/A")
        l3 = info.get("l3_cache_size", "N/A")
        if l2 != "N/A":
            rows.append(["L2 Cache", str(l2)])
        if l3 != "N/A":
            rows.append(["L3 Cache", str(l3)])
        flags = info.get("flags", [])
        notable = [f for f in ("sse4_2", "avx", "avx2", "avx512f", "aes", "fma3", "fma4") if f in flags]
        if notable:
            rows.append(["Notable Extensions", ", ".join(notable)])
    else:
        rows.append(["[py-cpuinfo]", "Not installed — install for detailed CPU info"])

    if psutil:
        rows.append(["Physical Cores", str(psutil.cpu_count(logical=False) or "N/A")])
        rows.append(["Logical Cores", str(psutil.cpu_count(logical=True) or "N/A")])
        freq = psutil.cpu_freq()
        if freq:
            rows.append(["Freq (current)", f"{freq.current:.2f} MHz"])
            if freq.min:
                rows.append(["Freq (min)", f"{freq.min:.2f} MHz"])
            if freq.max:
                rows.append(["Freq (max)", f"{freq.max:.2f} MHz"])

    parts.append(make_sub("Specifications", make_kv_table(rows)))

    # ── Usage ──
    if psutil:
        overall = psutil.cpu_percent(interval=1)
        usage_html = f'<div class="metric-row"><span class="metric-label">Overall CPU Usage</span>{progress_bar(overall)}</div>'
        per_cpu = psutil.cpu_percent(interval=0.5, percpu=True)
        if per_cpu:
            for i, u in enumerate(per_cpu):
                color = "var(--green)" if u < 50 else "var(--yellow)" if u < 80 else "var(--red)"
                usage_html += f'<div class="metric-row"><span class="metric-label">Core {i}</span>{progress_bar(u, color)}</div>'
        parts.append(make_sub("Usage", usage_html))

    # ── Temperature ──
    temp_html = ""
    temp_found = False

    if psutil and hasattr(psutil, "sensors_temperatures"):
        temps = psutil.sensors_temperatures()
        if temps:
            temp_rows = []
            for chip, entries in temps.items():
                for entry in entries:
                    label = f"{chip}: {entry.label or 'N/A'}"
                    current = f"{entry.current:.1f}°C" if entry.current else "N/A"
                    high = f"{entry.high:.1f}°C" if entry.high else "N/A"
                    critical = f"{entry.critical:.1f}°C" if entry.critical else "N/A"
                    temp_rows.append([label, current, high, critical])
            if temp_rows:
                temp_html = make_table(temp_rows, headers=["Sensor", "Current", "High", "Critical"])
                temp_found = True

    if not temp_found and platform.system() == "Linux":
        output = run_cmd(["sensors"])
        if output:
            temp_html = f"<pre>{esc(output)}</pre>"
            temp_found = True

    if not temp_found and platform.system() == "Windows":
        output = run_cmd(["powershell", "-Command",
                          "Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace root/wmi "
                          "| Select-Object InstanceName,CurrentTemperature | ConvertTo-Json"])
        if output:
            try:
                data = json.loads(output)
                if not isinstance(data, list):
                    data = [data]
                temp_rows = []
                for entry in data:
                    kelvin_tenths = entry.get("CurrentTemperature", 0)
                    celsius = (kelvin_tenths / 10) - 273.15
                    temp_rows.append([entry.get("InstanceName", "Unknown"), f"{celsius:.1f}°C"])
                temp_html = make_kv_table(temp_rows)
                temp_found = True
            except json.JSONDecodeError:
                pass

    if not temp_found:
        temp_html = '<p class="note">Temperature data not available (install lm-sensors on Linux, or run as admin on Windows)</p>'

    parts.append(make_sub("Temperature", temp_html))
    return "".join(parts)


def collect_memory_info() -> str:
    parts = []

    # ── Usage ──
    if psutil:
        vm = psutil.virtual_memory()
        color = "var(--green)" if vm.percent < 60 else "var(--yellow)" if vm.percent < 85 else "var(--red)"
        usage_html = f'<div class="metric-row"><span class="metric-label">RAM ({fmt_bytes(vm.used)} / {fmt_bytes(vm.total)})</span>{progress_bar(vm.percent, color)}</div>'

        rows = [
            ["Total RAM", fmt_bytes(vm.total)],
            ["Available", fmt_bytes(vm.available)],
            ["Used", fmt_bytes(vm.used)],
            ["Cached", fmt_bytes(getattr(vm, "cached", 0))],
            ["Buffers", fmt_bytes(getattr(vm, "buffers", 0))],
        ]
        usage_html += make_kv_table(rows)

        swap = psutil.swap_memory()
        if swap.total > 0:
            swap_color = "var(--green)" if swap.percent < 50 else "var(--yellow)" if swap.percent < 80 else "var(--red)"
            usage_html += f'<div class="metric-row" style="margin-top:0.8rem;"><span class="metric-label">Swap ({fmt_bytes(swap.used)} / {fmt_bytes(swap.total)})</span>{progress_bar(swap.percent, swap_color)}</div>'

        parts.append(make_sub("Usage", usage_html))
    else:
        parts.append('<p class="note">psutil not installed — install for memory usage info</p>')

    # ── Module Details ──
    module_html = ""
    module_found = False

    if platform.system() == "Linux":
        output = run_cmd(["sudo", "dmidecode", "-t", "memory"])
        if not output:
            output = run_cmd(["dmidecode", "-t", "memory"])
        if output:
            current_device: dict[str, str] = {}
            devices: list[dict[str, str]] = []
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("Memory Device"):
                    if current_device.get("Size") and "No Module" not in current_device.get("Size", ""):
                        devices.append(current_device)
                    current_device = {}
                for key in ("Size", "Type", "Speed", "Configured Memory Speed",
                            "Manufacturer", "Part Number", "Locator", "Form Factor"):
                    if line.startswith(f"{key}:"):
                        current_device[key] = line.split(":", 1)[1].strip()
            if current_device.get("Size") and "No Module" not in current_device.get("Size", ""):
                devices.append(current_device)
            if devices:
                mod_rows = []
                for dev in devices:
                    mod_rows.append([
                        dev.get("Locator", "N/A"), dev.get("Size", "N/A"),
                        dev.get("Type", "N/A"), dev.get("Speed", "N/A"),
                        dev.get("Manufacturer", "N/A"), dev.get("Part Number", "N/A").strip(),
                    ])
                module_html = make_table(mod_rows,
                                         headers=["Slot", "Size", "Type", "Speed", "Manufacturer", "Part Number"])
                module_found = True

    elif platform.system() == "Windows":
        output = run_cmd(["powershell", "-Command",
                          "Get-CimInstance Win32_PhysicalMemory | "
                          "Select-Object BankLabel,Capacity,SMBIOSMemoryType,Speed,"
                          "Manufacturer,PartNumber | ConvertTo-Json"])
        if output:
            try:
                data = json.loads(output)
                if not isinstance(data, list):
                    data = [data]
                smbios_map = {20: "DDR", 21: "DDR2", 22: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}
                mod_rows = []
                for m in data:
                    cap = fmt_bytes(m.get("Capacity", 0))
                    mem_type_code = m.get("SMBIOSMemoryType", 0)
                    mem_type = smbios_map.get(mem_type_code, f"Type {mem_type_code}")
                    mod_rows.append([
                        m.get("BankLabel", "N/A"), cap, mem_type,
                        f"{m.get('Speed', 'N/A')} MT/s",
                        m.get("Manufacturer", "N/A"), (m.get("PartNumber") or "N/A").strip(),
                    ])
                module_html = make_table(mod_rows,
                                         headers=["Slot", "Size", "Type", "Speed", "Manufacturer", "Part Number"])
                module_found = True
            except json.JSONDecodeError:
                pass

    elif platform.system() == "Darwin":
        output = run_cmd(["system_profiler", "SPMemoryDataType"])
        if output:
            module_html = f"<pre>{esc(output)}</pre>"
            module_found = True

    if not module_found:
        module_html = '<p class="note">Module details not available (may require sudo on Linux, or admin on Windows)</p>'

    parts.append(make_sub("Module Details", module_html))
    return "".join(parts)


def collect_gpu_info() -> str:
    parts = []
    gpu_found = False

    # ── NVIDIA via GPUtil ──
    if GPUtil:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                for i, gpu in enumerate(gpus):
                    mem_pct = gpu.memoryUtil * 100
                    load_pct = gpu.load * 100
                    mem_color = "var(--green)" if mem_pct < 60 else "var(--yellow)" if mem_pct < 85 else "var(--red)"
                    load_color = "var(--green)" if load_pct < 60 else "var(--yellow)" if load_pct < 85 else "var(--red)"

                    gpu_html = f'<div class="metric-row"><span class="metric-label">GPU Load</span>{progress_bar(load_pct, load_color)}</div>'
                    gpu_html += f'<div class="metric-row"><span class="metric-label">VRAM ({gpu.memoryUsed:.0f} / {gpu.memoryTotal:.0f} MB)</span>{progress_bar(mem_pct, mem_color)}</div>'
                    rows = [
                        ["GPU ID", str(gpu.id)],
                        ["Name", gpu.name],
                        ["Driver", gpu.driver],
                        ["Memory Total", f"{gpu.memoryTotal:.0f} MB"],
                        ["Memory Used", f"{gpu.memoryUsed:.0f} MB"],
                        ["Memory Free", f"{gpu.memoryFree:.0f} MB"],
                        ["Temperature", f"{gpu.temperature}°C"],
                    ]
                    gpu_html += make_kv_table(rows)
                    parts.append(make_sub(f"NVIDIA GPU {i}: {gpu.name}", gpu_html))
                gpu_found = True
        except Exception:
            pass

    # ── NVIDIA via nvidia-smi directly ──
    if not gpu_found and shutil.which("nvidia-smi"):
        output = run_cmd([
            "nvidia-smi",
            "--query-gpu=index,name,driver_version,temperature.gpu,utilization.gpu,"
            "utilization.memory,memory.total,memory.used,memory.free,clocks.gr,clocks.mem,"
            "clocks.max.gr,clocks.max.mem,power.draw,power.limit",
            "--format=csv,noheader,nounits"
        ])
        if output:
            for line in output.splitlines():
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 15:
                    rows = [
                        ["Index", p[0]], ["Name", p[1]], ["Driver", p[2]],
                        ["Temperature", f"{p[3]}°C"],
                        ["GPU Utilization", f"{p[4]}%"], ["Memory Utilization", f"{p[5]}%"],
                        ["Memory Total", f"{p[6]} MiB"], ["Memory Used", f"{p[7]} MiB"],
                        ["Memory Free", f"{p[8]} MiB"],
                        ["GPU Clock", f"{p[9]} MHz"], ["Memory Clock", f"{p[10]} MHz"],
                        ["Max GPU Clock", f"{p[11]} MHz"], ["Max Memory Clock", f"{p[12]} MHz"],
                        ["Power Draw", f"{p[13]} W"], ["Power Limit", f"{p[14]} W"],
                    ]
                    parts.append(make_sub(f"NVIDIA GPU {p[0]}: {p[1]}", make_kv_table(rows)))
            gpu_found = True

    # ── AMD via rocm-smi ──
    if shutil.which("rocm-smi"):
        output = run_cmd(["rocm-smi", "--showallinfo"])
        if output:
            parts.append(make_sub("AMD GPU (rocm-smi)", f"<pre>{esc(output[:4000])}</pre>"))
            gpu_found = True

    # ── lspci display adapters (Linux) ──
    if platform.system() == "Linux":
        output = run_cmd(["lspci"])
        if output:
            vga_lines = [l for l in output.splitlines() if "VGA" in l or "3D" in l or "Display" in l]
            if vga_lines:
                adapter_html = '<div class="adapter-list">' + "".join(
                    f'<div class="adapter-item">{esc(l)}</div>' for l in vga_lines
                ) + "</div>"
                parts.append(make_sub("Detected Display Adapters", adapter_html))
                if not gpu_found:
                    gpu_found = True

    # ── Windows fallback ──
    if platform.system() == "Windows" and not gpu_found:
        output = run_cmd(["powershell", "-Command",
                          "Get-CimInstance Win32_VideoController | "
                          "Select-Object Name,DriverVersion,AdapterRAM,VideoProcessor,"
                          "CurrentRefreshRate,Status | ConvertTo-Json"])
        if output:
            try:
                data = json.loads(output)
                if not isinstance(data, list):
                    data = [data]
                for gpu_data in data:
                    name = gpu_data.get("Name", "N/A")
                    adapter_ram = gpu_data.get("AdapterRAM")
                    rows = [
                        ["Name", name],
                        ["Video Processor", gpu_data.get("VideoProcessor", "N/A")],
                        ["Driver Version", gpu_data.get("DriverVersion", "N/A")],
                        ["Adapter RAM", fmt_bytes(adapter_ram) if adapter_ram else "N/A"],
                        ["Refresh Rate", f"{gpu_data.get('CurrentRefreshRate', 'N/A')} Hz"],
                        ["Status", gpu_data.get("Status", "N/A")],
                    ]
                    parts.append(make_sub(f"GPU: {name}", make_kv_table(rows)))
                gpu_found = True
            except json.JSONDecodeError:
                pass

    # ── macOS fallback ──
    if platform.system() == "Darwin" and not gpu_found:
        output = run_cmd(["system_profiler", "SPDisplaysDataType"])
        if output:
            parts.append(make_sub("GPU (system_profiler)", f"<pre>{esc(output)}</pre>"))
            gpu_found = True

    if not gpu_found:
        parts.append('<p class="note">No GPU information available (install GPUtil for NVIDIA, or ensure drivers are installed)</p>')

    return "".join(parts)


def collect_disk_info() -> str:
    parts = []

    if not psutil:
        return '<p class="note">psutil not installed — install for disk info</p>'

    # ── Partitions & Usage ──
    partitions = psutil.disk_partitions(all=False)
    if partitions:
        disk_html = ""
        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                used_pct = usage.percent
                color = "var(--green)" if used_pct < 60 else "var(--yellow)" if used_pct < 85 else "var(--red)"

                disk_html += f'<div class="iface-block">'
                disk_html += f'<div class="iface-header">'
                disk_html += f'<span class="iface-name">{esc(part.device)}</span>'
                disk_html += f'<span class="status-badge status-up">{esc(part.fstype)}</span>'
                disk_html += f'<span class="iface-meta">Mount: {esc(part.mountpoint)} · Opts: {esc(part.opts)}</span>'
                disk_html += f'</div>'

                disk_html += f'<div style="padding:0.8rem;">'
                disk_html += f'<div class="metric-row"><span class="metric-label">Usage ({fmt_bytes(usage.used)} / {fmt_bytes(usage.total)})</span>{progress_bar(used_pct, color)}</div>'

                rows = [
                    ["Total", fmt_bytes(usage.total)],
                    ["Used", fmt_bytes(usage.used)],
                    ["Free", fmt_bytes(usage.free)],
                    ["Filesystem", part.fstype or "N/A"],
                    ["Mount Point", part.mountpoint],
                    ["Mount Options", part.opts or "N/A"],
                ]
                disk_html += make_kv_table(rows)
                disk_html += f'</div></div>'

            except (PermissionError, OSError):
                disk_html += f'<div class="iface-block">'
                disk_html += f'<div class="iface-header">'
                disk_html += f'<span class="iface-name">{esc(part.device)}</span>'
                disk_html += f'<span class="status-badge status-down">NO ACCESS</span>'
                disk_html += f'<span class="iface-meta">Mount: {esc(part.mountpoint)}</span>'
                disk_html += f'</div></div>'

        parts.append(make_sub("Partitions &amp; Usage", disk_html))

    # ── Disk I/O Counters ──
    try:
        disk_io = psutil.disk_io_counters(perdisk=True)
        if disk_io:
            io_rows = []
            for disk_name, counters in sorted(disk_io.items()):
                io_rows.append([
                    disk_name,
                    str(counters.read_count),
                    str(counters.write_count),
                    fmt_bytes(counters.read_bytes),
                    fmt_bytes(counters.write_bytes),
                    f"{counters.read_time} ms",
                    f"{counters.write_time} ms",
                ])
            parts.append(make_sub("I/O Counters",
                                   make_table(io_rows, headers=["Disk", "Reads", "Writes",
                                                                "Read Bytes", "Written Bytes",
                                                                "Read Time", "Write Time"])))
    except Exception:
        pass

    # ── Physical Disk Details (platform-specific) ──
    phys_html = ""
    phys_found = False

    if platform.system() == "Linux":
        # Try lsblk for a nice overview
        output = run_cmd(["lsblk", "-o", "NAME,SIZE,TYPE,ROTA,MODEL,SERIAL,TRAN,REV,VENDOR",
                          "--nodeps", "--json"])
        if output:
            try:
                data = json.loads(output)
                devices = data.get("blockdevices", [])
                if devices:
                    phys_rows = []
                    for dev in devices:
                        dev_type = dev.get("type", "")
                        if dev_type not in ("disk",):
                            continue
                        rotational = "HDD" if dev.get("rota") else "SSD"
                        phys_rows.append([
                            dev.get("name", "N/A"),
                            dev.get("size", "N/A"),
                            rotational,
                            (dev.get("vendor") or "N/A").strip(),
                            (dev.get("model") or "N/A").strip(),
                            (dev.get("serial") or "N/A").strip(),
                            (dev.get("tran") or "N/A").upper(),
                        ])
                    if phys_rows:
                        phys_html = make_table(phys_rows,
                                               headers=["Device", "Size", "Type", "Vendor",
                                                        "Model", "Serial", "Transport"])
                        phys_found = True
            except json.JSONDecodeError:
                pass

        # Try smartctl for SMART data
        if shutil.which("smartctl"):
            smart_html = ""
            # Get list of disks
            for part in partitions:
                dev = part.device
                # Only check real block devices, not partitions like /dev/sda1 → /dev/sda
                if platform.system() == "Linux":
                    base_dev = re.sub(r'p?\d+$', '', dev)
                else:
                    base_dev = dev

                output = run_cmd(["sudo", "smartctl", "-i", "-H", "-A", base_dev])
                if not output:
                    output = run_cmd(["smartctl", "-i", "-H", "-A", base_dev])
                if output:
                    smart_html += f'<details class="smart-details"><summary>{esc(base_dev)}</summary>'
                    smart_html += f'<pre>{esc(output)}</pre></details>'

            if smart_html:
                phys_html += smart_html
                phys_found = True

    elif platform.system() == "Windows":
        output = run_cmd(["powershell", "-Command",
                          "Get-CimInstance Win32_DiskDrive | "
                          "Select-Object DeviceID,Model,Size,MediaType,InterfaceType,"
                          "SerialNumber,FirmwareRevision,Partitions,Status | ConvertTo-Json"])
        if output:
            try:
                data = json.loads(output)
                if not isinstance(data, list):
                    data = [data]
                phys_rows = []
                for disk in data:
                    size = fmt_bytes(disk.get("Size", 0)) if disk.get("Size") else "N/A"
                    phys_rows.append([
                        disk.get("DeviceID", "N/A"),
                        (disk.get("Model") or "N/A").strip(),
                        size,
                        disk.get("MediaType", "N/A"),
                        disk.get("InterfaceType", "N/A"),
                        (disk.get("SerialNumber") or "N/A").strip(),
                        str(disk.get("Partitions", "N/A")),
                        disk.get("Status", "N/A"),
                    ])
                if phys_rows:
                    phys_html = make_table(phys_rows,
                                           headers=["Device", "Model", "Size", "Media Type",
                                                    "Interface", "Serial", "Partitions", "Status"])
                    phys_found = True
            except json.JSONDecodeError:
                pass

    elif platform.system() == "Darwin":
        output = run_cmd(["system_profiler", "SPStorageDataType"])
        if output:
            phys_html = f"<pre>{esc(output)}</pre>"
            phys_found = True

    if phys_found:
        parts.append(make_sub("Physical Disks", phys_html))
    else:
        parts.append(make_sub("Physical Disks",
                              '<p class="note">Physical disk details not available (install smartmontools on Linux, or run as admin on Windows)</p>'))

    return "".join(parts)


def collect_network_info() -> str:
    parts = []

    # ── Basic ──
    rows = [["Hostname", socket.gethostname()]]
    try:
        rows.append(["FQDN", socket.getfqdn()])
    except Exception:
        pass
    try:
        rows.append(["Default IP", socket.gethostbyname(socket.gethostname())])
    except Exception:
        pass
    parts.append(make_sub("Host", make_kv_table(rows)))

    if not psutil:
        parts.append('<p class="note">psutil not installed — install for detailed network info</p>')
        return "".join(parts)

    # ── Interfaces ──
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    iface_html = ""

    for iface, addr_list in addrs.items():
        iface_stat = stats.get(iface)
        status = "UP" if iface_stat and iface_stat.isup else "DOWN"
        speed = f"{iface_stat.speed} Mbps" if iface_stat and iface_stat.speed else "N/A"
        mtu = str(iface_stat.mtu) if iface_stat else "N/A"
        duplex_map = {0: "N/A", 1: "Half", 2: "Full"}
        duplex = duplex_map.get(iface_stat.duplex, "N/A") if iface_stat else "N/A"

        status_class = "status-up" if status == "UP" else "status-down"
        iface_html += f'<div class="iface-block">'
        iface_html += f'<div class="iface-header"><span class="iface-name">{esc(iface)}</span>'
        iface_html += f'<span class="status-badge {status_class}">{status}</span>'
        iface_html += f'<span class="iface-meta">Speed: {esc(speed)} · MTU: {esc(mtu)} · Duplex: {esc(duplex)}</span></div>'

        addr_rows = []
        for addr in addr_list:
            family = str(addr.family).replace("AddressFamily.", "")
            addr_rows.append([family, addr.address or "N/A", addr.netmask or "N/A", addr.broadcast or "N/A"])
        iface_html += make_table(addr_rows, headers=["Family", "Address", "Netmask", "Broadcast"])
        iface_html += "</div>"

    parts.append(make_sub("Interfaces", iface_html))

    # ── I/O Stats ──
    io = psutil.net_io_counters(pernic=True)
    io_rows = []
    for iface, c in io.items():
        io_rows.append([iface, fmt_bytes(c.bytes_sent), fmt_bytes(c.bytes_recv),
                         str(c.packets_sent), str(c.packets_recv),
                         str(c.errin + c.errout), str(c.dropin + c.dropout)])
    parts.append(make_sub("I/O Statistics",
                           make_table(io_rows, headers=["Interface", "Sent", "Received",
                                                        "Pkts Sent", "Pkts Recv", "Errors", "Drops"])))

    # ── Connections Summary ──
    try:
        connections = psutil.net_connections(kind="inet")
        status_counts: dict[str, int] = {}
        for conn in connections:
            status_counts[conn.status] = status_counts.get(conn.status, 0) + 1
        if status_counts:
            conn_rows = [[s, str(n)] for s, n in sorted(status_counts.items())]
            parts.append(make_sub("Active Connections", make_table(conn_rows, headers=["Status", "Count"])))
    except psutil.AccessDenied:
        parts.append(make_sub("Active Connections",
                              '<p class="note">Access denied — run as admin/root for connection details</p>'))

    return "".join(parts)


# ──────────────────────────────────────────────
# HTML Template
# ──────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hardware Report &mdash; {hostname}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Outfit:wght@300;400;600;700&display=swap');

  :root {{
    --bg: #0b0e14;
    --surface: #12161f;
    --surface2: #181d29;
    --border: #1f2533;
    --border-glow: #2a3344;
    --text: #c5cdd9;
    --text-dim: #6b7a8d;
    --text-bright: #e8edf3;
    --accent: #58a6ff;
    --accent-dim: #1a3a5c;
    --green: #3fb950;
    --yellow: #d29922;
    --red: #f85149;
    --radius: 10px;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Outfit', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
    padding: 2rem;
  }}

  .container {{ max-width: 1100px; margin: 0 auto; }}

  /* Header */
  .report-header {{
    text-align: center;
    padding: 3rem 1rem 2rem;
    margin-bottom: 2rem;
    border-bottom: 1px solid var(--border);
    position: relative;
  }}
  .report-header::before {{
    content: '';
    position: absolute;
    top: 0; left: 50%;
    transform: translateX(-50%);
    width: 200px; height: 3px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    border-radius: 2px;
  }}
  .report-header h1 {{
    font-size: 2rem; font-weight: 700;
    color: var(--text-bright); letter-spacing: -0.02em;
  }}
  .report-header h1 span {{ color: var(--accent); }}
  .report-meta {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem; color: var(--text-dim); margin-top: 0.6rem;
  }}
  .report-meta span + span::before {{ content: '\\00b7'; margin: 0 0.6rem; }}

  /* Warning banner */
  .missing-banner {{
    background: var(--surface);
    border: 1px solid var(--yellow); border-left: 4px solid var(--yellow);
    border-radius: var(--radius); padding: 0.9rem 1.2rem;
    margin-bottom: 1.8rem; font-size: 0.88rem; color: var(--yellow);
  }}
  .missing-banner code {{
    font-family: 'JetBrains Mono', monospace;
    background: var(--surface2); padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.82rem;
  }}

  /* Nav */
  .nav {{ display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; margin-bottom: 2rem; }}
  .nav a {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    color: var(--text-dim); text-decoration: none;
    padding: 0.4rem 1rem; border: 1px solid var(--border); border-radius: 20px;
    transition: all 0.2s;
  }}
  .nav a:hover {{ color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }}

  /* Cards */
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); margin-bottom: 1.8rem; overflow: hidden;
    transition: border-color 0.3s;
  }}
  .card:hover {{ border-color: var(--border-glow); }}
  .card-header {{
    display: flex; align-items: center; gap: 0.7rem;
    padding: 1rem 1.4rem; border-bottom: 1px solid var(--border); background: var(--surface2);
  }}
  .card-icon {{ font-size: 1.3rem; }}
  .card-header h2 {{
    font-size: 1.05rem; font-weight: 600;
    color: var(--text-bright); letter-spacing: -0.01em;
  }}
  .card-body {{ padding: 1.2rem 1.4rem; }}

  /* Sub-sections */
  .sub-section {{ margin-bottom: 1.5rem; }}
  .sub-section:last-child {{ margin-bottom: 0; }}
  .sub-section h3 {{
    font-size: 0.82rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--accent);
    margin-bottom: 0.7rem; padding-bottom: 0.35rem; border-bottom: 1px dashed var(--border);
  }}

  /* Tables */
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  thead th {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
    text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--text-dim); text-align: left;
    padding: 0.5rem 0.8rem; border-bottom: 1px solid var(--border); background: var(--surface2);
  }}
  tbody td {{ padding: 0.45rem 0.8rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover td {{ background: rgba(88, 166, 255, 0.04); }}
  .kv td {{ padding: 0.35rem 0.8rem; }}
  .kv-key {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
    color: var(--text-dim); white-space: nowrap; width: 220px;
  }}
  .kv-val {{ color: var(--text-bright); word-break: break-all; }}

  /* Progress bars */
  .metric-row {{ display: flex; align-items: center; gap: 0.8rem; margin-bottom: 0.4rem; }}
  .metric-label {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    color: var(--text-dim); min-width: 140px; flex-shrink: 0;
  }}
  .progress-bar {{
    flex: 1; height: 20px; background: var(--surface2);
    border-radius: 4px; overflow: hidden; position: relative; border: 1px solid var(--border);
  }}
  .progress-fill {{ height: 100%; border-radius: 3px; transition: width 0.5s ease; }}
  .progress-label {{
    position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    color: var(--text-bright); text-shadow: 0 1px 3px rgba(0,0,0,0.6);
  }}

  /* Interface blocks */
  .iface-block {{ margin-bottom: 1rem; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }}
  .iface-block:last-child {{ margin-bottom: 0; }}
  .iface-header {{
    display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap;
    padding: 0.6rem 0.8rem; background: var(--surface2); border-bottom: 1px solid var(--border);
  }}
  .iface-name {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 0.88rem; color: var(--text-bright); }}
  .iface-meta {{ font-size: 0.78rem; color: var(--text-dim); }}
  .status-badge {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; font-weight: 600;
    padding: 0.15em 0.6em; border-radius: 10px; text-transform: uppercase; letter-spacing: 0.05em;
  }}
  .status-up {{ background: rgba(63,185,80,0.15); color: var(--green); border: 1px solid rgba(63,185,80,0.3); }}
  .status-down {{ background: rgba(248,81,73,0.15); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }}
  .adapter-item {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
    padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); color: var(--text);
  }}
  .adapter-item:last-child {{ border-bottom: none; }}

  /* Misc */
  .note {{ color: var(--text-dim); font-size: 0.85rem; font-style: italic; }}
  pre {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 6px; padding: 1rem; overflow-x: auto; color: var(--text);
  }}
  .smart-details {{
    margin-bottom: 0.6rem; border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
  }}
  .smart-details summary {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; font-weight: 600;
    padding: 0.6rem 0.8rem; cursor: pointer; background: var(--surface2);
    color: var(--text-bright); border-bottom: 1px solid var(--border);
    transition: background 0.2s;
  }}
  .smart-details summary:hover {{ background: var(--accent-dim); }}
  .smart-details[open] summary {{ color: var(--accent); }}
  .smart-details pre {{ margin: 0; border: none; border-radius: 0; }}
  .footer {{
    text-align: center; padding: 2rem 0; color: var(--text-dim);
    font-size: 0.78rem; border-top: 1px solid var(--border); margin-top: 1rem;
  }}

  @media (max-width: 700px) {{
    body {{ padding: 1rem; }}
    .kv-key {{ width: auto; min-width: 100px; }}
    .metric-row {{ flex-direction: column; gap: 0.3rem; }}
    .metric-label {{ min-width: unset; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="report-header">
    <h1>System <span>Hardware</span> Report</h1>
    <div class="report-meta">
      <span>{hostname}</span>
      <span>{timestamp}</span>
      <span>{os_name}</span>
    </div>
  </div>

  {missing_banner}

  <nav class="nav">
    <a href="#system">System</a>
    <a href="#cpu">CPU</a>
    <a href="#memory">Memory</a>
    <a href="#gpu">GPU</a>
    <a href="#disks">Disks</a>
    <a href="#network">Network</a>
  </nav>

  {content}

  <div class="footer">
    Generated by hardware_info.py &middot; {timestamp}
  </div>
</div>
</body>
</html>
"""


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a hardware info HTML report.")
    parser.add_argument("-o", "--output", default="hardware_report",
                        help="Output filename (without extension). Default: hardware_report")
    parser.add_argument("--no-open", action="store_true",
                        help="Don't auto-open the report in a browser.")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hostname = socket.gethostname()
    uname = platform.uname()
    os_name = f"{uname.system} {uname.release}"

    print(f"Collecting hardware information...")

    # Check missing packages
    missing = []
    if not psutil:
        missing.append("psutil")
    if not cpuinfo:
        missing.append("py-cpuinfo")
    if not GPUtil:
        missing.append("GPUtil")

    missing_banner = ""
    if missing:
        pkgs = ", ".join(f"<code>{p}</code>" for p in missing)
        install_cmd = " ".join(missing)
        missing_banner = (
            f'<div class="missing-banner">\u26a0 Optional packages not installed: {pkgs}. '
            f'Install with: <code>pip install {install_cmd}</code></div>'
        )

    # Collect all sections
    print("  [1/6] System overview...")
    content = make_card("System Overview", "\U0001f5a5\ufe0f", collect_system_summary(), "system")
    print("  [2/6] CPU info...")
    content += make_card("CPU", "\u26a1", collect_cpu_info(), "cpu")
    print("  [3/6] Memory info...")
    content += make_card("Memory", "\U0001f9e0", collect_memory_info(), "memory")
    print("  [4/6] GPU info...")
    content += make_card("GPU", "\U0001f3ae", collect_gpu_info(), "gpu")
    print("  [5/6] Disk info...")
    content += make_card("Disks", "\U0001f4be", collect_disk_info(), "disks")
    print("  [6/6] Network info...")
    content += make_card("Network", "\U0001f310", collect_network_info(), "network")

    # Render HTML
    html_output = HTML_TEMPLATE.format(
        hostname=esc(hostname),
        timestamp=esc(timestamp),
        os_name=esc(os_name),
        missing_banner=missing_banner,
        content=content,
    )

    # Write report
    filename = f"{args.output}.html"
    output_path = os.path.join(os.path.expanduser("~"), filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_output)

    print(f"\n\u2705 Report saved to: {output_path}")

    if not args.no_open:
        try:
            webbrowser.open(f"file://{os.path.abspath(output_path)}")
            print("   Opened in default browser.")
        except Exception:
            print("   Open the file manually in your browser.")


if __name__ == "__main__":
    main()
