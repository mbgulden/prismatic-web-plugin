
import os
import json
import yaml

def load_okf_config(path: str) -> dict:
    """Loads a YAML configuration file from the given path."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_okf_document(path: str) -> str:
    """Loads the content of a markdown document from the given path."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Document file not found: {path}")
    with open(path, 'r') as f:
        return f.read()

def scan_okf_for_pwp_context(okf_root_dir: str) -> dict:
    """
    Scans the OKF directory for relevant documents for PWP context.
    Returns a dictionary where keys are file paths and values are their content.
    """
    pwp_context_files = {}

    # Search for all markdown and yaml files within the OKF root directory
    result_md = search_files(pattern='.*\\.(md|yaml|yml)$', path=okf_root_dir, target='files', file_glob='*.md,*.yaml,*.yml')
    
    file_paths = []
    if result_md and result_md.get('matches'):
        file_paths.extend([match['path'] for match in result_md['matches']])

    for file_path in file_paths:
        try:
            file_content_result = read_file(file_path)
            if file_content_result and file_content_result.get('content') is not None:
                pwp_context_files[file_path] = file_content_result['content']
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")

    return pwp_context_files
