"""
Video Extractor
Uses Playwright to extract and download videos from Fathom pages
Supports Google OAuth by using a persistent browser session
"""

import os
import re
import json
import requests
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, Browser, Page


class VideoExtractor:
    """Extracts video files from Fathom video pages using browser automation"""
    
    # Path to store browser session for Google OAuth
    SESSION_DIR = os.path.join(os.path.dirname(__file__), '.browser_session')
    
    def __init__(self, email: str = None, password: str = None):
        self.email = email
        self.password = password
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.authenticated = False
        self._headless = True  # Will be set to False for first-time Google auth
    
    def _ensure_browser(self, headless: bool = True):
        """Initialize browser if not already running"""
        if not self.browser:
            self.playwright = sync_playwright().start()
            
            # Create session directory if it doesn't exist
            os.makedirs(self.SESSION_DIR, exist_ok=True)
            
            self.browser = self.playwright.chromium.launch(
                headless=headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            # Try to load existing session
            storage_state = os.path.join(self.SESSION_DIR, 'state.json')
            if os.path.exists(storage_state):
                try:
                    self.context = self.browser.new_context(
                        storage_state=storage_state,
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                except:
                    self.context = self.browser.new_context(
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
            else:
                self.context = self.browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
    
    def _save_session(self):
        """Save browser session for future use"""
        if self.context:
            storage_state = os.path.join(self.SESSION_DIR, 'state.json')
            self.context.storage_state(path=storage_state)
    
    def authenticate_with_google(self) -> Tuple[bool, str]:
        """
        Launch a visible browser for Google OAuth authentication.
        User must complete the login manually, then this saves the session.
        Returns (success, message)
        """
        # Close any existing browser
        self.close()
        
        # Launch visible browser for manual login
        self._ensure_browser(headless=False)
        page = self.context.new_page()
        
        try:
            # Navigate to Fathom login
            page.goto('https://fathom.video/login', wait_until='networkidle')
            
            # Check if already logged in
            if 'login' not in page.url.lower() and 'fathom.video' in page.url:
                self._save_session()
                self.authenticated = True
                page.close()
                return True, "Already logged in! Session saved."
            
            # Wait for user to complete Google OAuth (up to 2 minutes)
            print("\n" + "="*50)
            print("GOOGLE LOGIN REQUIRED")
            print("="*50)
            print("A browser window has opened.")
            print("Please log in with your Google account.")
            print("Waiting up to 2 minutes for login...")
            print("="*50 + "\n")
            
            # Wait for redirect away from login page
            try:
                page.wait_for_url(
                    lambda url: 'login' not in url.lower() and 'accounts.google' not in url.lower(),
                    timeout=120000  # 2 minutes
                )
            except:
                page.close()
                return False, "Login timed out. Please try again."
            
            # Give it a moment to fully load
            page.wait_for_timeout(2000)
            
            # Save the session
            self._save_session()
            self.authenticated = True
            
            page.close()
            return True, "Login successful! Session saved for future downloads."
            
        except Exception as e:
            page.close()
            return False, f"Authentication error: {str(e)}"
    
    def _authenticate(self, page: Page) -> Tuple[bool, Optional[str]]:
        """Check if authenticated, prompt for Google login if needed"""
        if self.authenticated:
            return True, None
        
        try:
            # Navigate to Fathom to check auth status
            page.goto('https://fathom.video/', wait_until='networkidle')
            
            # Check if we're logged in
            if 'login' not in page.url.lower():
                self.authenticated = True
                return True, None
            
            # Not logged in - need Google OAuth
            return False, "Google authentication required. Please use 'Authenticate with Google' button first."
            
        except Exception as e:
            return False, f"Authentication check error: {str(e)}"
    
    def extract_video_url(self, fathom_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Visit a Fathom video page and extract the direct video URL
        Returns (video_url, error_message)
        """
        self._ensure_browser()
        
        page = self.context.new_page()
        video_urls = []
        
        try:
            # Set up request interception to capture video URLs
            def handle_response(response):
                url = response.url
                content_type = response.headers.get('content-type', '')
                
                # Look for video files or HLS manifests
                if any(ext in url.lower() for ext in ['.mp4', '.webm', '.m3u8', '/video/']):
                    video_urls.append(url)
                elif 'video' in content_type:
                    video_urls.append(url)
            
            page.on('response', handle_response)
            
            # Authenticate first
            success, error = self._authenticate(page)
            if not success:
                return None, error
            
            # Navigate to the video page
            page.goto(fathom_url, wait_until='networkidle', timeout=30000)
            
            # Wait a bit for video to start loading
            page.wait_for_timeout(3000)
            
            # Try to find video element in the DOM
            video_src = None
            try:
                video_element = page.query_selector('video source, video')
                if video_element:
                    video_src = video_element.get_attribute('src')
                    if video_src:
                        video_urls.append(video_src)
            except:
                pass
            
            # Try to trigger video playback to capture the URL
            try:
                play_button = page.query_selector('button[aria-label*="play" i], .play-button, [class*="play"]')
                if play_button:
                    play_button.click()
                    page.wait_for_timeout(2000)
            except:
                pass
            
            # Filter and prioritize video URLs
            mp4_urls = [u for u in video_urls if '.mp4' in u.lower()]
            
            if mp4_urls:
                # Prefer the highest quality (usually the longest URL or specific patterns)
                return mp4_urls[-1], None
            elif video_urls:
                return video_urls[-1], None
            else:
                return None, "Could not find video URL on page"
                
        except Exception as e:
            return None, str(e)
        finally:
            page.close()
    
    def download_video(
        self, 
        fathom_url: str, 
        output_folder: str,
        filename: str = "video.mp4"
    ) -> Tuple[bool, str]:
        """
        Download video from a Fathom page to the specified folder
        Returns (success, message)
        """
        video_url, error = self.extract_video_url(fathom_url)
        
        if error:
            return False, error
        
        if not video_url:
            return False, "No video URL found"
        
        try:
            # Download the video
            output_path = os.path.join(output_folder, filename)
            
            # Use cookies from browser session for authenticated download
            cookies = {}
            if self.context:
                for cookie in self.context.cookies():
                    cookies[cookie['name']] = cookie['value']
            
            response = requests.get(
                video_url,
                cookies=cookies,
                stream=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://fathom.video/'
                }
            )
            
            if response.status_code != 200:
                return False, f"Download failed with status {response.status_code}"
            
            # Get file size for progress (if available)
            total_size = int(response.headers.get('content-length', 0))
            
            # Write file
            with open(output_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            return True, f"Video saved to {output_path}"
            
        except Exception as e:
            return False, f"Download error: {str(e)}"
    
    def close(self):
        """Clean up browser resources"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        
        self.context = None
        self.browser = None
        self.playwright = None
        self.authenticated = False

