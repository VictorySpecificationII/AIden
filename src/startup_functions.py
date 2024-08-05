"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- print_banner(): Prints a welcome banner at startup.
"""
import lib_copilot_telemetry
# Initialize LoggerProvider and LoggingHandler
logger_provider = lib_copilot_telemetry.LoggerProvider(
    resource=lib_copilot_telemetry.Resource.create(
        {
            "service.name": "startup",
            "service.instance.id": "instance-00",
        }
    ),
)
lib_copilot_telemetry.set_logger_provider(logger_provider)

exporter = lib_copilot_telemetry.OTLPLogExporter(insecure=True)
logger_provider.add_log_record_processor(lib_copilot_telemetry.BatchLogRecordProcessor(exporter))
handler = lib_copilot_telemetry.LoggingHandler(level=lib_copilot_telemetry.logging.NOTSET, logger_provider=logger_provider)

# Set minimum log level and attach OTLP handler to root logger
lib_copilot_telemetry.logging.basicConfig(level=lib_copilot_telemetry.logging.INFO)
lib_copilot_telemetry.logging.getLogger().addHandler(handler)

# Create different namespaced loggers
logger1 = lib_copilot_telemetry.logging.getLogger("aiden.startup")

# Initialize tracer
tracer = lib_copilot_telemetry.trace.get_tracer(__name__)

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
        logger1.info("Banner displayed.")