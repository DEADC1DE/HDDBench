#!/usr/bin/env python3
import argparse
import os
import subprocess
import time
import datetime
import shutil
import re
import yaml
import concurrent.futures

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def parse_size(size_str):
    match = re.match(r'^(\d+\.?\d*)([KkMmGgTt]?)[Bb]?$', size_str)
    if not match:
        raise ValueError(f"Invalid size string: {size_str}")
    num, unit = match.groups()
    num = float(num)
    unit = unit.upper()
    units = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    return int(num * units.get(unit, 1))

def test_file(file_index, run_dir, size_str, syncmode=None, debug=False):
    file_path = os.path.join(run_dir, f"testfile_{file_index}.dat")
    result = {"index": file_index, "write_time": None, "read_time": None, "error": None}
    write_cmd = ['dd', 'if=/dev/zero', f'of={file_path}', f'bs={size_str}', 'count=1']
    
    if syncmode == 'sync':
        write_cmd.append('oflag=sync')
    elif syncmode == 'dsync':
        write_cmd.append('oflag=dsync')
    elif syncmode == 'direct':
        write_cmd.append('oflag=direct')

    start = time.monotonic()
    try:
        if debug:
            subprocess.run(write_cmd, check=True)
        else:
            subprocess.run(write_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        result["error"] = f"Error writing {file_path}: {e}"
        return result
    end = time.monotonic()
    result["write_time"] = end - start

    if syncmode in ['sync', 'dsync']:
        read_cmd = ['dd', f'if={file_path}', 'of=/dev/null', f'bs={size_str}', 'count=1']
        start = time.monotonic()
        try:
            if debug:
                subprocess.run(read_cmd, check=True)
            else:
                subprocess.run(read_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            result["error"] = f"Error reading {file_path}: {e}"
            return result
        end = time.monotonic()
        result["read_time"] = end - start

    return result

def run_test_run(run_number, files, size_str, run_dir, syncmode, bytes_per_file, debug):
    print(f"{Colors.OKBLUE}Starting test run {run_number} ...{Colors.ENDC}")
    os.makedirs(run_dir, exist_ok=True)
    start_run = time.monotonic()
    results = []
    total_written_speeds = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=files) as executor:
        futures = [executor.submit(test_file, i, run_dir, size_str, syncmode, debug) for i in range(1, files + 1)]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            if result["write_time"] is not None:
                written_bytes = bytes_per_file
                write_speed = written_bytes / result["write_time"] / (1024**2)
                total_written_speeds.append(write_speed)
    
    end_run = time.monotonic()
    run_duration = end_run - start_run
    total_bytes = files * bytes_per_file
    overall_write_speed = total_bytes / run_duration / (1024**2)
    average_written_speed = sum(total_written_speeds) / len(total_written_speeds) if total_written_speeds else 0

    print(f"{Colors.OKGREEN}Test run {run_number} completed in {run_duration:.2f} s{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Overall write speed: {overall_write_speed:.2f} MB/s{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Average written speed per file: {average_written_speed:.2f} MB/s{Colors.ENDC}")

    errors = [res["error"] for res in results if res["error"]]
    if errors:
        print(f"{Colors.FAIL}Errors encountered:{Colors.ENDC}")
        for err in errors:
            print(f"  - {Colors.WARNING}{err}{Colors.ENDC}")
    print()
    
    return run_duration, overall_write_speed, average_written_speed, errors

def main():
    parser = argparse.ArgumentParser(description="HDDBench: Simultaneous file write/read performance test tool")
    parser.add_argument('--config', type=str, default='config.yaml', help="Path to YAML configuration file (default: config.yaml)")
    args = parser.parse_args()

    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"{Colors.FAIL}Error loading configuration file: {e}{Colors.ENDC}")
        return

    try:
        hdd_config = config['HDDTest']
        files = int(hdd_config['files'])
        size_str = str(hdd_config['size'])
        runs = int(hdd_config['runs'])
        keep = bool(hdd_config['keep'])
        syncmode = str(hdd_config.get('syncmode', 'none')).lower()
        test_path = hdd_config['test_path']
        debug = bool(hdd_config.get('debug', False))
    except Exception as e:
        print(f"{Colors.FAIL}Error reading configuration: {e}{Colors.ENDC}")
        return

    valid_syncmodes = ['none', 'direct', 'dsync', 'sync']
    if syncmode not in valid_syncmodes:
        print(f"{Colors.FAIL}Invalid syncmode specified: {syncmode}. Defaulting to 'none'.{Colors.ENDC}")
        syncmode = 'none'

    try:
        bytes_per_file = parse_size(size_str)
    except ValueError as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")
        return

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    base_test_dir = os.path.join(test_path, f"HDDBench_{timestamp}")
    os.makedirs(base_test_dir, exist_ok=True)

    all_run_durations = []
    all_write_speeds = []
    all_avg_written_speeds = []
    all_errors = []

    for run in range(1, runs + 1):
        run_dir = os.path.join(base_test_dir, f"run_{run}")
        run_duration, write_speed, average_written_speed, errors = run_test_run(run, files, size_str, run_dir, syncmode, bytes_per_file, debug)

        all_run_durations.append(run_duration)
        all_write_speeds.append(write_speed)
        all_avg_written_speeds.append(average_written_speed)
        all_errors.extend(errors)

        if not keep:
            try:
                shutil.rmtree(run_dir)
            except Exception as e:
                print(f"{Colors.FAIL}Error deleting run directory {run_dir}: {e}{Colors.ENDC}")

    avg_duration = sum(all_run_durations) / len(all_run_durations) if all_run_durations else 0
    avg_write_speed = sum(all_write_speeds) / len(all_write_speeds) if all_write_speeds else 0
    avg_written_speed = sum(all_avg_written_speeds) / len(all_avg_written_speeds) if all_avg_written_speeds else 0
    
    print(f"{Colors.OKCYAN}HDDBench test completed.{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Average duration per test run: {avg_duration:.2f} s{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Average write speed: {avg_write_speed:.2f} MB/s{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Average written speed per file across runs: {avg_written_speed:.2f} MB/s{Colors.ENDC}")

if __name__ == '__main__':
    main()