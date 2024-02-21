# AIden

The world's best co-pilot.

# Directory Structure

 - src/ contains Python source code organized into modules and packages.
 - tests/ contains the test suite, organized into subdirectories corresponding to the modules they test.
 - docs/ contains documentation files.
 - conf/ contains configuration files.
 - data/ contains any data files and datasets used by the project.
 - requirements.txt lists project dependencies.

# Components

 - SignalSculptor - Top Level Design for the input system to AIden
  - Sensory Suite - Visual, Audio, Thermal
  - Input Suite - Text, Voice
 - MindForge - AIden's Personality Engine(LLM) and toolset
 - EchoSphere - Top Level Design for the output system to AIden (API Execution, Textual, Voice)
 - CyberGuardian - Top Level Design for AIden's security system
 - CodeCraft - Top Level Design for CI/CD
 - CaringCustodian - Top Level Design for SRE
