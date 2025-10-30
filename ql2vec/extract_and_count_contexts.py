#!/usr/bin/env python3
"""
Extract contexts from JavaScript files and count them after validation.

This script performs:
1. Step 1: Extract - Run JSExtractor to get raw contexts
2. Step 2: Validate - Filter valid context lines using regex
3. Step 3: Count - Calculate total contexts per file
4. Output: Save results to JSON file

Expected Input Structure:
    target/id_222/
      {project1}/
        {project1}_1.js
        {project1}_2.js
      {project2}/
        {project2}_1.js
        ...

Output Structure:
    results/{project}/txt/{file}.test.raw.txt
    results/{project}/context_count.json

Usage:
    python3 extract_and_count_contexts.py --input target/id_222 --output results [--jobs 8]
"""

import os
import sys
import subprocess
import multiprocessing
import re
import json
from argparse import ArgumentParser
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import time
import tempfile


class ContextExtractorCounter:
    """Extract contexts from JS files and count them"""
    
    def __init__(self, max_path_length: int = 8, max_path_width: int = 2, timeout: int = 480):
        self.max_path_length = max_path_length
        self.max_path_width = max_path_width
        self.timeout = timeout
        self.python_bin = os.environ.get('PYTHON_BIN', 'python3')
        self.extract_script = '/code2vec/JSExtractor/extract.py'
        
        # Validate extract script exists
        if not os.path.exists(self.extract_script):
            # Try relative path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.extract_script = os.path.join(script_dir, '..', 'JSExtractor', 'extract.py')
            if not os.path.exists(self.extract_script):
                raise FileNotFoundError(f"Extract script not found: {self.extract_script}")
    
    def extract_file(self, js_file: Path, output_file: Path) -> bool:
        """
        Step 1: Extract contexts from JS file using JSExtractor
        
        Returns:
            True if extraction succeeded, False otherwise
        """
        try:
            cmd = [
                'timeout', '--kill-after=10s', str(self.timeout),
                self.python_bin, self.extract_script,
                '--file', str(js_file),
                '--whole_file',
                '--max_path_length', str(self.max_path_length),
                '--max_path_width', str(self.max_path_width)
            ]
            
            with open(output_file, 'w') as outf:
                result = subprocess.run(
                    cmd,
                    stdout=outf,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout + 20  # Python timeout as fallback
                )
            
            return result.returncode == 0 and output_file.stat().st_size > 0
            
        except (subprocess.TimeoutExpired, Exception) as e:
            if output_file.exists():
                output_file.unlink()
            return False
    
    def validate_and_count_contexts(self, raw_file: Path) -> Dict[str, int]:
        """
        Step 2 & 3: Validate context lines and count contexts
        
        Returns:
            dict with 'lines' (valid lines count) and 'contexts' (total contexts count)
            Returns {'lines': 0, 'contexts': 0} if no valid contexts
            Returns {'lines': -1, 'contexts': -1} if error
        """
        try:
            # Regex pattern for valid context lines (same as process_project_worker.sh)
            # Format: target_name context1,path1,token1 context2,path2,token2 ...
            pattern = re.compile(r'^[a-zA-Z|]+\s')
            
            total_lines = 0
            total_contexts = 0
            
            with open(raw_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if pattern.match(line):
                        parts = line.rstrip('\n').split(' ')
                        if len(parts) > 1:
                            # parts[0] is target_name, rest are contexts
                            total_lines += 1
                            total_contexts += len(parts) - 1
            
            return {'lines': total_lines, 'contexts': total_contexts}
            
        except Exception as e:
            return {'lines': -1, 'contexts': -1}


def process_single_file(args_tuple: Tuple) -> Dict:
    """
    Process a single JS file (for parallel execution)
    
    Args:
        args_tuple: (js_file_path, project_name, results_base_dir, extractor_config)
    
    Returns:
        dict with processing results
    """
    js_file, project_name, results_base_dir, config = args_tuple
    
    js_path = Path(js_file)
    base_name = js_path.stem
    
    # Output to results/{project}/txt/
    project_output_dir = Path(results_base_dir) / project_name / 'txt'
    project_output_dir.mkdir(parents=True, exist_ok=True)
    
    raw_file = project_output_dir / f"{base_name}.test.raw.txt"
    
    extractor = ContextExtractorCounter(
        max_path_length=config['max_path_length'],
        max_path_width=config['max_path_width'],
        timeout=config['timeout']
    )
    
    result = {
        'file': str(js_path),
        'base_name': base_name,
        'project': project_name,
        'status': 'error',
        'contexts': 'error',
        'lines': 0,
        'raw_file': None,
        'error': None
    }
    
    try:
        # Step 1: Extract
        if not extractor.extract_file(js_path, raw_file):
            result['error'] = 'Extraction failed or timeout'
            result['contexts'] = 'error'
            return result
        
        # Step 2 & 3: Validate and count
        count_result = extractor.validate_and_count_contexts(raw_file)
        
        if count_result['lines'] < 0:
            result['error'] = 'Validation/counting failed'
            result['contexts'] = 'error'
            if raw_file.exists():
                raw_file.unlink()
            return result
        
        if count_result['contexts'] == 0:
            result['status'] = 'empty'
            result['contexts'] = 0
            result['lines'] = count_result['lines']
            # Keep raw file for debugging
            result['raw_file'] = str(raw_file)
            return result
        
        # Success
        result['status'] = 'success'
        result['contexts'] = count_result['contexts']
        result['lines'] = count_result['lines']
        result['raw_file'] = str(raw_file)
        
        return result
        
    except Exception as e:
        result['error'] = str(e)
        result['contexts'] = 'error'
        # Cleanup on error
        if raw_file.exists():
            raw_file.unlink()
        return result


def find_js_files_by_project(input_dir: Path) -> Dict[str, List[Path]]:
    """
    Find all .js files grouped by project directory
    
    Expected structure: input_dir/{project}/{project}_{id}.js
    
    Returns:
        dict mapping project_name -> list of js files
    """
    projects_files = {}
    
    # Find all project directories (first level subdirectories)
    if not input_dir.exists():
        return projects_files
    
    for project_dir in sorted(input_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        
        project_name = project_dir.name
        js_files = sorted(project_dir.glob('*.js'))
        
        if js_files:
            projects_files[project_name] = js_files
    
    return projects_files


def main():
    parser = ArgumentParser(description='Extract and count contexts from JS files in parallel')
    parser.add_argument('-i', '--input', required=True, 
                        help='Input directory (e.g., target/id_222) containing project subdirectories')
    parser.add_argument('-o', '--output', required=True, 
                        help='Output base directory (e.g., results)')
    parser.add_argument('-j', '--jobs', type=int, default=None, 
                        help='Number of parallel jobs (default: CPU count)')
    parser.add_argument('--max_path_length', type=int, default=8, 
                        help='Max AST path length (default: 8)')
    parser.add_argument('--max_path_width', type=int, default=2, 
                        help='Max AST path width (default: 2)')
    parser.add_argument('--timeout', type=int, default=600, 
                        help='Timeout per file in seconds (default: 600)')
    parser.add_argument('-v', '--verbose', action='store_true', 
                        help='Verbose output')
    
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    results_base_dir = Path(args.output)
    
    if not input_dir.exists():
        print(f"[ERROR] Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Create base output directory
    results_base_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all JS files grouped by project
    projects_files = find_js_files_by_project(input_dir)
    
    if not projects_files:
        print(f"[ERROR] No project directories with .js files found in {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Count total files
    total_files = sum(len(files) for files in projects_files.values())
    print(f"[INFO] Found {len(projects_files)} project(s) with {total_files} JS file(s)")
    for project, files in projects_files.items():
        print(f"  - {project}: {len(files)} files")
    
    # Determine number of parallel jobs
    num_jobs = args.jobs or multiprocessing.cpu_count()
    print(f"[INFO] Using {num_jobs} parallel job(s)")
    
    # Configuration for workers
    config = {
        'max_path_length': args.max_path_length,
        'max_path_width': args.max_path_width,
        'timeout': args.timeout
    }
    
    # Prepare arguments for parallel execution
    # Each arg: (js_file, project_name, results_base_dir, config)
    process_args = []
    for project_name, js_files in projects_files.items():
        for js_file in js_files:
            process_args.append((js_file, project_name, results_base_dir, config))
    
    # Process files in parallel
    print(f"[INFO] Processing files...")
    start_time = time.time()
    
    success_count = 0
    empty_count = 0
    error_count = 0
    total_contexts = 0
    
    # Dictionary to store context counts per project
    project_context_counts = {project: {} for project in projects_files.keys()}
    
    with multiprocessing.Pool(processes=num_jobs) as pool:
        results = pool.imap_unordered(process_single_file, process_args)
        
        for i, result in enumerate(results, 1):
            base_name = result['base_name']
            project_name = result['project']
            
            if result['status'] == 'success':
                success_count += 1
                total_contexts += result['contexts']
                project_context_counts[project_name][base_name] = result['contexts']
                
                if args.verbose:
                    print(f"[{i}/{total_files}] ✓ {project_name}/{base_name}: "
                          f"{result['lines']} lines, {result['contexts']} contexts")
                else:
                    # Progress indicator
                    if i % 10 == 0:
                        print(f"[INFO] Processed {i}/{total_files} files...", end='\r')
            
            elif result['status'] == 'empty':
                empty_count += 1
                project_context_counts[project_name][base_name] = 0
                if args.verbose:
                    print(f"[{i}/{total_files}] ⚠ {project_name}/{base_name}: No valid contexts")
            
            else:  # error
                error_count += 1
                project_context_counts[project_name][base_name] = 'error'
                if args.verbose:
                    print(f"[{i}/{total_files}] ✗ {project_name}/{base_name}: {result['error']}")
    
    elapsed_time = time.time() - start_time
    
    # Write context counts to JSON file for each project
    print("\n[INFO] Writing JSON files...")
    
    # Collect all context counts for the combined JSON
    all_context_counts = {}
    
    for project_name, context_counts in project_context_counts.items():
        # Write per-project JSON
        json_output_path = results_base_dir / project_name / 'context_count.json'
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(context_counts, f, indent=2, ensure_ascii=False)
        
        print(f"  - {project_name}: {json_output_path}")
        
        # Add to combined dictionary
        all_context_counts.update(context_counts)
    
    # Write combined all_context_count.json
    all_json_output_path = results_base_dir / 'all_context_count.json'
    with open(all_json_output_path, 'w', encoding='utf-8') as f:
        json.dump(all_context_counts, f, indent=2, ensure_ascii=False)
    
    print(f"  - ALL PROJECTS: {all_json_output_path}")
    
    # Summary
    print("\n")
    print("=" * 60)
    print("  Context Extraction & Counting Summary")
    print("=" * 60)
    print(f"Total projects:     {len(projects_files)}")
    print(f"Total files:        {total_files}")
    print(f"Success:            {success_count}")
    print(f"Empty (no contexts): {empty_count}")
    print(f"Errors:             {error_count}")
    print(f"Total contexts:     {total_contexts}")
    if success_count > 0:
        print(f"Avg contexts/file:  {total_contexts / success_count:.1f}")
    print(f"Processing time:    {elapsed_time:.1f}s")
    print(f"Output directory:   {results_base_dir}")
    print(f"Combined JSON:      {all_json_output_path}")
    print("=" * 60)
    
    # Write summary to file
    summary_file = results_base_dir / 'extraction_summary.txt'
    with open(summary_file, 'w') as f:
        f.write(f"Total projects: {len(projects_files)}\n")
        f.write(f"Total files: {total_files}\n")
        f.write(f"Success: {success_count}\n")
        f.write(f"Empty: {empty_count}\n")
        f.write(f"Errors: {error_count}\n")
        f.write(f"Total contexts: {total_contexts}\n")
        if success_count > 0:
            f.write(f"Avg contexts/file: {total_contexts / success_count:.1f}\n")
        f.write(f"Processing time: {elapsed_time:.1f}s\n")
    
    print(f"[INFO] Summary written to: {summary_file}")
    
    sys.exit(0 if error_count == 0 else 1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
