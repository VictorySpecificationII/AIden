"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- print_banner(): Prints a welcome banner at startup.
"""
import lib_copilot_telemetry

logger, tracer = lib_copilot_telemetry.instrumentator("startup", "instance-00", "startup")

def print_banner():
    with tracer.start_as_current_span("print_welcome_banner"):
        '''
        Prints a banner at startup.
        '''
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