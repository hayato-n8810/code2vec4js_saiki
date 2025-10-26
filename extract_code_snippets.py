#!/usr/bin/env python3
"""
Extract code snippets from JSON files and save them as individual JS files.

Usage:
    python3 extract_code_snippets.py <input_dir> <output_dir>
    
Example:
    python3 extract_code_snippets.py outputs/extracted_code/id_222 target/id_222
"""

import json
import os
import sys
from pathlib import Path


def extract_code_snippets(input_dir: str, output_dir: str):
    """
    Extract code snippets from all *_code.json files in input_dir.
    
    Args:
        input_dir: Directory containing {project_name}_code.json files
        output_dir: Base directory for output (e.g., target/id_222)
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        print(f"[ERROR] Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Find all *_code.json files
    json_files = list(input_path.glob("*_code.json"))
    
    if not json_files:
        print(f"[WARN] No *_code.json files found in {input_dir}")
        return
    
    print(f"[INFO] Found {len(json_files)} JSON file(s)")
    
    total_snippets = 0
    
    for json_file in sorted(json_files):
        # Extract project name from filename (e.g., "wuchangming-spy-debugger_code.json" -> "wuchangming-spy-debugger")
        project_name = json_file.stem.replace("_code", "")
        
        print(f"\n[PROCESSING] {json_file.name}")
        print(f"  Project: {project_name}")
        
        # Create output directory for this project
        project_output_dir = output_path / project_name
        project_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load JSON
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON: {json_file.name}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[ERROR] Failed to read file: {json_file.name}: {e}", file=sys.stderr)
            continue
        
        # Extract results
        results = data.get("results", [])
        
        if not results:
            print(f"  [WARN] No results found in {json_file.name}")
            continue
        
        print(f"  Found {len(results)} code snippet(s)")
        
        # Save each code snippet
        for result in results:
            snippet_id = result.get("id")
            code_snippet = result.get("code_snippet", "")
            
            if snippet_id is None:
                print(f"  [WARN] Result missing 'id' field, skipping")
                continue
            
            if not code_snippet:
                print(f"  [WARN] Empty code_snippet for id={snippet_id}, skipping")
                continue
            
            # Output filename: {project_name}_{id}.js
            output_filename = f"{project_name}_{snippet_id}.js"
            output_file = project_output_dir / output_filename
            
            # Write code snippet to file
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(code_snippet)
                    f.write('\n')  # Add trailing newline
                total_snippets += 1
            except Exception as e:
                print(f"  [ERROR] Failed to write {output_filename}: {e}", file=sys.stderr)
                continue
        
        print(f"  [DONE] Saved {len(results)} snippet(s) to {project_output_dir}")
    
    print(f"\n[ALL DONE] Extracted {total_snippets} code snippets to {output_dir}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 extract_code_snippets.py <input_dir> <output_dir>", file=sys.stderr)
        print("Example: python3 extract_code_snippets.py outputs/extracted_code/id_222 target/id_222", file=sys.stderr)
        sys.exit(1)
    
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    
    extract_code_snippets(input_dir, output_dir)


if __name__ == "__main__":
    main()
