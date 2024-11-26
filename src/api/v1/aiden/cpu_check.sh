#!/bin/bash

# Function to collect CPU information
collect_cpu_info() {
    local cpu_id="$1"
    local cpu_path="/sys/devices/system/cpu/$cpu_id"

    echo "CPU Information for ID: $cpu_id"
    echo "-----------------------------------"

    # Vendor and model information from /proc/cpuinfo
    local cpu_info=$(grep -m 1 -A 10 "^processor.*$cpu_id" /proc/cpuinfo)
    echo "$cpu_info"

    # Additional details from /sys/devices/system/cpu
    if [ -d "$cpu_path" ]; then
        echo "Additional Information from /sys/devices/system/cpu:"
        echo "  CPU MHz (current): $(cat "$cpu_path/cpufreq/cpuinfo_cur_freq" 2>/dev/null || echo 'N/A')"
        echo "  CPU MHz (min): $(cat "$cpu_path/cpufreq/cpuinfo_min_freq" 2>/dev/null || echo 'N/A')"
        echo "  CPU MHz (max): $(cat "$cpu_path/cpufreq/cpuinfo_max_freq" 2>/dev/null || echo 'N/A')"
        echo "  Scaling Driver: $(cat "$cpu_path/cpufreq/scaling_driver" 2>/dev/null || echo 'N/A')"
        echo "  Scaling Governor: $(cat "$cpu_path/cpufreq/scaling_governor" 2>/dev/null || echo 'N/A')"
        echo "  Online: $(cat "$cpu_path/online" 2>/dev/null || echo 'N/A')"
        echo "  Topology (physical ID): $(cat "$cpu_path/topology/physical_package_id" 2>/dev/null || echo 'N/A')"
        echo "  Topology (core ID): $(cat "$cpu_path/topology/core_id" 2>/dev/null || echo 'N/A')"
    else
        echo "No /sys information available for CPU $cpu_id."
    fi
    echo ""
}

# Main script starts here
echo "Searching for CPUs..."
cpu_ids=$(ls /sys/devices/system/cpu | grep -E '^cpu[0-9]+$')

# Check if any CPUs were found
if [ -z "$cpu_ids" ]; then
    echo "No CPUs found."
    exit 1
fi

# Loop through each CPU and collect information
for cpu_id in $cpu_ids; do
    collect_cpu_info "$cpu_id"
done

# Fetch system-wide information using lscpu
echo "Fetching system-wide CPU details using lscpu..."
lscpu
echo ""
echo "Finished collecting CPU information."