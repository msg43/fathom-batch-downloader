"""
Video Extractor
Uses Playwright to extract and download videos from Fathom pages
Supports Google OAuth by using a persistent browser session
"""

import os
import re
import sys
import json
import tempfile
import subprocess
import requests
from typing import Optional, Tuple, List
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


def _storage_state_to_netscape_cookies(storage_path: str, out_path: str) -> bool:
    """Convert Playwright storage_state JSON to Netscape cookies.txt for yt-dlp."""
    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        cookies = state.get('cookies') or []
        if not cookies:
            return False
        lines = [
            '# Netscape HTTP Cookie File',
            '# https://curl.haxx.se/rfc/cookie_spec.html',
            '',
        ]
        for c in cookies:
            domain = (c.get('domain') or '').strip()
            if not domain:
                continue
            if not domain.startswith('.'):
                domain = '.' + domain
            path = c.get('path') or '/'
            secure = 'TRUE' if c.get('secure') else 'FALSE'
            exp = c.get('expires')
            if exp is None or exp <= 0:
                exp = 2145916555
            else:
                exp = int(exp)
            name = c.get('name', '')
            value = c.get('value', '')
            if not name:
                continue
            lines.append(f'{domain}\tTRUE\t{path}\t{secure}\t{exp}\t{name}\t{value}')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True
    except Exception:
        return False


class VideoExtractor:
    """Extracts video files from Fathom video pages using browser automation"""
    
    # Path to store browser session for Google OAuth
    SESSION_DIR = os.path.join(os.path.dirname(__file__), '.browser_session')
    
    # Fathom is a SPA; "networkidle" often never fires (analytics, websockets). Use "load".
    _NAV_WAIT = 'load'
    _NAV_TIMEOUT_MS = 90_000
    
    def __init__(self, email: str = None, password: str = None):
        self.email = email
        self.password = password
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.authenticated = False
        self._headless = True  # Will be set to False for first-time Google auth

    def _profile_dir(self) -> str:
        """Persistent Chromium profile (OAuth + cookies survive across runs)."""
        return os.path.join(self.SESSION_DIR, 'chromium-profile')

    def _should_seed_storage_state(self) -> bool:
        """Load state.json into a fresh profile once (migration from old flow)."""
        storage_state = os.path.join(self.SESSION_DIR, 'state.json')
        if not os.path.exists(storage_state):
            return False
        profile_dir = self._profile_dir()
        if not os.path.isdir(profile_dir):
            return True
        try:
            return len(os.listdir(profile_dir)) == 0
        except OSError:
            return True

    def _apply_storage_state_cookies(self) -> None:
        """One-time migration: load cookies from state.json into persistent context."""
        path = os.path.join(self.SESSION_DIR, 'state.json')
        if not self.context or not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            cookies = state.get('cookies') or []
            if cookies:
                self.context.add_cookies(cookies)
        except Exception:
            pass

    def _apply_storage_state_origins(self) -> None:
        """Restore localStorage for fathom.* origins from state.json (migration helper)."""
        if not self.context:
            return
        path = os.path.join(self.SESSION_DIR, 'state.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception:
            return
        for origin in state.get('origins') or []:
            origin_url = origin.get('origin') or ''
            if 'fathom' not in origin_url.lower():
                continue
            ls_items = origin.get('localStorage') or []
            if not origin_url or not ls_items:
                continue
            page = self.context.new_page()
            try:
                page.goto(origin_url, wait_until=self._NAV_WAIT, timeout=self._NAV_TIMEOUT_MS)
                for item in ls_items:
                    name = item.get('name')
                    if name is None:
                        continue
                    value = item.get('value') or ''
                    page.evaluate(
                        """([n, v]) => { try { localStorage.setItem(n, v); } catch (e) {} }""",
                        [name, value],
                    )
            except Exception:
                pass
            finally:
                page.close()

    def _launch_persistent_context(self, launch_kwargs: dict):
        """
        Prefer installed Google Chrome (includes Google API keys; fewer OAuth quirks than bundled Chromium).
        On macOS, drop Playwright's --no-sandbox default (unnecessary and triggers a scary banner).
        """
        ignore = ['--enable-automation']
        if sys.platform == 'darwin':
            ignore.append('--no-sandbox')
        launch_kwargs = {**launch_kwargs, 'ignore_default_args': ignore}

        channel = (os.environ.get('PLAYWRIGHT_BROWSER_CHANNEL') or os.environ.get('FATHOM_BROWSER_CHANNEL') or '').strip()
        use_system_chrome = os.environ.get('FATHOM_USE_SYSTEM_CHROME', '1').lower() not in ('0', 'false', 'no')

        if channel:
            return self.playwright.chromium.launch_persistent_context(**{**launch_kwargs, 'channel': channel})

        if use_system_chrome:
            try:
                return self.playwright.chromium.launch_persistent_context(
                    **{**launch_kwargs, 'channel': 'chrome'}
                )
            except Exception:
                pass

        return self.playwright.chromium.launch_persistent_context(**launch_kwargs)

    def _ensure_browser(self, headless: bool = True):
        """Launch persistent browser context (required for reliable Google OAuth reuse)."""
        if self.context:
            return
        if os.environ.get('FATHOM_VIDEO_HEADLESS', '').lower() in ('0', 'false', 'no'):
            headless = False
        self.playwright = sync_playwright().start()
        os.makedirs(self.SESSION_DIR, exist_ok=True)
        profile_dir = self._profile_dir()
        os.makedirs(profile_dir, exist_ok=True)

        uag = (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )
        launch_kwargs = {
            'user_data_dir': profile_dir,
            'headless': headless,
            'viewport': {'width': 1280, 'height': 720},
            'locale': 'en-US',
            'user_agent': uag,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ],
        }
        seed_from_json = self._should_seed_storage_state()

        self.context = self._launch_persistent_context(launch_kwargs)
        self.browser = None

        # launch_persistent_context() does not accept storage_state; seed once for migration.
        if seed_from_json:
            self._apply_storage_state_cookies()
            self._apply_storage_state_origins()
    
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
            page.goto(
                'https://fathom.video/users/sign_in',
                wait_until=self._NAV_WAIT,
                timeout=self._NAV_TIMEOUT_MS,
            )
            
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
            
            verify = self.context.new_page()
            try:
                verify.goto(
                    'https://fathom.video/home',
                    wait_until=self._NAV_WAIT,
                    timeout=self._NAV_TIMEOUT_MS,
                )
                verify.wait_for_timeout(2000)
                vurl = verify.url.lower()
                if 'sign_in' in vurl or 'sign_up' in vurl:
                    page.close()
                    return (
                        False,
                        'Fathom still shows the sign-in page after login. Try again, use a normal network/VPN, '
                        'or ensure Chrome (not only Chromium) is used for sign-in.',
                    )
            finally:
                verify.close()
            
            page.close()
            return True, "Login successful! Session saved for future downloads."
            
        except Exception as e:
            page.close()
            return False, f"Authentication error: {str(e)}"
    
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
                video_indicators = [
                    '.mp4', '.webm', '.m3u8', '.mpd', '/video/', 'cloudfront', 'amazonaws',
                    'storage.googleapis', 'mux.com', 'akamaized', 'fastly',
                ]
                if any(ind in url.lower() for ind in video_indicators):
                    video_urls.append(url)
                elif 'video' in content_type.lower():
                    video_urls.append(url)
            
            page.on('response', handle_response)

            # Single navigation: OAuth sessions often fail on /home but work on meeting URLs.
            page.goto(
                fathom_url,
                wait_until=self._NAV_WAIT,
                timeout=self._NAV_TIMEOUT_MS,
            )
            page.wait_for_timeout(2000)

            url_lower = page.url.lower()
            if 'sign_in' in url_lower or 'sign_up' in url_lower:
                return None, (
                    'Google authentication required. Use "Sign in with Google" in the app, '
                    "or set FATHOM_VIDEO_HEADLESS=0 if headless Chrome cannot use your session."
                )
            if 'accounts.google.com' in url_lower:
                return None, (
                    'Google sign-in page opened in the automated browser. '
                    'Use "Sign in with Google" in the app to refresh the session.'
                )
            self.authenticated = True
            
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
            m3u8_urls = [u for u in unique_urls if '.m3u8' in u.lower()]
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
    
    def _download_via_ytdlp(self, share_url: str, output_path: str) -> Tuple[bool, str]:
        """
        Fathom's public share links work with yt-dlp's built-in extractor (not /calls/ URLs).
        Uses cookies from state.json when present.
        """
        cookie_file = None
        try:
            out_dir = os.path.dirname(output_path)
            base = os.path.splitext(os.path.basename(output_path))[0]
            out_tmpl = os.path.join(out_dir, f'{base}.%(ext)s')
            
            state_path = os.path.join(self.SESSION_DIR, 'state.json')
            if os.path.exists(state_path):
                fd, cookie_file = tempfile.mkstemp(suffix='_cookies.txt', text=True)
                os.close(fd)
                if not _storage_state_to_netscape_cookies(state_path, cookie_file):
                    try:
                        os.unlink(cookie_file)
                    except OSError:
                        pass
                    cookie_file = None
            
            cmd = [
                sys.executable,
                '-m',
                'yt_dlp',
                '--no-warnings',
                '--no-playlist',
                '-f',
                'bv*+ba/b',
                '--merge-output-format',
                'mp4',
                '-o',
                out_tmpl,
            ]
            if cookie_file:
                cmd.extend(['--cookies', cookie_file])
            cmd.append(share_url)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or '')[-2500:]
                return False, tail.strip() or 'yt-dlp failed'
            
            if not os.path.exists(output_path):
                for name in os.listdir(out_dir):
                    if name.startswith(base) and name.endswith('.mp4'):
                        found = os.path.join(out_dir, name)
                        if found != output_path:
                            os.replace(found, output_path)
                        break
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                mb = os.path.getsize(output_path) // 1_000_000
                return True, f'Video saved ({mb}MB) via yt-dlp'
            return False, 'yt-dlp finished but no MP4 was written'
        except subprocess.TimeoutExpired:
            return False, 'yt-dlp timed out (very long recording?)'
        except Exception as e:
            return False, f'yt-dlp error: {e}'
        finally:
            if cookie_file and os.path.exists(cookie_file):
                try:
                    os.unlink(cookie_file)
                except OSError:
                    pass
    
    def download_video(
        self, 
        fathom_url: str, 
        output_folder: str,
        filename: str = "video.mp4",
        progress_callback: callable = None
    ) -> Tuple[bool, str]:
        """
        Download video from a Fathom page to the specified folder
        Returns (success, message)
        Skips download if existing file is complete (same duration as source).
        """
        output_path = os.path.join(output_folder, filename)
        
        # yt-dlp only supports /share/... — avoids brittle Playwright HLS sniffing when it works.
        if '/share/' in fathom_url.lower():
            ok, msg = self._download_via_ytdlp(fathom_url, output_path)
            if ok:
                return True, msg
        
        video_url, error = self.extract_video_url(fathom_url)
        
        if error:
            return False, error
        
        if not video_url:
            return False, "No video URL found"
        
        # Check if file already exists and is complete
        if os.path.exists(output_path):
            existing_size = os.path.getsize(output_path)
            if existing_size > 1_000_000:  # Only check if > 1MB
                # Compare durations to verify completeness
                is_complete, msg = self._is_video_complete(output_path, video_url)
                if is_complete:
                    return True, f"Video already complete ({existing_size // 1_000_000}MB), skipped"
        
        # Check if it's an HLS stream
        if '.m3u8' in video_url.lower():
            return self._download_hls(video_url, output_path, progress_callback)
        else:
            return self._download_direct(video_url, output_path, progress_callback)
    
    def download_video_stream_url(
        self,
        stream_url: str,
        output_folder: str,
        filename: str = "video.mp4",
        api_key: Optional[str] = None,
        progress_callback: callable = None,
    ) -> Tuple[bool, str]:
        """
        Download a direct stream URL (e.g. from Fathom API). Does not use Playwright.
        Pass api_key when the CDN requires X-Api-Key.
        """
        output_path = os.path.join(output_folder, filename)
        extra = {}
        if api_key:
            extra['X-Api-Key'] = api_key
        if '.m3u8' in stream_url.lower():
            return self._download_hls(stream_url, output_path, progress_callback, extra_headers=extra)
        return self._download_direct_http(stream_url, output_path, progress_callback, extra_headers=extra)

    def _ffmpeg_headers_for_stream(self, extra_headers: Optional[dict] = None) -> str:
        """Header block for ffmpeg -cookies (all browser cookies + optional API headers)."""
        parts = []
        if self.context:
            cookies = self.context.cookies()
            cookie_parts = [f"{c['name']}={c['value']}" for c in cookies if c.get('value')]
            cookie_str = "; ".join(cookie_parts)
            if cookie_str:
                parts.append(f"Cookie: {cookie_str}\r\n")
        parts.append("Referer: https://fathom.video/\r\n")
        parts.append(
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36\r\n"
        )
        if extra_headers:
            for k, v in extra_headers.items():
                if v is not None:
                    parts.append(f"{k}: {v}\r\n")
        return "".join(parts)

    def _get_duration(self, path_or_url: str, is_url: bool = False) -> Optional[float]:
        """Get video duration in seconds using ffprobe"""
        try:
            ffprobe = self._find_ffprobe()
            if not ffprobe:
                return None
            
            cmd = [ffprobe, '-v', 'error', '-show_entries', 'format=duration', 
                   '-of', 'default=noprint_wrappers=1:nokey=1']
            
            if is_url:
                cookie_str = ""
                if self.context:
                    cookies = self.context.cookies()
                    cookie_parts = [f"{c['name']}={c['value']}" for c in cookies if c.get('value')]
                    cookie_str = "; ".join(cookie_parts)
                cmd.extend(['-headers', f'Cookie: {cookie_str}\r\n'])
            
            cmd.append(path_or_url)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except:
            pass
        return None
    
    def _find_ffprobe(self) -> Optional[str]:
        """Find ffprobe binary"""
        import shutil
        
        ffprobe_path = shutil.which('ffprobe')
        if ffprobe_path:
            return ffprobe_path
        
        common_paths = [
            '/opt/homebrew/bin/ffprobe',
            '/usr/local/bin/ffprobe',
            '/usr/bin/ffprobe',
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        return None
    
    def _is_video_complete(self, existing_path: str, source_url: str) -> Tuple[bool, str]:
        """Check if existing video is complete by verifying it's fully readable"""
        # First, verify the file is actually readable to the end (not just header)
        if not self._verify_video_readable(existing_path):
            return False, "File is corrupted or truncated"
        
        existing_duration = self._get_duration(existing_path)
        if existing_duration is None:
            return False, "Could not read existing file duration"
        
        source_duration = self._get_duration(source_url, is_url=True)
        if source_duration is None:
            # Can't verify source, but file is readable - assume complete if > 1 min
            if existing_duration > 60:
                return True, f"Source unavailable, but file is valid ({existing_duration:.0f}s)"
            return False, "Could not read source duration"
        
        # Consider complete if within 5 seconds or 98% of source duration
        duration_diff = abs(source_duration - existing_duration)
        if duration_diff <= 5 or existing_duration >= (source_duration * 0.98):
            return True, f"Complete: {existing_duration:.0f}s / {source_duration:.0f}s"
        
        return False, f"Incomplete: {existing_duration:.0f}s vs {source_duration:.0f}s expected"
    
    def _verify_video_readable(self, video_path: str) -> bool:
        """Verify video file is fully readable (not truncated)"""
        try:
            ffprobe = self._find_ffprobe()
            if not ffprobe:
                return True  # Can't verify, assume OK
            
            # Use ffprobe to try reading the entire file
            # -count_frames forces reading through the whole file
            cmd = [
                ffprobe, '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=nb_read_frames',
                '-count_frames',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            # If ffprobe can count frames without error, file is readable
            if result.returncode == 0:
                return True
            
            # Check for truncation errors
            if 'Invalid data' in result.stderr or 'moov atom not found' in result.stderr:
                return False
                
            return True  # Other errors, assume OK
            
        except subprocess.TimeoutExpired:
            return False  # Timeout likely means file is very corrupted
        except:
            return True  # Can't verify, assume OK
    
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
    
    def _download_hls(
        self,
        m3u8_url: str,
        output_path: str,
        progress_callback: callable = None,
        extra_headers: Optional[dict] = None,
    ) -> Tuple[bool, str]:
        """Download HLS stream using ffmpeg with progress monitoring."""
        import threading
        
        try:
            # Find ffmpeg
            ffmpeg = self._find_ffmpeg()
            if not ffmpeg:
                return False, "ffmpeg not found. Please install ffmpeg to download videos (brew install ffmpeg)."
            
            # Download to temp file first (safety against partial downloads)
            temp_path = output_path + '.tmp'
            
            header_block = self._ffmpeg_headers_for_stream(extra_headers)
            
            # Build ffmpeg command (download to temp file)
            cmd = [
                ffmpeg,
                '-y',  # Overwrite output
                '-headers', header_block,
                '-i', m3u8_url,
                '-c', 'copy',  # Copy streams without re-encoding
                '-bsf:a', 'aac_adtstoasc',  # Fix audio for MP4 container
                '-f', 'mp4',  # Explicitly specify MP4 format (needed for .tmp extension)
                temp_path
            ]
            
            # Run ffmpeg with progress monitoring
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Monitor file size in background
            stop_monitoring = threading.Event()
            
            def monitor_progress():
                last_size = 0
                while not stop_monitoring.is_set():
                    if os.path.exists(temp_path):
                        size = os.path.getsize(temp_path)
                        if size != last_size and progress_callback:
                            progress_callback(size)
                            last_size = size
                    stop_monitoring.wait(1)  # Check every second
            
            if progress_callback:
                monitor_thread = threading.Thread(target=monitor_progress)
                monitor_thread.start()
            
            # Wait for ffmpeg to complete
            try:
                stdout, stderr = process.communicate(timeout=1800)  # 30 minute timeout
            finally:
                stop_monitoring.set()
                if progress_callback:
                    monitor_thread.join(timeout=2)
            
            if process.returncode != 0:
                # Try without the bsf filter
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
                cmd_simple = [
                    ffmpeg,
                    '-y',
                    '-headers', header_block,
                    '-i', m3u8_url,
                    '-c', 'copy',
                    '-f', 'mp4',
                    temp_path
                ]
                result = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=1800)
                
                if result.returncode != 0:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    error_msg = result.stderr[-500:] if len(result.stderr) > 500 else result.stderr
                    return False, f"ffmpeg failed: {error_msg}"
            
            # Verify temp file was created and move to final location
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_path, output_path)
                size_mb = os.path.getsize(output_path) // 1_000_000
                return True, f"Video saved ({size_mb}MB)"
            else:
                return False, "ffmpeg completed but no output file created"
                
        except FileNotFoundError:
            return False, "ffmpeg not found. Please install ffmpeg to download videos."
        except subprocess.TimeoutExpired:
            return False, "Video download timed out (exceeded 30 minutes)"
        except Exception as e:
            return False, f"HLS download error: {str(e)}"
    
    def _download_direct(self, video_url: str, output_path: str, progress_callback: callable = None) -> Tuple[bool, str]:
        return self._download_direct_http(video_url, output_path, progress_callback, extra_headers=None)

    def _download_direct_http(
        self,
        video_url: str,
        output_path: str,
        progress_callback: callable = None,
        extra_headers: Optional[dict] = None,
    ) -> Tuple[bool, str]:
        """Download video directly via HTTP with progress monitoring."""
        temp_path = output_path + '.tmp'
        try:
            cookies = {}
            if self.context:
                for cookie in self.context.cookies():
                    cookies[cookie['name']] = cookie['value']
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://fathom.video/',
            }
            if extra_headers:
                headers.update(extra_headers)
            
            response = requests.get(
                video_url,
                cookies=cookies,
                stream=True,
                headers=headers,
            )
            
            if response.status_code != 200:
                return False, f"Download failed with status {response.status_code}"
            
            # Write to temp file with progress updates
            downloaded = 0
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):  # 64KB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded)
            
            # Move temp to final destination
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_path, output_path)
                size_mb = os.path.getsize(output_path) // 1_000_000
                return True, f"Video saved ({size_mb}MB)"
            
            return False, "Download completed but no file created"
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
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

