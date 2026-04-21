#!/usr/bin/env python3
"""
Combine multiple transcript files into a single file with date headers.
Supports both JSON and TXT output formats.
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime


def find_transcript_folders(base_dir):
    """Find all folders containing transcript files, sorted by date."""
    folders = []
    base_path = Path(base_dir)
    
    for item in base_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            transcript_json = item / 'transcript.json'
            transcript_txt = item / 'transcript.txt'
            metadata_json = item / 'metadata.json'
            
            if transcript_json.exists() or transcript_txt.exists():
                # Extract date from folder name (assumes YYYY-MM-DD prefix)
                folder_name = item.name
                date_str = folder_name[:10] if len(folder_name) >= 10 else folder_name
                
                folders.append({
                    'path': item,
                    'name': folder_name,
                    'date': date_str,
                    'has_json': transcript_json.exists(),
                    'has_txt': transcript_txt.exists(),
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


def combine_txt_transcripts(folders, output_path):
    """Combine all transcript.txt files into one readable document."""
    with open(output_path, 'w') as out:
        out.write("=" * 80 + "\n")
        out.write("COMBINED TRANSCRIPTS\n")
        out.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write("=" * 80 + "\n\n")
        
        for folder in folders:
            if not folder['has_txt']:
                continue
                
            transcript_path = folder['path'] / 'transcript.txt'
            meeting_info = get_meeting_info(folder)
            
            # Write header
            out.write("\n" + "=" * 80 + "\n")
            out.write(f"DATE: {folder['date']}\n")
            if meeting_info:
                out.write(f"TITLE: {meeting_info['title']}\n")
                if meeting_info['start_time']:
                    out.write(f"START: {meeting_info['start_time']}\n")
                if meeting_info['recorded_by']:
                    out.write(f"RECORDED BY: {meeting_info['recorded_by']}\n")
            out.write(f"FOLDER: {folder['name']}\n")
            out.write("=" * 80 + "\n\n")
            
            # Write transcript content
            with open(transcript_path, 'r') as f:
                out.write(f.read())
            out.write("\n")
    
    print(f"✓ Combined TXT transcripts saved to: {output_path}")


def combine_json_transcripts(folders, output_path):
    """Combine all transcript.json files into one structured JSON file."""
    combined = {
        'generated': datetime.now().isoformat(),
        'transcripts': []
    }
    
    for folder in folders:
        if not folder['has_json']:
            continue
            
        transcript_path = folder['path'] / 'transcript.json'
        meeting_info = get_meeting_info(folder)
        
        try:
            with open(transcript_path, 'r') as f:
                transcript_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read {transcript_path}: {e}")
            continue
        
        entry = {
            'date': folder['date'],
            'folder': folder['name'],
            'meeting_info': meeting_info,
            'transcript': transcript_data.get('transcript', transcript_data)
        }
        combined['transcripts'].append(entry)
    
    with open(output_path, 'w') as f:
        json.dump(combined, f, indent=2)
    
    print(f"✓ Combined JSON transcripts saved to: {output_path}")


def combine_md_transcripts(folders, output_path):
    """Combine all transcript.txt files into a Markdown document with collapsible sections."""
    with open(output_path, 'w') as out:
        out.write("# Combined Transcripts\n\n")
        out.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        out.write(f"**Total Episodes: {len([f for f in folders if f['has_txt']])}**\n\n")
        out.write("---\n\n")
        
        for folder in folders:
            if not folder['has_txt']:
                continue
                
            transcript_path = folder['path'] / 'transcript.txt'
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
            
            # Write transcript content in a code block for readability
            out.write("```\n")
            with open(transcript_path, 'r') as f:
                content = f.read().strip()
                out.write(content)
            out.write("\n```\n\n")
            
            # End collapsible section
            out.write("</details>\n\n")
    
    print(f"✓ Combined Markdown transcripts saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Combine multiple Fathom transcript files into one.'
    )
    parser.add_argument(
        'source_dir',
        help='Directory containing transcript folders'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output filename (without extension)',
        default='combined_transcripts'
    )
    parser.add_argument(
        '-f', '--format',
        choices=['txt', 'json', 'md', 'all'],
        default='all',
        help='Output format: txt, json, md, or all (default: all)'
    )
    
    args = parser.parse_args()
    
    # Find all transcript folders
    folders = find_transcript_folders(args.source_dir)
    
    if not folders:
        print(f"No transcript folders found in: {args.source_dir}")
        return
    
    print(f"Found {len(folders)} transcript folder(s):\n")
    for folder in folders:
        print(f"  • {folder['name']}")
    print()
    
    # Determine output directory (same as source)
    output_dir = Path(args.source_dir)
    
    # Generate outputs
    if args.format in ['txt', 'all']:
        txt_output = output_dir / f"{args.output}.txt"
        combine_txt_transcripts(folders, txt_output)
    
    if args.format in ['json', 'all']:
        json_output = output_dir / f"{args.output}.json"
        combine_json_transcripts(folders, json_output)
    
    if args.format in ['md', 'all']:
        md_output = output_dir / f"{args.output}.md"
        combine_md_transcripts(folders, md_output)


if __name__ == '__main__':
    main()
