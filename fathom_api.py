"""
Fathom API Client
Handles all communication with the Fathom API
"""

import requests
from typing import Optional, Tuple, List, Dict, Any


class FathomAPI:
    """Client for the Fathom API"""
    
    BASE_URL = "https://api.fathom.ai/external/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Tuple[Optional[Dict], Optional[str]]:
        """Make a request to the Fathom API"""
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            
            if response.status_code == 401:
                return None, "Invalid API key"
            elif response.status_code == 429:
                return None, "Rate limit exceeded. Please wait and try again."
            elif response.status_code >= 400:
                try:
                    error_data = response.json()
                    return None, error_data.get('message', f"API error: {response.status_code}")
                except:
                    return None, f"API error: {response.status_code}"
            
            return response.json(), None
            
        except requests.exceptions.ConnectionError:
            return None, "Could not connect to Fathom API"
        except requests.exceptions.Timeout:
            return None, "Request timed out"
        except Exception as e:
            return None, str(e)
    
    def validate_key(self) -> Tuple[bool, Optional[str]]:
        """Validate the API key by making a test request"""
        data, error = self._request('GET', '/meetings', params={'limit': 1})
        if error:
            return False, error
        return True, None
    
    def get_meetings(self, limit: int = 100) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Fetch all meetings from the Fathom API
        Handles pagination automatically
        """
        all_meetings = []
        cursor = None
        
        while True:
            params = {}
            if cursor:
                params['cursor'] = cursor
            
            data, error = self._request('GET', '/meetings', params=params)
            
            if error:
                return None, error
            
            items = data.get('items', [])
            all_meetings.extend(items)
            
            # Check for more pages
            cursor = data.get('next_cursor')
            if not cursor:
                break
        
        # Transform to simpler format for frontend
        meetings = []
        for m in all_meetings:
            meetings.append({
                'id': m.get('recording_id'),
                'title': m.get('title') or m.get('meeting_title') or 'Untitled Meeting',
                'meeting_title': m.get('meeting_title'),
                'date': m.get('created_at'),
                'url': m.get('url'),
                'share_url': m.get('share_url'),
                'recording_start_time': m.get('recording_start_time'),
                'recording_end_time': m.get('recording_end_time'),
                'recorded_by': m.get('recorded_by', {}).get('name'),
                'calendar_invitees': m.get('calendar_invitees', [])
            })
        
        # Sort by date, newest first
        meetings.sort(key=lambda x: x.get('date') or '', reverse=True)
        
        return meetings, None
    
    def get_meeting_details(
        self, 
        recording_id: int, 
        options: Dict[str, bool],
        meeting_info: Optional[Dict] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Fetch detailed meeting data including transcript, summary, etc.
        If meeting_info is provided, use it as base and fetch additional data.
        """
        # Use provided meeting info as base, or create minimal structure
        meeting = meeting_info.copy() if meeting_info else {'recording_id': recording_id}
        
        # Fetch transcript if requested
        if options.get('transcript'):
            transcript, error = self.get_transcript(recording_id)
            if transcript:
                meeting['transcript'] = transcript
            elif error:
                meeting['transcript_error'] = error
        
        # Fetch summary if requested  
        if options.get('summary'):
            summary, error = self.get_summary(recording_id)
            if summary:
                meeting['summary'] = summary
            elif error:
                meeting['summary_error'] = error
        
        # Fetch action items if requested
        if options.get('action_items'):
            action_items, error = self.get_action_items(recording_id)
            if action_items:
                meeting['action_items'] = action_items
            elif error:
                meeting['action_items_error'] = error
        
        return meeting, None
    
    def get_transcript(self, recording_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch transcript for a specific recording"""
        return self._request('GET', f'/recordings/{recording_id}/transcript')
    
    def get_summary(self, recording_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch summary for a specific recording"""
        return self._request('GET', f'/recordings/{recording_id}/summary')
    
    def get_action_items(self, recording_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch action items for a specific recording"""
        return self._request('GET', f'/recordings/{recording_id}/action_items')

