"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- print_banner(): Prints a welcome banner at startup.
"""

from lib_copilot_telemetry import OpenTelemetryInstrumentor

# Initialize the OpenTelemetryInstrumentor
instrumentor = OpenTelemetryInstrumentor(svc_name="startup", instance_id="instance-00")

# Get the logger and tracer
logger = instrumentor.get_logger(logging_area="startup")
tracer = instrumentor.get_tracer()

def print_banner():
    """
    Prints a banner at startup.
    """
    with tracer.start_as_current_span("print_welcome_banner"):
        ascii_art = """
            _    ___    _            
           / \  |_ _|__| | ___ _ __  
          / _ \  | |/ _` |/ _ \ '_ \ 
         / ___ \ | | (_| |  __/ | | |
        /_/   \_\___\__,_|\___|_| |_|
        
    Artificial Intelligence Co-Pilot
        """
        print(ascii_art)
        logger.info("Banner displayed.")
