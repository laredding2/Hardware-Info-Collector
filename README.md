# Hardware Info

A cross-platform Python script that collects comprehensive hardware information from your system and generates a polished, dark-themed HTML report.

## Features

### CPU
- Brand, vendor, architecture, and family/model/stepping
- Base and current clock frequencies
- L2/L3 cache sizes and notable instruction set extensions (AVX, AES, etc.)
- Physical and logical core counts
- Per-core usage with color-coded progress bars
- Temperature readings (Linux via `lm-sensors` / `psutil`, Windows via WMI)

### Memory
- Total, available, used, cached, and buffered RAM with usage bar
- Swap usage and capacity
- Per-module details: slot, size, type (DDR4/DDR5/etc.), speed, manufacturer, and part number
  - Linux: via `dmidecode` (may require `sudo`)
  - Windows: via `Win32_PhysicalMemory`
  - macOS: via `system_profiler`

### GPU
- **NVIDIA**: name, driver, VRAM usage, GPU load, temperature, clock speeds, and power draw (via `GPUtil` or `nvidia-smi`)
- **AMD**: full info via `rocm-smi`
- **Intel / Other**: detected display adapters via `lspci` (Linux), `Win32_VideoController` (Windows), or `system_profiler` (macOS)

### Disks
- All mounted partitions with filesystem type, mount point, and mount options
- Per-partition usage with color-coded progress bars
- Per-disk I/O counters (reads, writes, bytes, timing)
- Physical disk details: model, size, SSD vs HDD, vendor, serial, and transport type
  - Linux: via `lsblk` (JSON)
  - Windows: via `Win32_DiskDrive`
  - macOS: via `system_profiler`
- SMART health data in collapsible sections (requires `smartmontools`)

### Network
- Hostname, FQDN, and default IP
- All network interfaces with status badges (UP/DOWN), link speed, MTU, and duplex mode
- Per-interface addresses: IPv4, IPv6, and MAC with netmask and broadcast
- Per-interface I/O statistics (bytes, packets, errors, drops)
- Active connection summary by status

## Requirements

- **Python 3.10+**
- Required: [`psutil`](https://pypi.org/project/psutil/)
- Optional (but recommended):
  - [`py-cpuinfo`](https://pypi.org/project/py-cpuinfo/) — detailed CPU identification
  - [`GPUtil`](https://pypi.org/project/GPUtil/) — NVIDIA GPU info

```bash
pip install psutil py-cpuinfo GPUtil
```

### System Tools (Optional)

| Tool             | Platform | What it enables                        |
|------------------|----------|----------------------------------------|
| `lm-sensors`     | Linux    | CPU temperature readings               |
| `dmidecode`      | Linux    | RAM module type, speed, manufacturer   |
| `smartmontools`  | Linux    | SMART disk health data                 |
| `lsblk`          | Linux    | Physical disk model, serial, transport |
| `nvidia-smi`     | All      | NVIDIA GPU details (fallback)          |
| `rocm-smi`       | Linux    | AMD GPU details                        |

## Usage

```bash
# Default — saves to ~/hardware_report.html and opens in browser
python hardware_info.py

# Custom output filename
python hardware_info.py -o my_system_report

# Don't auto-open the browser
python hardware_info.py --no-open
```

### Command-Line Options

| Flag              | Description                                      | Default            |
|-------------------|--------------------------------------------------|--------------------|
| `-o`, `--output`  | Output filename (without `.html` extension)      | `hardware_report`  |
| `--no-open`       | Skip auto-opening the report in the browser      | Off                |

## Output

The script generates a single self-contained HTML file with:

- Dark theme with responsive layout
- Anchor-link navigation bar for quick jumping between sections
- Color-coded progress bars (green → yellow → red) for usage metrics
- Status badges for network interfaces and disk filesystems
- Collapsible SMART data sections per drive
- Warning banner listing any missing optional packages

The report requires no external assets and can be opened in any modern browser.

## Platform Support

| Feature              | Linux | Windows | macOS |
|----------------------|:-----:|:-------:|:-----:|
| CPU specs & usage    |   ✅  |   ✅    |  ✅   |
| CPU temperature      |   ✅  |   ⚠️    |  ❌   |
| RAM usage            |   ✅  |   ✅    |  ✅   |
| RAM module details   |   ✅  |   ✅    |  ✅   |
| NVIDIA GPU           |   ✅  |   ✅    |  ✅   |
| AMD GPU              |   ✅  |   ❌    |  ❌   |
| Disk partitions      |   ✅  |   ✅    |  ✅   |
| Disk I/O counters    |   ✅  |   ✅    |  ✅   |
| Physical disk info   |   ✅  |   ✅    |  ✅   |
| SMART data           |   ✅  |   ⚠️    |  ⚠️   |
| Network interfaces   |   ✅  |   ✅    |  ✅   |

> ✅ = Full support · ⚠️ = Partial (may require admin/drivers) · ❌ = Not available

## Notes

- Some features require **root/admin** privileges (CPU temperature on Windows, `dmidecode` and `smartctl` on Linux).
- The script gracefully degrades — missing packages or insufficient permissions display a note in the report instead of crashing.
- Google Fonts (`Outfit` and `JetBrains Mono`) are loaded from CDN. The report still renders fine without internet, just with fallback fonts.

## License

This project is licensed under the [MIT License](LICENSE.md).
