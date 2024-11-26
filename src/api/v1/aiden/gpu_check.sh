#!/bin/bash

# Function to check if a GPU is integrated or discrete
is_discrete_gpu() {
    local vendor_id="$1"
    vendor_id=${vendor_id#0x}
    
    echo "Checking vendor ID: $vendor_id"  # Debug statement
    case "$vendor_id" in
        "10de" | "1002") # Nvidia and AMD/ATI vendors
            return 0 # Discrete
            ;;
        *)
            return 1 # Integrated or unknown
            ;;
    esac
}

# Function to collect GPU information
collect_gpu_info() {
    local gpu_id="$1"
    local device_path="/sys/bus/pci/devices/$gpu_id"

    if [ ! -d "$device_path" ]; then
        echo "Device path $device_path does not exist."
        return
    fi

    echo "GPU Information for ID: $gpu_id"
    echo "-----------------------------------"
    local vendor=$(cat "$device_path/vendor" 2>/dev/null || echo 'N/A')
    local device=$(cat "$device_path/device" 2>/dev/null || echo 'N/A')

    # Determine if the GPU is discrete
    if is_discrete_gpu "$vendor"; then
        echo "  Vendor ID: $vendor"
        echo "  Device ID: $device"
        echo "  Subsystem Vendor ID: $(cat "$device_path/subsystem_vendor" 2>/dev/null || echo 'N/A')"
        echo "  Subsystem Device ID: $(cat "$device_path/subsystem_device" 2>/dev/null || echo 'N/A')"

        # Locate the DRM device path dynamically
        local drm_device_path=""
        for drm_device in /sys/class/drm/card*; do
            # Resolve the 'device' symlink and compare it with the PCI device path
            if [ "$(readlink -f "$drm_device/device")" == "$device_path" ]; then
                drm_device_path="$drm_device"
                break
            fi
        done

        if [ -n "$drm_device_path" ]; then
            echo "  DRM Path: $drm_device_path"
            echo "  Additional Information from /sys/class/drm:"
            echo "    Max Frequency: $(cat "$drm_device_path/gt_max_freq_mhz" 2>/dev/null || echo 'N/A') MHz"
            echo "    Current Frequency: $(cat "$drm_device_path/gt_cur_freq_mhz" 2>/dev/null || echo 'N/A') MHz"
            echo "    Min Frequency: $(cat "$drm_device_path/gt_min_freq_mhz" 2>/dev/null || echo 'N/A') MHz"
        else
            echo "  No DRM information found for device $gpu_id."
        fi

        # Loop through each file in the device path and print relevant info
        echo "  Additional Information from PCI device path:"
        for file in "$device_path"/*; do
            if [[ -f "$file" ]]; then
                filename=$(basename "$file")
                value=$(cat "$file" 2>/dev/null || echo 'N/A')
                echo "    $filename: $value"
            fi
        done
        echo ""
    else
        echo "Integrated GPU found (not reporting): $gpu_id"
    fi

    # Fetch additional information using lspci
    echo "Fetching additional details using lspci..."
    sudo lspci -v -s "$gpu_id" | grep -E 'VGA|Memory|Flags|Kernel modules'
    echo ""
}

# Find all VGA-compatible GPU IDs
echo "Searching for VGA-compatible GPU(s)..."
gpu_ids=$(lspci | grep -i "vga" | awk '{ print $1 }')

# Check if any GPUs were found
if [ -z "$gpu_ids" ]; then
    echo "No GPU found."
    exit 1
fi

# Loop through each GPU ID and collect information
for gpu_id in $gpu_ids; do
    # The GPU ID from lspci is in the format "00:01.0", we need to prefix with "0000:"
    collect_gpu_info "0000:$gpu_id"
done

echo "Finished collecting GPU information."
