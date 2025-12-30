# Pi Zero 2W Performance Optimizations

Optimizations for running Dune Weaver on resource-constrained Pi Zero 2W (512MB RAM, quad-core ARM @ 1GHz).

## Quick Wins (Already Applied)

### 1. Docker Resource Limits
✅ **Applied in `docker-compose.yml`:**
- Memory limit: 384MB (leaves 128MB for system)
- Swap limit: 512MB total
- CPU limit: 3 cores (leaves 1 for system)

## System-Level Optimizations

### 2. Reduce Logging Verbosity
Set log level to WARNING (reduces I/O and CPU):

```bash
# Edit .env file
echo "LOG_LEVEL=WARNING" >> .env

# Then restart
docker compose down && docker compose up -d
```

**Options:** `DEBUG` (most verbose) → `INFO` → `WARNING` → `ERROR` (least verbose)

### 3. Increase Swap (If Needed)
Check current swap:
```bash
free -h
```

If swap is small (<512MB), increase it:
```bash
# Stop swap
sudo dswapoff -a

# Increase swap file (1GB recommended)
sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
```

### 4. Disable Unnecessary Services
```bash
# Check what's running
systemctl list-units --type=service --state=running

# Disable unnecessary services (examples):
sudo systemctl disable bluetooth.service
sudo systemctl disable hciuart.service
sudo systemctl disable avahi-daemon.service  # If not using .local hostname

# Reboot
sudo reboot
```

### 5. Use Faster SD Card
- **Class 10** or **A1/A2** rated SD cards significantly improve I/O
- Consider USB boot if supported (faster than SD)

### 6. Reduce GPU Memory
Edit `/boot/config.txt`:
```bash
# Reduce GPU memory (headless system doesn't need much)
gpu_mem=16

# Then reboot
sudo reboot
```

## Application-Level Optimizations

### 7. Limit Pattern Cache Size
Reduce cached preview images to save memory:

```bash
# Find large caches
du -h patterns/cached_images/

# Delete old/unused pattern previews
rm patterns/cached_images/old_pattern_*.webp

# Consider reducing preview resolution in future
```

### 8. Reduce WebSocket Update Frequency (Optional)
**Current:** Status updates every 1 second (already reasonable)

**If needed**, edit `modules/core/pattern_manager.py` line 1224:
```python
await asyncio.sleep(2)  # Change from 1 to 2 seconds
```

### 9. Optimize Docker Image (Advanced)
Use alpine-based image instead of debian:

Edit `Dockerfile` (requires rebuild):
```dockerfile
FROM python:3.11-alpine  # Instead of python:3.11-slim

# Install runtime dependencies
RUN apk add --no-cache \
    libstdc++ \
    libgcc
```

**Trade-off:** Smaller image (~100MB savings) but longer build time.

## Monitoring & Troubleshooting

### Check Resource Usage
```bash
# Overall system
htop

# Docker container specifically
docker stats dune-weaver

# Memory pressure
free -h
vmstat 1

# I/O wait
iostat -x 2
```

### Common Lockup Causes

1. **Out of Memory (OOM)**
   - Symptom: Container restarts, `dmesg` shows OOM killer
   - Fix: Increase swap or reduce mem_limit slightly

2. **CPU Saturation**
   - Symptom: High load average (>4 on 4-core system)
   - Fix: Reduce WebSocket update frequency

3. **Slow SD Card I/O**
   - Symptom: High `iowait` in `top/htop`
   - Fix: Use faster SD card or USB boot

4. **Too Many Docker Logs**
   - Symptom: `/var/lib/docker` fills up
   - Fix: Set log rotation in docker-compose.yml

### Log Rotation (Prevent Disk Fills)
Add to `docker-compose.yml`:
```yaml
services:
  dune-weaver:
    # ... existing config ...
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Performance Expectations

### With Optimizations:
- **Idle RAM usage:** ~180-220MB
- **Active RAM usage:** ~280-320MB (pattern execution)
- **CPU usage:** 20-40% idle, 60-80% during pattern execution
- **Web UI response:** <1s for most actions
- **Pattern upload:** 5-15s for large files

### Signs of Resource Exhaustion:
- Web UI freezes/timeouts
- Slow page loads (>5s)
- Container restarts
- SSH disconnects
- Kernel OOM messages in `dmesg`

## Recommended Configuration

**Best balance of performance and stability:**

```bash
# .env
LOG_LEVEL=WARNING  # Reduce logging overhead

# System
- 1GB swap file
- GPU memory = 16MB
- Class 10/A1 SD card
- Disable unused services (bluetooth, avahi)

# Docker
- mem_limit: 384m
- memswap_limit: 512m
- cpus: 3.0
- Log rotation enabled
```

## Apply Changes
```bash
cd /path/to/dune-weaver

# Pull latest code (includes docker-compose.yml updates)
git pull

# Apply .env changes
echo "LOG_LEVEL=WARNING" >> .env

# Rebuild and restart
docker compose down
docker compose up -d

# Monitor
docker logs -f dune-weaver
```

---

**Note:** These optimizations prioritize stability over peak performance. The Pi Zero 2W can run Dune Weaver smoothly with proper tuning!
