#!/usr/bin/env python3
import yaml
import subprocess
import os
import time
import re
import sys
import glob
import json

def get_port_numbers(endpoint_pair):
    ports = []
    for endpoint in endpoint_pair:
        interface_num = endpoint.split(':eth')[1]
        ports.append(f"1/1/{interface_num}")
    return ports

def get_topology_links(yaml_file):
    with open(yaml_file, 'r') as file:
        topology = yaml.safe_load(file)
        if 'topology' in topology and 'links' in topology['topology']:
            return topology['topology']['links']
    return None

def deploy_topology(filename):
    try:
        print(f"\nDeploying topology: {filename}")
        deploy_command = f"sudo clab deploy -t {filename}"
        process = subprocess.run(deploy_command, shell=True, check=True, text=True)
        print("\nTopology successfully deployed!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\nError: An issue occurred while deploying the topology!")
        print(f"Error details: {str(e)}")
        return False

def create_links_structure(original_yaml):
    topology_links = get_topology_links(original_yaml)
    if not topology_links:
        return None
    
    links_to_add = []
    for link in topology_links:
        if 'endpoints' in link:
            endpoints = link['endpoints']
            ports = get_port_numbers(endpoints)
            # Create base vars structure with just port
            link_vars = {
                'port': ports
            }
            # Add any additional vars from original topology
            if 'vars' in link:
                for key, value in link['vars'].items():
                    link_vars[key] = value
            link_config = {
                'endpoints': endpoints,
                'vars': link_vars
            }
            links_to_add.append(link_config)
    
    return links_to_add

def update_ansible_inventory(lab_name, original_yaml):
    inventory_path = f"clab-{lab_name}/ansible-inventory.yml"
    
    max_wait = 30
    wait_count = 0
    while not os.path.exists(inventory_path) and wait_count < max_wait:
        print(f"Waiting for ansible inventory file... ({wait_count}/{max_wait})")
        time.sleep(1)
        wait_count += 1
    if not os.path.exists(inventory_path):
        print(f"\nError: File {inventory_path} not found!")
        return False, None
    
    print(f"\nAnsible inventory file found: {inventory_path}")
    
    try:
        # Read the existing inventory file
        with open(inventory_path, 'r') as file:
            existing_inventory = yaml.safe_load(file)
        
        if not existing_inventory:
            print("Error: Inventory file is empty or invalid!")
            return False, None
        
        # Create links structure from the topology YAML
        links_to_add = create_links_structure(original_yaml)
        if not links_to_add:
            print("Error: Failed to create links structure!")
            return False, None
        
        # Find the appropriate place to add the links in the existing inventory
        # First, try to find the nokia_sros group
        nokia_sros_path = None
        
        # Check if we have the standard structure
        if ('all' in existing_inventory and 
            'children' in existing_inventory['all'] and 
            'nokia_sros' in existing_inventory['all']['children']):
            
            nokia_sros = existing_inventory['all']['children']['nokia_sros']
            if 'vars' not in nokia_sros:
                nokia_sros['vars'] = {}
            
            # Add the links to the vars section
            nokia_sros['vars']['links'] = links_to_add
            print("Added links to nokia_sros vars section.")
        else:
            # If we can't find the standard structure, search for any vars section
            # and add the links there
            print("Standard nokia_sros structure not found. Looking for alternative location.")
            
            # Try to find any vars section in the inventory
            if 'all' in existing_inventory and 'vars' in existing_inventory['all']:
                existing_inventory['all']['vars']['links'] = links_to_add
                print("Added links to all.vars section.")
            else:
                # If no suitable location found, add to the root level
                existing_inventory['links'] = links_to_add
                print("Added links to root level of inventory.")
        
        # Save updated inventory
        with open(inventory_path, 'w') as file:
            yaml.dump(existing_inventory, file, default_flow_style=False, sort_keys=False)
        
        print(f"\nAnsible inventory file successfully updated with new links!")
        return True, inventory_path
    
    except Exception as e:
        print(f"\nError: An issue occurred while updating ansible inventory!")
        print(f"Error details: {str(e)}")
        return False, None

def wait_for_containers_healthy(lab_name):
    print("\nChecking container health status...")
    
    max_wait_time = 300  # 5 minutes maximum wait time
    check_interval = 10  # Check every 10 seconds
    start_time = time.time()
    
    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > max_wait_time:
            print(f"\nTimeout after waiting {max_wait_time} seconds for containers to become healthy.")
            return False
        
        # Get container status using docker ps directly
        try:
            # Get all containers for this lab
            cmd = f"docker ps --filter name=clab-{lab_name} --format '{{{{.Names}}}}|{{{{.Status}}}}'"
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            
            container_lines = result.stdout.strip().split('\n')
            if not container_lines or container_lines[0] == '':
                print(f"No containers found for lab '{lab_name}'")
                time.sleep(check_interval)
                continue
            
            # Process container status
            all_ready = True
            not_ready_containers = []
            
            print("\nContainer status:")
            for line in container_lines:
                if not line or '|' not in line:
                    continue
                
                name, status = line.split('|', 1)
                print(f"  {name}: {status}")
                
                # For containers with health checks, look for "healthy"
                # For containers without health checks, just make sure they're "Up" or "running"
                if '(healthy)' in status or 'healthy' in status:
                    # Container has health check and is healthy
                    continue
                elif ('(health' in status) or ('health:' in status):
                    # Container has health check but is not healthy yet
                    all_ready = False
                    not_ready_containers.append(name)
                elif not ('Up' in status or 'running' in status):
                    # Container without health check is not running
                    all_ready = False
                    not_ready_containers.append(name)
                # Otherwise, container is running but doesn't have a health check, consider it ready
            
            if all_ready:
                print("\nAll containers are ready!")
                return True
            
            # If not all ready, wait and try again
            remaining = max_wait_time - elapsed_time
            print(f"\nWaiting for {len(not_ready_containers)} containers to become ready... (timeout in {int(remaining)}s)")
            time.sleep(check_interval)
            
        except subprocess.CalledProcessError as e:
            print(f"Error checking container status: {e}")
            time.sleep(check_interval)

def run_ansible_playbook(inventory_path):
    # Find available playbook files
    playbook_files = glob.glob('*.yaml') + glob.glob('*.yml')
    playbook_files = [f for f in playbook_files if 'playbook' in f.lower()]
    
    if not playbook_files:
        print("\nNo playbook files found in the current directory.")
        return False
    
    # If multiple playbooks found, let user choose
    selected_playbook = None
    if len(playbook_files) == 1:
        selected_playbook = playbook_files[0]
    else:
        print("\nAvailable playbook files:")
        for i, file in enumerate(playbook_files, 1):
            print(f"{i}. {file}")
        
        while True:
            choice = input("\nEnter the number of the playbook to run, or type the filename: ")
            
            # Check if the input is a number referring to the list
            if choice.isdigit() and 1 <= int(choice) <= len(playbook_files):
                selected_playbook = playbook_files[int(choice) - 1]
                break
            # Check if the input is a valid filename
            elif os.path.exists(choice) and choice.endswith(('.yaml', '.yml')):
                selected_playbook = choice
                break
            else:
                print(f"File '{choice}' not found or not a YAML file.")
                retry = input("Do you want to try again? (y/n): ").lower()
                if retry != 'y':
                    return False
    
    # Run the selected playbook
    try:
        print(f"\nRunning Ansible playbook: {selected_playbook}")
        print(f"Using inventory: {inventory_path}")
        
        ansible_command = f"ansible-playbook -i {inventory_path} {selected_playbook}"
        process = subprocess.run(ansible_command, shell=True, check=True, text=True)
        
        print("\nAnsible playbook executed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\nError: An issue occurred while running the Ansible playbook!")
        print(f"Error details: {str(e)}")
        return False

def get_yaml_file():
    # Check if a file was provided as a command-line argument
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        if os.path.exists(input_file) and input_file.endswith(('.yaml', '.yml')):
            return input_file
        else:
            print(f"Error: The file '{input_file}' does not exist or is not a YAML file.")
    
    # If no valid file was provided as an argument, prompt the user
    while True:
        # Find all YAML files in the current directory
        yaml_files = glob.glob('*.yaml') + glob.glob('*.yml')
        
        if yaml_files:
            print("\nAvailable YAML files:")
            for i, file in enumerate(yaml_files, 1):
                print(f"{i}. {file}")
            
            choice = input("\nEnter the number of the file to use, or type the filename: ")
            
            # Check if the input is a number referring to the list
            if choice.isdigit() and 1 <= int(choice) <= len(yaml_files):
                return yaml_files[int(choice) - 1]
            # Check if the input is a valid filename
            elif os.path.exists(choice) and choice.endswith(('.yaml', '.yml')):
                return choice
            # If not found, ask if user wants to enter a different name
            else:
                print(f"File '{choice}' not found or not a YAML file.")
                retry = input("Do you want to try again? (y/n): ").lower()
                if retry != 'y':
                    return None
        else:
            # No YAML files found automatically
            filename = input("\nNo YAML files found. Please enter the path to a YAML file: ")
            if os.path.exists(filename) and filename.endswith(('.yaml', '.yml')):
                return filename
            else:
                print(f"File '{filename}' not found or not a YAML file.")
                retry = input("Do you want to try again? (y/n): ").lower()
                if retry != 'y':
                    return None

def main():
    input_file = get_yaml_file()
    
    if not input_file:
        print("No valid YAML file selected. Exiting.")
        return
    
    # Get lab name from YAML file
    with open(input_file, 'r') as file:
        topology = yaml.safe_load(file)
        lab_name = topology.get('name', '')
    
    if not lab_name:
        print("Lab name not found in the YAML file!")
        return
    
    # Get confirmation for deployment
    while True:
        response = input(f"\nDo you want to deploy the topology? ({input_file}) (y/n): ").lower()
        if response in ['y', 'yes']:
            if deploy_topology(input_file):
                success, inventory_path = update_ansible_inventory(lab_name, input_file)
                if success and inventory_path:
                    # Wait for containers to become healthy
                    if wait_for_containers_healthy(lab_name):
                        # Automatically run the Ansible playbook when all containers are healthy
                        print("\nAll containers are healthy. Running Ansible playbook...")
                        run_ansible_playbook(inventory_path)
                    else:
                        print("\nSome containers are not healthy. Skipping Ansible playbook execution.")
                        run_anyway = input("Do you want to run the Ansible playbook anyway? (y/n): ").lower()
                        if run_anyway in ['y', 'yes']:
                            run_ansible_playbook(inventory_path)
            break
        elif response in ['n', 'no']:
            print("\nDeployment cancelled.")
            break
        else:
            print("\nPlease enter a valid response (y/n)")

if __name__ == "__main__":
    main()