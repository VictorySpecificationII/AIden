import subprocess
import platform

def print_banner():
    """
    Prints a banner at startup.
    """
    ascii_art = """
            _    ___    _            
           / \  |_ _|__| | ___ _ __  
          / _ \  | |/ _` |/ _ \ '_ \ 
         / ___ \ | | (_| |  __/ | | |
        /_/   \_\___\__,_|\___|_| |_|
        
    Artificial Intelligence Co-Pilot
        """
    print(ascii_art)

def run_command(command):
    """Run a shell command and return the output."""
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

def detect_environment():
    """Detects the current environment: container, VM, or native."""
    if platform.system() == "Linux":
        if run_command("cat /proc/cpuinfo | grep -i 'hypervisor'"):
            return "virtual machine"
        elif run_command("cat /proc/1/cgroup | grep -i 'docker'"):
            return "container"
    return "native"

def get_cpu_info():
    """Get detailed CPU information and format it."""
    cpu_info = run_command("lscpu")
    return format_output(cpu_info)

def get_gpu_info():
    """Get detailed GPU information and format it."""
    gpu_info = run_command("lshw -C display")
    return format_output(gpu_info)

def format_output(raw_output):
    """Format raw command output into a structured format."""
    if not raw_output:
        return "No information available."
    formatted_lines = []
    for line in raw_output.splitlines():
        formatted_lines.append(line.strip())
    return "\n".join(formatted_lines)

def detect_resources():
    """Detects CPU, GPU, network, and disk information."""
    resources = {
        "cpu_info": get_cpu_info(),
        "gpu_info": get_gpu_info()
    }
    return resources

def is_nvidia_smi_installed():
    """Check if `nvidia-smi` is installed."""
    return run_command("which nvidia-smi") is not None

def decide_model(resources):
    """Decides which model to run based on the detected resources."""
    cpu_info = resources.get("cpu_info")
    
    # Example edge device criteria
    edge_device_criteria = {
        "max_cores": 2,          # Max cores for an edge device
        "max_clock_speed": 2000, # Max clock speed in MHz (2.0 GHz)
        "acceptable_architectures": ["arm", "x86_64"] # Include ARM architectures
    }
    
    # If `nvidia-smi` isn't installed, use the edge model
    if not is_nvidia_smi_installed():
        return "edge_device_model"  # Return specific model for edge devices

    # Parse the CPU information to extract necessary values
    if cpu_info:
        # Extract relevant lines from the CPU info
        lines = cpu_info.splitlines()
        cores = None
        clock_speed = None
        architecture = None
        
        for line in lines:
            if "CPU(s):" in line:
                # Extract the core range and calculate the number of cores
                core_range = line.split(":")[1].strip()
                if '-' in core_range:
                    # Calculate the number of cores from the range (e.g., '0-3' -> 4 cores)
                    start, end = map(int, core_range.split('-'))
                    cores = end - start + 1  # Total cores in the range
                else:
                    cores = int(core_range)  # Single core value
            if "CPU max MHz:" in line:
                clock_speed = float(line.split(":")[1].strip().replace(",", "."))  # Convert to MHz
            if "Architecture:" in line:
                architecture = line.split(":")[1].strip().lower()
        
        # Determine if the device is an edge device
        if (cores <= edge_device_criteria["max_cores"] and
            clock_speed <= edge_device_criteria["max_clock_speed"] and
            architecture in edge_device_criteria["acceptable_architectures"]):
            return "edge_device_model"  # Return specific model for edge devices

    # Default model for non-edge devices
    return "default_model"

def boot_checks():
    environment = detect_environment()
    resources = detect_resources()
    model = decide_model(resources)

    print(f"Environment: {environment}\n")
    print("Resources:")
    for key, value in resources.items():
        print(f"{key.replace('_', ' ').title()}:\n{value}\n")
    print(f"Model selected: {model}")

    return model