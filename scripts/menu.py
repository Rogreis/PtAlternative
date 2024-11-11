import json
import os
import platform

# The path to the JSON settings file
settings_file = 'settings.json'

# Global data
global_settings = {
    'Edit Repository Folder': "",
    'Book Repository Folder': "",
    'last_paper': -1
}



# Function to get the full path to the settings file (local to each user)
def full_settings_path():
    # Get the appropriate directory based on the operating system
    if platform.system() == 'Windows':
        config_dir = os.getenv('ProgramData')
        print()
    else:
        config_dir = os.path.join(os.path.expanduser('~'), '.config')

    # Ensure the directory exists
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    return os.path.join(config_dir, settings_file)

# Function to load the current settings
def load_settings():
    try:
        with open(full_settings_path(), 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Function to save settings to the file
def save_settings(settings):
    with open(full_settings_path(), 'w') as file:
        json.dump(settings, file, indent=4)

# Function to get the string input from the user
def get_input(prompt, default=None):
    if default:
        return input(f"{prompt} [{default}]: ") or default
    else:
        return input(f"{prompt}: ")

# Load the current settings
global_settings = load_settings()

# Get the three strings from the user
string1 = get_input("Edit Repository Folder", global_settings.get('Edit Repository Folder'))
string2 = get_input("Book Repository Folder", global_settings.get('Book Repository Folder'))

# Update the settings dictionary
global_settings['Edit Repository Folder'] = string1
global_settings['Book Repository Folder'] = string2
global_settings['last_paper'] = 20

# Save the updated settings
save_settings(global_settings)
print(f"Settings have been updated: {full_settings_path()}")
