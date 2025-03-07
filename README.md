# clab-nokia-ip-automation
A Python tool for automating ContainerLab deployments and Ansible configuration for SROS - Nokia 7750 SR7 network labs.

## Overview

This tool simplifies the process of deploying network topologies with ContainerLab and configuring them with Ansible. It automates the following tasks:

1. Deploying a ContainerLab topology from a YAML file
2. Updating the Ansible inventory with link information from the topology
3. Waiting for all containers to become ready/healthy
4. Running an Ansible playbook to configure the network devices

## Features

- Interactive selection of topology YAML files
- Automatic detection of available Ansible playbooks
- Smart container health/readiness detection for both containers with and without health checks
- Automatic link information extraction from topology files
- Intelligent inventory updating that preserves existing structure

## Requirements

- Python 3.6+
- ContainerLab
- Ansible
- Docker
- PyYAML (`pip install pyyaml`)
  * [Python 3.6+](https://www.python.org/downloads/)
  * [ContainerLab](https://containerlab.dev/)
  * [Ansible](https://docs.ansible.com/)
  * [Docker](https://www.docker.com/)
  * [PyYaml](`pip install pyyaml`)
  * [Nokia SROS VSIM Images](`Direct Contact with Nokia`)
  * [Nokia SROS License](`Direct Contact with Nokia`)

## Installation

1. Clone this repository:
<pre>
git clone https://github.com/network-automation/clab-nokia-ip-automation.git
cd clab-ansible-automation
</pre>

3. Install required Python packages:
<pre>
pip install pyyaml
</pre>

4. Make the script executable:
chmod +x clab-nokia-ip-automation.py


5. Make the Nokia SROS docker images and point license file in the yaml:

## Usage
Run the script with:
<pre>
./clab_ansible_automation.py [topology_file.yaml]
</pre>
If you don't specify a topology file, the script will list available YAML files in the current directory.

Workflow
Select a topology YAML file
Confirm deployment
The script deploys the topology with ContainerLab
The script updates the Ansible inventory with link information
The script waits for all containers to become ready
When all containers are ready, the script runs the Ansible playbook

## License

This project is licensed under the [MIT License](LICENSE).
