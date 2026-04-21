#!/usr/bin/env python3
"""
Combine multiple summary.md files into a single Markdown file with collapsible sections.
Sorted chronologically by folder name (date prefix).
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime


def find_summary_folders(base_dir):
    """Find all folders containing summary.md files, sorted by date."""
    folders = []
    base_path = Path(base_dir)
    
    for item in base_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            summary_md = item / 'summary.md'
            metadata_json = item / 'metadata.json'
            
            if summary_md.exists():
                # Extract date from folder name (assumes YYYY-MM-DD prefix)
                folder_name = item.name
                date_str = folder_name[:10] if len(folder_name) >= 10 else folder_name
                
                folders.append({
                    'path': item,
                    'name': folder_name,
                    'date': date_str,
                    'has_summary': True,
                    'has_metadata': metadata_json.exists()
                })
    
    # Sort by folder name (which includes date)
    folders.sort(key=lambda x: x['name'])
    return folders


def get_meeting_info(folder_info):
    """Extract meeting info from metadata if available."""
    if folder_info['has_metadata']:
        metadata_path = folder_info['path'] / 'metadata.json'
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                return {
                    'title': metadata.get('title', metadata.get('meeting_title', 'Unknown')),
                    'start_time': metadata.get('recording_start_time'),
                    'end_time': metadata.get('recording_end_time'),
                    'recorded_by': metadata.get('recorded_by')
                }
        except:
            pass
    return None


def combine_summaries(folders, output_path):
    """Combine all summary.md files into a Markdown document with collapsible sections."""
    with open(output_path, 'w') as out:
        out.write("# Combined Meeting Summaries\n\n")
        out.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        out.write(f"**Total Meetings: {len(folders)}**\n\n")
        out.write("---\n\n")
        
        for folder in folders:
            summary_path = folder['path'] / 'summary.md'
            meeting_info = get_meeting_info(folder)
            
            # Build the summary line for the collapsible header
            title = meeting_info['title'] if meeting_info else folder['name']
            date_display = folder['date']
            
            # Start collapsible section
            out.write("<details>\n")
            out.write(f"<summary><strong>📅 {date_display}</strong> — {title}</summary>\n\n")
            
            # Add metadata inside the section
            if meeting_info:
                if meeting_info['start_time']:
                    out.write(f"**Start Time:** {meeting_info['start_time']}  \n")
                if meeting_info['recorded_by']:
                    out.write(f"**Recorded By:** {meeting_info['recorded_by']}  \n")
            out.write(f"**Folder:** `{folder['name']}`\n\n")
            
            # Write summary content (already markdown, so include as-is)
            with open(summary_path, 'r') as f:
                content = f.read().strip()
                # Skip the "# Meeting Summary" header if present to avoid duplication
                lines = content.split('\n')
                start_idx = 0
                for i, line in enumerate(lines):
                    if line.strip().lower() == '# meeting summary':
                        start_idx = i + 1
                        # Also skip any blank lines or template line after header
                        while start_idx < len(lines) and (
                            lines[start_idx].strip() == '' or 
                            lines[start_idx].strip().lower().startswith('*template:')
                        ):
                            start_idx += 1
                        break
                
                cleaned_content = '\n'.join(lines[start_idx:]).strip()
                if cleaned_content:
                    out.write(cleaned_content)
                else:
                    out.write("*No summary content available.*")
            
            out.write("\n\n")
            
            # End collapsible section
            out.write("</details>\n\n")
    
    print(f"✓ Combined summaries saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Combine multiple Fathom summary.md files into one.'
    )
    parser.add_argument(
        'source_dir',
        help='Directory containing folders with summary.md files'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output filename (without extension)',
        default='combined_summaries'
    )
    
    args = parser.parse_args()
    
    # Find all summary folders
    folders = find_summary_folders(args.source_dir)
    
    if not folders:
        print(f"No summary.md files found in: {args.source_dir}")
        return
    
    print(f"Found {len(folders)} folder(s) with summaries:\n")
    for folder in folders:
        print(f"  • {folder['name']}")
    print()
    
    # Determine output directory (same as source)
    output_dir = Path(args.source_dir)
    md_output = output_dir / f"{args.output}.md"
    
    combine_summaries(folders, md_output)


if __name__ == '__main__':
    main()
