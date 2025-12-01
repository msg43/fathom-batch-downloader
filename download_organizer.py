"""
Download Organizer
Handles folder creation and file organization for downloaded content
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional


class DownloadOrganizer:
    """Organizes downloaded meeting content into structured folders"""
    
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
    
    def _safe_write(self, filepath: str, content: str, encoding: str = 'utf-8') -> bool:
        """
        Write content to file only if new content is larger than existing.
        Returns True if file was written, False if skipped.
        """
        new_size = len(content.encode(encoding))
        
        if os.path.exists(filepath):
            existing_size = os.path.getsize(filepath)
            if new_size <= existing_size:
                return False  # Skip - existing file is same size or larger
        
        with open(filepath, 'w', encoding=encoding) as f:
            f.write(content)
        return True
    
    def _safe_write_json(self, filepath: str, data: Any) -> bool:
        """
        Write JSON data to file only if new content is larger than existing.
        Returns True if file was written, False if skipped.
        """
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return self._safe_write(filepath, content)
    
    def _sanitize_filename(self, name: str) -> str:
        """Convert a string to a safe filename"""
        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        
        # Limit length
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        
        return sanitized or 'untitled'
    
    def _format_date(self, date_str: Optional[str]) -> str:
        """Format a date string for folder naming"""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        
        try:
            # Parse ISO format date
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except:
            return datetime.now().strftime('%Y-%m-%d')
    
    def create_meeting_folder(self, meeting: Dict[str, Any]) -> str:
        """
        Create a folder for a meeting with format: YYYY-MM-DD_Meeting_Title
        Returns the folder path
        If folder exists, it will be reused (files will be overwritten)
        """
        date = self._format_date(meeting.get('created_at') or meeting.get('recording_start_time'))
        title = meeting.get('title') or meeting.get('meeting_title') or 'Untitled_Meeting'
        
        folder_name = f"{date}_{self._sanitize_filename(title)}"
        folder_path = os.path.join(self.base_dir, folder_name)
        
        # Create folder (or reuse existing - files will be overwritten)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path
    
    def save_metadata(self, folder_path: str, meeting: Dict[str, Any]) -> str:
        """Save meeting metadata as JSON (always overwrites - metadata is small)"""
        metadata = {
            'id': meeting.get('recording_id'),
            'title': meeting.get('title'),
            'meeting_title': meeting.get('meeting_title'),
            'url': meeting.get('url'),
            'share_url': meeting.get('share_url'),
            'created_at': meeting.get('created_at'),
            'recording_start_time': meeting.get('recording_start_time'),
            'recording_end_time': meeting.get('recording_end_time'),
            'recorded_by': meeting.get('recorded_by'),
            'calendar_invitees': meeting.get('calendar_invitees', []),
            'calendar_invitees_domains_type': meeting.get('calendar_invitees_domains_type'),
            'transcript_language': meeting.get('transcript_language')
        }
        
        filepath = os.path.join(folder_path, 'metadata.json')
        self._safe_write_json(filepath, metadata)
        
        return filepath
    
    def save_transcript(self, folder_path: str, transcript) -> tuple:
        """
        Save transcript in both JSON and human-readable text formats
        Returns (json_path, txt_path)
        Handles various transcript formats from Fathom API
        Only overwrites if new file is larger than existing.
        """
        # Save JSON version
        json_path = os.path.join(folder_path, 'transcript.json')
        self._safe_write_json(json_path, transcript)
        
        # Build human-readable text version
        txt_path = os.path.join(folder_path, 'transcript.txt')
        lines = []
        
        # Handle different transcript formats
        entries = transcript
        
        # If transcript is a dict with 'entries' or 'segments' key
        if isinstance(transcript, dict):
            entries = transcript.get('entries') or transcript.get('segments') or transcript.get('transcript') or []
        
        # If entries is still not a list, try to handle it
        if not isinstance(entries, list):
            lines.append(str(entries))
        else:
            for entry in entries:
                # Skip non-dict entries
                if isinstance(entry, str):
                    lines.append(f"{entry}\n")
                    continue
                    
                if not isinstance(entry, dict):
                    continue
                
                # Try different field names for speaker
                speaker = entry.get('speaker', {})
                if isinstance(speaker, str):
                    speaker_name = speaker
                elif isinstance(speaker, dict):
                    speaker_name = speaker.get('display_name') or speaker.get('name', 'Unknown')
                else:
                    speaker_name = 'Unknown'
                
                # Try different field names for timestamp
                timestamp = entry.get('timestamp') or entry.get('start_time') or entry.get('time', '')
                
                # Try different field names for text
                text = entry.get('text') or entry.get('content') or entry.get('transcript', '')
                
                lines.append(f"[{timestamp}] {speaker_name}:\n{text}\n")
        
        # Only write if new content is larger
        self._safe_write(txt_path, '\n'.join(lines))
        
        return json_path, txt_path
    
    def save_summary(self, folder_path: str, summary: Dict[str, Any]) -> str:
        """Save summary as markdown file. Only overwrites if new file is larger."""
        filepath = os.path.join(folder_path, 'summary.md')
        
        template_name = summary.get('template_name', 'general')
        content = summary.get('markdown_formatted', '')
        
        full_content = f"# Meeting Summary\n\n*Template: {template_name}*\n\n{content}"
        self._safe_write(filepath, full_content)
        
        return filepath
    
    def save_action_items(self, folder_path: str, action_items: List[Dict]) -> tuple:
        """
        Save action items in both JSON and markdown formats
        Returns (json_path, md_path)
        Only overwrites if new file is larger than existing.
        """
        # Save JSON version
        json_path = os.path.join(folder_path, 'action_items.json')
        self._safe_write_json(json_path, action_items)
        
        # Build markdown version
        md_path = os.path.join(folder_path, 'action_items.md')
        lines = ["# Action Items\n"]
        
        items_list = action_items if isinstance(action_items, list) else []
        for i, item in enumerate(items_list, 1):
            if not isinstance(item, dict):
                continue
            description = item.get('description', 'No description')
            completed = item.get('completed', False)
            assignee = item.get('assignee', {})
            assignee_name = assignee.get('name', 'Unassigned') if isinstance(assignee, dict) else str(assignee)
            timestamp = item.get('recording_timestamp', '')
            playback_url = item.get('recording_playback_url', '')
            
            checkbox = '☑' if completed else '☐'
            
            lines.append(f"## {i}. {checkbox} {description}\n")
            lines.append(f"- **Assignee:** {assignee_name}")
            if timestamp:
                lines.append(f"- **Timestamp:** {timestamp}")
            if playback_url:
                lines.append(f"- **Link:** [{playback_url}]({playback_url})")
            lines.append(f"- **Status:** {'Completed' if completed else 'Pending'}\n")
        
        self._safe_write(md_path, '\n'.join(lines))
        
        return json_path, md_path

