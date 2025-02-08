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
import platform
import json

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

def bytes_to_readable(num_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"

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
    print(f"{Colors.OKBLUE}Starting test run {run_number}...{Colors.ENDC}")
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
                write_speed = bytes_per_file / result["write_time"] / (1024**2)
                total_written_speeds.append(write_speed)
    end_run = time.monotonic()
    run_duration = end_run - start_run
    total_bytes_expected = files * bytes_per_file
    overall_write_speed = total_bytes_expected / run_duration / (1024**2)
    average_written_speed = sum(total_written_speeds) / len(total_written_speeds) if total_written_speeds else 0
    files_successful = sum(1 for res in results if res["write_time"] is not None)
    data_written = files_successful * bytes_per_file
    print(f"{Colors.OKGREEN}Test run {run_number} completed in {run_duration:.2f} s{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Overall write speed: {overall_write_speed:.2f} MB/s{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Average file write speed: {average_written_speed:.2f} MB/s{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Successful files: {files_successful} / {files}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Data written: {bytes_to_readable(data_written)} (Expected: {bytes_to_readable(total_bytes_expected)}){Colors.ENDC}")
    errors = [res["error"] for res in results if res["error"]]
    if errors:
        print(f"{Colors.FAIL}Errors encountered:{Colors.ENDC}")
        for err in errors:
            print(f"  - {Colors.WARNING}{err}{Colors.ENDC}")
    print()
    return {
        'run': run_number,
        'duration': run_duration,
        'overall_speed': overall_write_speed,
        'avg_file_speed': average_written_speed,
        'files_successful': files_successful,
        'data_written_bytes': data_written,
        'error_count': len(errors)
    }

def print_summary_table(run_results, overall_stats):
    col1 = 8
    col2 = 15
    col3 = 10
    col4 = 12
    col5 = 16
    col6 = 16
    col7 = 18
    col8 = 24
    col9 = 8
    header = (f"{'Run':<{col1}}"
              f"{'File Size':<{col2}}"
              f"{'Flag':<{col3}}"
              f"{'Duration(s)':<{col4}}"
              f"{'Total MB/s':<{col5}}"
              f"{'File MB/s':<{col6}}"
              f"{'Success':<{col7}}"
              f"{'Data':<{col8}}"
              f"{'Errors':<{col9}}")
    separator = "-" * (col1 + col2 + col3 + col4 + col5 + col6 + col7 + col8 + col9)
    print(Colors.HEADER + "\nSummary of test runs:" + Colors.ENDC)
    print(Colors.HEADER + separator + Colors.ENDC)
    print(Colors.HEADER + header + Colors.ENDC)
    print(Colors.HEADER + separator + Colors.ENDC)
    for res in run_results:
        data_readable = bytes_to_readable(res['data_written_bytes'])
        success = f"{res['files_successful']} / {overall_stats['files_per_run']}"
        line = (f"{res['run']:<{col1}}"
                f"{overall_stats['file_size']:<{col2}}"
                f"{overall_stats['flag']:<{col3}}"
                f"{res['duration']:<{col4}.2f}"
                f"{res['overall_speed']:<{col5}.2f}"
                f"{res['avg_file_speed']:<{col6}.2f}"
                f"{success:<{col7}}"
                f"{data_readable:<{col8}}"
                f"{res['error_count']:<{col9}}")
        print(line)
    print(Colors.HEADER + separator + Colors.ENDC)
    total_success = f"{overall_stats['total_files_successful']} / {overall_stats['total_files']}"
    total_line = (f"{'Total':<{col1}}"
                  f"{overall_stats['file_size']:<{col2}}"
                  f"{overall_stats['flag']:<{col3}}"
                  f"{overall_stats['avg_duration']:<{col4}.2f}"
                  f"{overall_stats['avg_overall_speed']:<{col5}.2f}"
                  f"{overall_stats['avg_file_speed']:<{col6}.2f}"
                  f"{total_success:<{col7}}"
                  f"{overall_stats['total_data_written']:<{col8}}"
                  f"{overall_stats['total_error_count']:<{col9}}")
    print(Colors.HEADER + total_line + Colors.ENDC)
    print(Colors.HEADER + separator + Colors.ENDC)

def format_speed(raw):
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return ""
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f} GB/s"
    elif value >= 1_000:
        return f"{value/1_000:.2f} MB/s"
    else:
        return f"{value:.2f} KB/s"

def format_iops(raw):
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return ""
    if value >= 1000:
        return f"{value/1000:.1f}k"
    else:
        return f"{int(value)}"

def run_fio_test_for_bs(bs, fio_size, test_file, fio_cmd="fio"):
    jobname = f"rand_rw_{bs}"
    cmd = [
        fio_cmd,
        f"--name={jobname}",
        "--ioengine=libaio",
        "--rw=randrw",
        "--rwmixread=50",
        f"--bs={bs}",
        "--iodepth=64",
        "--numjobs=2",
        f"--size={fio_size}",
        "--runtime=30",
        "--gtod_reduce=1",
        "--direct=1",
        f"--filename={test_file}",
        "--group_reporting",
        "--output-format=json"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35, check=True)
        data = json.loads(result.stdout)
        job = data["jobs"][0]
        read_bw = job["read"]["bw"]
        read_iops = job["read"]["iops"]
        write_bw = job["write"]["bw"]
        write_iops = job["write"]["iops"]
        total_bw = read_bw + write_bw
        total_iops = read_iops + write_iops
        return {
            "bs": bs,
            "read_bw": read_bw,
            "read_iops": read_iops,
            "write_bw": write_bw,
            "write_iops": write_iops,
            "total_bw": total_bw,
            "total_iops": total_iops
        }
    except Exception as e:
        print(f"{Colors.FAIL}Fio test for block size {bs} failed: {e}{Colors.ENDC}")
        return None

def run_dd_test(disk_dir):
    test_filename = os.path.join(disk_dir, f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.test")
    write_speeds = []
    read_speeds = []
    for i in range(3):
        write_cmd = ["dd", "if=/dev/zero", f"of={test_filename}", "bs=64k", "count=16k", "oflag=direct"]
        try:
            proc = subprocess.run(write_cmd, capture_output=True, text=True, check=True)
            m = re.search(r',\s*([\d\.]+)\s*([KMGT]?B/s)', proc.stderr)
            if m:
                val, unit = m.groups()
                speed = float(val)
                if "GB" in unit.upper():
                    speed *= 1000
                write_speeds.append(speed)
        except Exception as e:
            print(f"{Colors.FAIL}dd write test failed: {e}{Colors.ENDC}")
        read_cmd = ["dd", f"if={test_filename}", "of=/dev/null", "bs=8k"]
        try:
            proc = subprocess.run(read_cmd, capture_output=True, text=True, check=True)
            m = re.search(r',\s*([\d\.]+)\s*([KMGT]?B/s)', proc.stderr)
            if m:
                val, unit = m.groups()
                speed = float(val)
                if "GB" in unit.upper():
                    speed *= 1000
                read_speeds.append(speed)
        except Exception as e:
            print(f"{Colors.FAIL}dd read test failed: {e}{Colors.ENDC}")
    try:
        os.remove(test_filename)
    except Exception:
        pass
    avg_write = sum(write_speeds)/len(write_speeds) if write_speeds else 0
    avg_read = sum(read_speeds)/len(read_speeds) if read_speeds else 0
    return avg_write, avg_read

def run_disk_test(disk_folder, fio_cmd="fio"):
    disk_dir = disk_folder
    if shutil.which(fio_cmd) is None:
        print(f"{Colors.WARNING}Fio is not installed. Skipping additional disk test.{Colors.ENDC}")
        return
    st = shutil.disk_usage(disk_folder)
    avail_kb = st.free // 1024
    arch = platform.machine().lower()
    if (("arm" in arch or arch in ["aarch64", "arm"]) and avail_kb < 524288) or (avail_kb < 2097152):
        print(f"{Colors.WARNING}\nNot enough free space available. Skipping additional disk test.{Colors.ENDC}")
        return
    fio_size = "512M" if ("arm" in arch or arch in ["aarch64", "arm"]) else "2G"
    test_file = os.path.join(disk_dir, "test.fio")
    setup_cmd = [
        fio_cmd,
        "--name=setup",
        "--ioengine=libaio",
        "--rw=read",
        "--bs=64k",
        "--iodepth=64",
        "--numjobs=2",
        f"--size={fio_size}",
        "--runtime=1",
        "--gtod_reduce=1",
        f"--filename={test_file}",
        "--direct=1",
        "--minimal"
    ]
    try:
        subprocess.run(setup_cmd, capture_output=True, text=True, check=True, timeout=15)
        print(f"{Colors.OKBLUE}Fio test file generated.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.WARNING}Error generating fio test file: {e}. Skipping additional disk test.{Colors.ENDC}")
        return
    block_sizes = ["4k", "64k", "512k", "1m"]
    fio_results = []
    for bs in block_sizes:
        print(f"{Colors.OKBLUE}Running fio test with block size {bs}...{Colors.ENDC}")
        res = run_fio_test_for_bs(bs, fio_size, test_file, fio_cmd)
        if res:
            res["read_bw_fmt"] = format_speed(res["read_bw"])
            res["write_bw_fmt"] = format_speed(res["write_bw"])
            res["total_bw_fmt"] = format_speed(res["total_bw"])
            res["read_iops_fmt"] = format_iops(res["read_iops"])
            res["write_iops_fmt"] = format_iops(res["write_iops"])
            res["total_iops_fmt"] = format_iops(res["total_iops"])
            fio_results.append(res)
    if fio_results:
        print(f"\n{Colors.HEADER}Fio Disk Speed Tests:{Colors.ENDC}")
        print("-" * 60)
        for res in fio_results:
            print(f"Block Size: {res['bs']}")
            print(f"  Read  : {res['read_bw_fmt']} ({res['read_iops_fmt']} IOPS)")
            print(f"  Write : {res['write_bw_fmt']} ({res['write_iops_fmt']} IOPS)")
            print(f"  Total : {res['total_bw_fmt']} ({res['total_iops_fmt']} IOPS)")
            print("-" * 60)
    else:
        print(f"{Colors.WARNING}No results from fio test. Skipping additional disk test.{Colors.ENDC}")

def main():
    parser = argparse.ArgumentParser(description="HDDBench: Simultaneous file write/read test tool")
    parser.add_argument('--config', type=str, default='config.yaml', help="Path to YAML configuration file (default: config.yaml)")
    parser.add_argument('--run-as-root', action='store_true', help="Allow running as root")
    args = parser.parse_args()
    if os.geteuid() == 0 and not args.run_as_root:
        print(f"{Colors.WARNING}Warning: This script should not be run as root. Use --run-as-root to run as root.{Colors.ENDC}")
        exit(1)
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
        fio_test_enabled = bool(hdd_config.get('fio_test', True))
    except Exception as e:
        print(f"{Colors.FAIL}Error reading configuration: {e}{Colors.ENDC}")
        return
    valid_syncmodes = ['none', 'direct', 'dsync', 'sync']
    if syncmode not in valid_syncmodes:
        print(f"{Colors.FAIL}Invalid syncmode: {syncmode}. Using 'none'.{Colors.ENDC}")
        syncmode = 'none'
    try:
        bytes_per_file = parse_size(size_str)
    except ValueError as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")
        return
    disk_test_folder = os.path.join(test_path, "Disk_Test")
    os.makedirs(disk_test_folder, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    base_test_dir = os.path.join(disk_test_folder, f"HDDBench_{timestamp}")
    os.makedirs(base_test_dir, exist_ok=True)
    run_results = []
    all_run_durations = []
    all_overall_speeds = []
    all_file_speeds = []
    total_files_successful = 0
    total_data_written = 0
    total_error_count = 0
    for run in range(1, runs + 1):
        run_dir = os.path.join(base_test_dir, f"run_{run}")
        res = run_test_run(run, files, size_str, run_dir, syncmode, bytes_per_file, debug)
        run_results.append(res)
        all_run_durations.append(res['duration'])
        all_overall_speeds.append(res['overall_speed'])
        all_file_speeds.append(res['avg_file_speed'])
        total_files_successful += res['files_successful']
        total_data_written += res['data_written_bytes']
        total_error_count += res['error_count']
        if not keep:
            try:
                shutil.rmtree(run_dir)
            except Exception as e:
                print(f"{Colors.FAIL}Error deleting {run_dir}: {e}{Colors.ENDC}")
    avg_duration = sum(all_run_durations) / len(all_run_durations) if all_run_durations else 0
    avg_overall_speed = sum(all_overall_speeds) / len(all_overall_speeds) if all_overall_speeds else 0
    avg_file_speed = sum(all_file_speeds) / len(all_file_speeds) if all_file_speeds else 0
    overall_stats = {
        'avg_duration': avg_duration,
        'avg_overall_speed': avg_overall_speed,
        'avg_file_speed': avg_file_speed,
        'total_files_successful': total_files_successful,
        'total_files': files * runs,
        'total_data_written': bytes_to_readable(total_data_written),
        'total_error_count': total_error_count,
        'files_per_run': files,
        'file_size': bytes_to_readable(bytes_per_file),
        'flag': syncmode
    }
    print_summary_table(run_results, overall_stats)
    if fio_test_enabled:
        print(f"\n{Colors.OKCYAN}Starting additional disk test...{Colors.ENDC}")
        run_disk_test(disk_test_folder)
    else:
        print(f"{Colors.WARNING}Additional disk test (fio) is disabled in the configuration.{Colors.ENDC}")
    if not keep:
        try:
            shutil.rmtree(disk_test_folder)
            print(f"{Colors.OKGREEN}Disk Test folder '{disk_test_folder}' has been deleted.{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}Error deleting Disk Test folder '{disk_test_folder}': {e}{Colors.ENDC}")

if __name__ == '__main__':
    main()
