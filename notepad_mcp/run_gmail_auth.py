"""
Gmail Authentication Helper Script
----------------------------------
This script is designed to be run manually from the command line
to generate or refresh the Gmail API token (`token.json`).

Run this script directly if you need to re-authenticate the application,
for example, after deleting the token file or if the permissions have changed.

Command to run from the project root (`mcp_Client`):
python notepad_mcp/run_gmail_auth.py
"""

import os
import sys
import logging
import importlib.util

# Fix module import path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def import_module_from_file(module_name, file_path):
    """Safely import a module from a file path."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            raise ImportError(f"Could not load spec for module {module_name} from {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logging.error(f"Error importing {module_name} from {file_path}: {e}")
        raise

try:
    # Import the config module first
    config_module = import_module_from_file('config', os.path.join(script_dir, 'config.py'))
    GMAIL_CONFIG = config_module.GMAIL_CONFIG
    
    # Then import the gmail service
    gmail_service_module = import_module_from_file('gmail_service', os.path.join(script_dir, 'services', 'gmail_service.py'))
    GmailService = gmail_service_module.GmailService
    
    logging.info("Successfully imported required modules")
except ImportError as e:
    logging.error(f"Import error: {e}")
    print(f"Error: Failed to import necessary modules.")
    print(f"Please check that you have:")
    print(f"1. Run this script from the project root directory (mcp_Client)")
    print(f"2. Installed all required packages (pip install -r requirements.txt)")
    print(f"3. Set up your .env file with necessary configurations")
    print(f"\nDetailed error: {e}")
    sys.exit(1)

def main():
    """
    Initializes the GmailService to trigger the OAuth2 flow and generate a token.
    """
    token_path = GMAIL_CONFIG.get('token_path', 'token.json')
    
    print("="*60)
    print("Gmail Authentication Helper")
    print("="*60)
    print("This script will guide you through the Google authentication process.")
    print("Your web browser should open shortly.")
    print("If it doesn't, please copy the URL printed in the console into your browser.")
    print(f"The new token will be saved to: {os.path.abspath(token_path)}")
    print("-"*60)

    try:
        # Temporarily override server_mode to force interactive authentication
        original_server_mode = GMAIL_CONFIG.get('server_mode', False)
        GMAIL_CONFIG['server_mode'] = False
        
        # This is the line that will trigger the authentication flow
        # if token.json is missing or invalid.
        service = GmailService()
        service._initialize_service() # Manually trigger the initialization

        # Restore original server_mode
        GMAIL_CONFIG['server_mode'] = original_server_mode

        if service and service.service:
            print("\n✅ Authentication successful!")
            print("Token file has been created/updated successfully.")
            # You can optionally add a check here to see if the service is usable
            profile = service.service.users().getProfile(userId='me').execute()
            print(f"Authenticated as: {profile.get('emailAddress')}")
        else:
            print("\n❌ Authentication failed. Please check the console output for any error messages.")
            print("You may need to copy a URL from the console into your browser and then paste the resulting code.")

    except Exception as e:
        print(f"\nAn error occurred during the authentication process: {e}")
        logging.error("Authentication process failed.", exc_info=True)

    print("\n" + "="*60)
    print("Process finished.")

if __name__ == "__main__":
    # Ensure the .google_key directory exists
    token_dir = os.path.dirname(GMAIL_CONFIG.get('token_path'))
    if token_dir and not os.path.exists(token_dir):
        os.makedirs(token_dir)

    main()
