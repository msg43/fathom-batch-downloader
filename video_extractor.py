"""
Video Extractor
Uses Playwright to extract and download videos from Fathom pages
Supports Google OAuth by using a persistent browser session
"""

import os
import re
import json
import subprocess
import requests
from typing import Optional, Tuple, List
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
            # Navigate to Fathom login page
            page.goto('https://fathom.video/users/sign_in', wait_until='networkidle')
            
            # Check if already logged in (redirected to dashboard or home)
            if 'sign_in' not in page.url.lower() and 'sign_up' not in page.url.lower():
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
                    lambda url: 'sign_in' not in url.lower() and 'sign_up' not in url.lower() and 'accounts.google' not in url.lower(),
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
            page.goto('https://fathom.video/home', wait_until='networkidle')
            
            # Check if we're logged in (not redirected to sign_in)
            if 'sign_in' not in page.url.lower() and 'sign_up' not in page.url.lower():
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
                
                # Skip blob URLs - they can't be downloaded directly
                if url.startswith('blob:'):
                    return
                
                # Look for video files, HLS manifests, or cloud storage URLs
                video_indicators = ['.mp4', '.webm', '.m3u8', '/video/', 'cloudfront', 'amazonaws', 'storage.googleapis']
                if any(ind in url.lower() for ind in video_indicators):
                    video_urls.append(url)
                elif 'video' in content_type.lower():
                    video_urls.append(url)
            
            page.on('response', handle_response)
            
            # Authenticate first
            success, error = self._authenticate(page)
            if not success:
                return None, error
            
            # Navigate to the video page
            page.goto(fathom_url, wait_until='networkidle', timeout=30000)
            
            # Wait for page to fully load
            page.wait_for_timeout(2000)
            
            # Try to trigger video playback to capture the actual URL
            try:
                # Look for play button and click it
                play_selectors = [
                    'button[aria-label*="play" i]',
                    '.play-button',
                    '[class*="play"]',
                    'video',  # Clicking video often starts playback
                    '[data-testid*="play"]'
                ]
                for selector in play_selectors:
                    try:
                        element = page.query_selector(selector)
                        if element:
                            element.click()
                            page.wait_for_timeout(3000)
                            break
                    except:
                        continue
            except:
                pass
            
            # Wait more for video to load after click
            page.wait_for_timeout(2000)
            
            # Try to find video source in page source
            try:
                # Look for video URLs in page content
                page_content = page.content()
                
                # Common patterns for video URLs in Fathom/React apps
                import re
                url_patterns = [
                    r'https://[^"\s]+\.mp4[^"\s]*',
                    r'https://[^"\s]+cloudfront[^"\s]+',
                    r'https://[^"\s]+amazonaws\.com[^"\s]+video[^"\s]*',
                    r'"videoUrl"\s*:\s*"([^"]+)"',
                    r'"video_url"\s*:\s*"([^"]+)"',
                    r'"src"\s*:\s*"(https://[^"]+\.mp4[^"]*)"',
                ]
                
                for pattern in url_patterns:
                    matches = re.findall(pattern, page_content)
                    for match in matches:
                        url = match if isinstance(match, str) else match
                        if url.startswith('http') and 'blob:' not in url:
                            video_urls.append(url)
            except:
                pass
            
            # Filter and prioritize video URLs
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for u in video_urls:
                if u not in seen and not u.startswith('blob:'):
                    seen.add(u)
                    unique_urls.append(u)
            
            # Prefer m3u8 (HLS) for streaming, then MP4
            m3u8_urls = [u for u in unique_urls if '.m3u8' in u.lower() and 'index.m3u8' in u.lower()]
            mp4_urls = [u for u in unique_urls if '.mp4' in u.lower()]
            
            if m3u8_urls:
                # Return the HLS manifest URL
                return m3u8_urls[0], None
            elif mp4_urls:
                return mp4_urls[0], None
            elif unique_urls:
                # Look for any m3u8
                any_m3u8 = [u for u in unique_urls if '.m3u8' in u.lower()]
                if any_m3u8:
                    return any_m3u8[0], None
                return unique_urls[0], None
            else:
                return None, "Could not find video URL on page. The video may use protected streaming."
                
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
        
        output_path = os.path.join(output_folder, filename)
        
        # Check if it's an HLS stream
        if '.m3u8' in video_url.lower():
            return self._download_hls(video_url, output_path)
        else:
            return self._download_direct(video_url, output_path)
    
    def _find_ffmpeg(self) -> Optional[str]:
        """Find ffmpeg binary"""
        import shutil
        
        # Check if in PATH
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            return ffmpeg_path
        
        # Check common locations
        common_paths = [
            '/opt/homebrew/bin/ffmpeg',  # macOS ARM
            '/usr/local/bin/ffmpeg',      # macOS Intel
            '/usr/bin/ffmpeg',            # Linux
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _download_hls(self, m3u8_url: str, output_path: str) -> Tuple[bool, str]:
        """Download HLS stream using ffmpeg"""
        try:
            # Find ffmpeg
            ffmpeg = self._find_ffmpeg()
            if not ffmpeg:
                return False, "ffmpeg not found. Please install ffmpeg to download videos (brew install ffmpeg)."
            
            # Build cookie string for ffmpeg
            cookie_str = ""
            if self.context:
                cookies = self.context.cookies()
                cookie_parts = [f"{c['name']}={c['value']}" for c in cookies if 'fathom' in c.get('domain', '')]
                cookie_str = "; ".join(cookie_parts)
            
            # Build ffmpeg command
            cmd = [
                ffmpeg,
                '-y',  # Overwrite output
                '-headers', f'Cookie: {cookie_str}\r\nReferer: https://fathom.video/\r\nUser-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36\r\n',
                '-i', m3u8_url,
                '-c', 'copy',  # Copy streams without re-encoding
                '-bsf:a', 'aac_adtstoasc',  # Fix audio for MP4 container
                output_path
            ]
            
            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode != 0:
                # Try without the bsf filter
                cmd_simple = [
                    ffmpeg,
                    '-y',
                    '-headers', f'Cookie: {cookie_str}\r\nReferer: https://fathom.video/\r\n',
                    '-i', m3u8_url,
                    '-c', 'copy',
                    output_path
                ]
                result = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=600)
                
                if result.returncode != 0:
                    return False, f"ffmpeg failed: {result.stderr[:200]}"
            
            # Verify file was created
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True, f"Video saved to {output_path}"
            else:
                return False, "ffmpeg completed but no output file created"
                
        except FileNotFoundError:
            return False, "ffmpeg not found. Please install ffmpeg to download videos."
        except subprocess.TimeoutExpired:
            return False, "Video download timed out (exceeded 10 minutes)"
        except Exception as e:
            return False, f"HLS download error: {str(e)}"
    
    def _download_direct(self, video_url: str, output_path: str) -> Tuple[bool, str]:
        """Download video directly via HTTP"""
        try:
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
            
            # Write file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
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

