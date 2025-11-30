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
        """
        date = self._format_date(meeting.get('created_at') or meeting.get('recording_start_time'))
        title = meeting.get('title') or meeting.get('meeting_title') or 'Untitled_Meeting'
        
        folder_name = f"{date}_{self._sanitize_filename(title)}"
        folder_path = os.path.join(self.base_dir, folder_name)
        
        # Handle duplicate folder names
        if os.path.exists(folder_path):
            counter = 1
            while os.path.exists(f"{folder_path}_{counter}"):
                counter += 1
            folder_path = f"{folder_path}_{counter}"
        
        os.makedirs(folder_path, exist_ok=True)
        return folder_path
    
    def save_metadata(self, folder_path: str, meeting: Dict[str, Any]) -> str:
        """Save meeting metadata as JSON"""
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
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def save_transcript(self, folder_path: str, transcript: List[Dict]) -> tuple:
        """
        Save transcript in both JSON and human-readable text formats
        Returns (json_path, txt_path)
        """
        # Save JSON version
        json_path = os.path.join(folder_path, 'transcript.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(transcript, f, indent=2, ensure_ascii=False)
        
        # Save human-readable text version
        txt_path = os.path.join(folder_path, 'transcript.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            for entry in transcript:
                speaker = entry.get('speaker', {})
                speaker_name = speaker.get('display_name', 'Unknown')
                timestamp = entry.get('timestamp', '')
                text = entry.get('text', '')
                
                f.write(f"[{timestamp}] {speaker_name}:\n")
                f.write(f"{text}\n\n")
        
        return json_path, txt_path
    
    def save_summary(self, folder_path: str, summary: Dict[str, Any]) -> str:
        """Save summary as markdown file"""
        filepath = os.path.join(folder_path, 'summary.md')
        
        template_name = summary.get('template_name', 'general')
        content = summary.get('markdown_formatted', '')
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# Meeting Summary\n\n")
            f.write(f"*Template: {template_name}*\n\n")
            f.write(content)
        
        return filepath
    
    def save_action_items(self, folder_path: str, action_items: List[Dict]) -> tuple:
        """
        Save action items in both JSON and markdown formats
        Returns (json_path, md_path)
        """
        # Save JSON version
        json_path = os.path.join(folder_path, 'action_items.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(action_items, f, indent=2, ensure_ascii=False)
        
        # Save markdown version
        md_path = os.path.join(folder_path, 'action_items.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write("# Action Items\n\n")
            
            for i, item in enumerate(action_items, 1):
                description = item.get('description', 'No description')
                completed = item.get('completed', False)
                assignee = item.get('assignee', {})
                assignee_name = assignee.get('name', 'Unassigned')
                timestamp = item.get('recording_timestamp', '')
                playback_url = item.get('recording_playback_url', '')
                
                checkbox = '☑' if completed else '☐'
                
                f.write(f"## {i}. {checkbox} {description}\n\n")
                f.write(f"- **Assignee:** {assignee_name}\n")
                if timestamp:
                    f.write(f"- **Timestamp:** {timestamp}\n")
                if playback_url:
                    f.write(f"- **Link:** [{playback_url}]({playback_url})\n")
                f.write(f"- **Status:** {'Completed' if completed else 'Pending'}\n")
                f.write("\n")
        
        return json_path, md_path

