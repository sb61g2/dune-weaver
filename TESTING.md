# Testing Upstream vs Fork

This document describes how to test the original upstream Dune Weaver container from [tuanchris/dune-weaver](https://github.com/tuanchris/dune-weaver) while retaining the ability to switch back to this fork.

## Prerequisites

- SSH access to your Raspberry Pi
- Docker installed and running
- Your fork's container already built or available

## Shared Data

Both containers will share the same Docker volumes, so your patterns and state data are preserved:
- **Pattern files**: `dune-weaver-data` volume
- **State data**: `dune-weaver-state` volume
- **Web interface**: `http://[raspberry-pi-ip]:8080`

## Switch to Original (Upstream) Container

Run these commands via SSH to test the original container:

```bash
# 1. Stop and remove your current container
docker stop dune-weaver
docker rm dune-weaver

# 2. Clone the upstream repository (if not already cloned)
cd ~
git clone https://github.com/tuanchris/dune-weaver.git dune-weaver-upstream
cd dune-weaver-upstream

# 3. Build the upstream container
docker build -t dune-weaver-upstream:latest .

# 4. Run the upstream container
docker run -d \
  --name dune-weaver-original \
  --restart unless-stopped \
  -p 8080:8080 \
  -v dune-weaver-data:/app/patterns \
  -v dune-weaver-state:/app/state \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  --privileged \
  dune-weaver-upstream:latest
```

**Notes**:
- Adjust `--device=/dev/ttyUSB0` if your serial device path is different
- The upstream repository doesn't publish pre-built Docker images, so you must build from source
- This creates a separate directory (`~/dune-weaver-upstream`) so it doesn't interfere with your fork

## Switch Back to This Fork

To return to your customized fork:

```bash
# 1. Stop and remove the upstream container
docker stop dune-weaver-original
docker rm dune-weaver-original

# 2. Restart your fork's container
docker run -d \
  --name dune-weaver \
  --restart unless-stopped \
  -p 8080:8080 \
  -v dune-weaver-data:/app/patterns \
  -v dune-weaver-state:/app/state \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  --privileged \
  dune-weaver:latest
```

### If You Need to Rebuild

If you need to rebuild your fork's container from updated code:

```bash
# Navigate to your local repository on the Pi
cd /path/to/dune-weaver

# Build the container
docker build -t dune-weaver:latest .

# Run the container
docker run -d \
  --name dune-weaver \
  --restart unless-stopped \
  -p 8080:8080 \
  -v dune-weaver-data:/app/patterns \
  -v dune-weaver-state:/app/state \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  --privileged \
  dune-weaver:latest
```

## Monitoring & Troubleshooting

### Check Running Containers

```bash
# List running containers
docker ps

# List all containers (including stopped)
docker ps -a
```

### View Container Logs

```bash
# View upstream container logs
docker logs dune-weaver-original

# View your fork's logs
docker logs dune-weaver

# Follow logs in real-time
docker logs -f dune-weaver
```

### Container Status

```bash
# Check container resource usage
docker stats

# Inspect container configuration
docker inspect dune-weaver
```

## Key Differences Between Versions

Your fork includes these enhancements not present in the upstream version:

### RGBCCT LED Support
- Dual WS2811 chip configuration for 5-channel RGBCCT LED strips
- Independent RGB and White channel brightness controls
- Color temperature control (2700K-6500K)
- Equal-width two-column layout for RGBCCT controls
- Amber/gray power button states for better visual feedback

### UI Improvements
- Fixed LED page initialization (LEDs stay off when loading page)
- Effect colors sync with selected palette
- Improved power button state management
- Better visual hierarchy with updated button colors

### Additional Features
See `RGBCCT_SETUP.md` for detailed RGBCCT LED configuration.

## Cleanup

After testing the upstream version, you can remove it to free up space:

```bash
# Remove the upstream container
docker stop dune-weaver-original
docker rm dune-weaver-original

# Remove the upstream Docker image
docker rmi dune-weaver-upstream:latest

# Optionally remove the upstream repository directory
rm -rf ~/dune-weaver-upstream
```

## Reverting Changes

If you encounter issues with your fork and need to troubleshoot:

1. **Test with upstream**: Switch to the upstream container to isolate whether the issue is hardware-related or code-related
2. **Compare behavior**: Note differences in LED control, UI responsiveness, and functionality
3. **Report issues**: If upstream works but fork doesn't, the issue is in the fork's changes
4. **Clean state**: If needed, you can remove and recreate volumes (⚠️ **this will delete your patterns and settings**):

```bash
# ⚠️ WARNING: This deletes all your data!
docker volume rm dune-weaver-data
docker volume rm dune-weaver-state
```

## Notes

- Both containers use the same port (8080), so only one can run at a time
- Serial device path may vary (`/dev/ttyUSB0`, `/dev/ttyACM0`, etc.)
- GPIO access requires `--privileged` flag for the container
- Pattern files are stored in a named Docker volume for persistence
- Your local code changes in `/Users/sb61g2/Documents/Projects/Sand Table/dune-weaver` are independent of Docker containers
