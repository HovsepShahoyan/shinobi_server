"""
ONVIF Event Listener

Subscribes to ONVIF events from cameras and forwards them to Shinobi's motion API.
Shinobi handles all the actual recording with pre/post buffers.
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from typing import Callable, Optional, Dict
import uuid
import hashlib
import base64
from loguru import logger


class ONVIFEventListener:
    """
    ONVIF PullPoint subscription listener.
    Forwards motion events to a callback (which triggers Shinobi recording).
    """
    
    def __init__(self):
        self.subscriptions: Dict[str, dict] = {}
        self.running = False
        self._tasks: Dict[str, asyncio.Task] = {}

    def _create_auth_header(self, username: str, password: str) -> str:
        """Create WS-Security header"""
        nonce = base64.b64encode(uuid.uuid4().bytes).decode()
        created = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        nonce_bytes = base64.b64decode(nonce)
        digest_input = nonce_bytes + created.encode() + password.encode()
        password_digest = base64.b64encode(hashlib.sha1(digest_input).digest()).decode()
        
        return f'''
        <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                       xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
            <wsse:UsernameToken>
                <wsse:Username>{username}</wsse:Username>
                <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password>
                <wsse:Nonce>{nonce}</wsse:Nonce>
                <wsu:Created>{created}</wsu:Created>
            </wsse:UsernameToken>
        </wsse:Security>
        '''

    async def _soap_request(self, url: str, action: str, body: str,
                            username: str = None, password: str = None,
                            session_cookie: str = None) -> Optional[str]:
        """Send SOAP request"""
        auth = self._create_auth_header(username, password) if username else ""
        
        envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
                       xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
                       xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
            <soap:Header>{auth}</soap:Header>
            <soap:Body>{body}</soap:Body>
        </soap:Envelope>'''
        
        headers = {'Content-Type': 'application/soap+xml'}
        if session_cookie:
            headers['Cookie'] = session_cookie
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=envelope, headers=headers,
                                        timeout=30, allow_redirects=False) as resp:
                    return await resp.text()
        except Exception as e:
            logger.error(f"SOAP error: {e}")
            return None

    async def _web_login(self, base_url: str, username: str, password: str) -> Optional[str]:
        """
        Login via web form to get session cookie.
        Required for RPOS Camera and similar servers.
        """
        login_url = f"{base_url}/login"
        
        try:
            async with aiohttp.ClientSession() as session:
                # POST login form
                data = {'username': username, 'password': password}
                async with session.post(login_url, data=data, allow_redirects=False) as resp:
                    # Get session cookie from response
                    cookies = resp.cookies
                    if cookies:
                        cookie_str = '; '.join([f"{k}={v.value}" for k, v in cookies.items()])
                        logger.debug(f"Got session cookie: {cookie_str[:50]}...")
                        return cookie_str
                    
                    # Try getting from Set-Cookie header
                    set_cookie = resp.headers.get('Set-Cookie', '')
                    if set_cookie:
                        logger.debug(f"Got Set-Cookie: {set_cookie[:50]}...")
                        return set_cookie.split(';')[0]
                    
        except Exception as e:
            logger.error(f"Web login failed: {e}")
        
        return None

    async def create_subscription(self, camera_id: str, onvif_url: str,
                                   username: str, password: str) -> Optional[str]:
        """Create PullPoint subscription"""
        # Get base URL for login
        from urllib.parse import urlparse
        parsed = urlparse(onvif_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # First, try web login to get session cookie
        logger.info(f"Attempting web login for {camera_id}...")
        session_cookie = await self._web_login(base_url, username, password)
        
        if session_cookie:
            logger.info(f"✅ Web login successful for {camera_id}")
            # Store cookie for future requests
            self.subscriptions[camera_id] = {
                'session_cookie': session_cookie,
                'base_url': base_url,
                'username': username,
                'password': password
            }
        else:
            logger.warning(f"Web login failed for {camera_id}, trying without session")
        
        # Try to get event service URL
        event_url = onvif_url.replace('device_service', 'event_service')
        
        body = '''
        <tev:CreatePullPointSubscription>
            <tev:InitialTerminationTime>PT60S</tev:InitialTerminationTime>
        </tev:CreatePullPointSubscription>
        '''
        
        response = await self._soap_request(
            event_url,
            "http://www.onvif.org/ver10/events/wsdl/CreatePullPointSubscription",
            body, username, password,
            session_cookie=session_cookie
        )
        
        if response:
            try:
                # Clean response - remove invalid XML characters
                response = response.encode('utf-8', errors='ignore').decode('utf-8')
                response = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', response)
                
                # Check if we got a redirect/login page
                if '<html' in response.lower() or 'login' in response.lower():
                    logger.error(f"Got login page instead of ONVIF response for {camera_id}")
                    with open(f"onvif_debug_{camera_id}.xml", "w") as f:
                        f.write(response)
                    return None
                
                # Try to find the Address URL with regex first
                address_match = re.search(r'<[^>]*Address[^>]*>([^<]+)</[^>]*Address>', response)
                if address_match:
                    pullpoint_url = address_match.group(1).strip()
                    if pullpoint_url.startswith('http'):
                        self.subscriptions[camera_id].update({
                            'pullpoint_url': pullpoint_url,
                        })
                        logger.info(f"✅ ONVIF subscription created for {camera_id}")
                        logger.debug(f"   PullPoint URL: {pullpoint_url}")
                        return pullpoint_url
                
                # Fallback to XML parsing
                root = ET.fromstring(response)
                for elem in root.iter():
                    if 'Address' in elem.tag and elem.text and 'http' in elem.text:
                        pullpoint_url = elem.text.strip()
                        self.subscriptions[camera_id].update({
                            'pullpoint_url': pullpoint_url,
                        })
                        logger.info(f"✅ ONVIF subscription created for {camera_id}")
                        return pullpoint_url
                        
            except ET.ParseError as e:
                logger.error(f"Failed to parse subscription XML for {camera_id}: {e}")
                try:
                    with open(f"onvif_debug_{camera_id}.xml", "w") as f:
                        f.write(response)
                    logger.info(f"   Saved response to onvif_debug_{camera_id}.xml for debugging")
                except:
                    pass
            except Exception as e:
                logger.error(f"Failed to parse subscription for {camera_id}: {e}")
        
        logger.error(f"❌ Failed to create ONVIF subscription for {camera_id}")
        return None

    async def pull_messages(self, camera_id: str) -> list:
        """Pull events from subscription"""
        if camera_id not in self.subscriptions:
            return []
        
        sub = self.subscriptions[camera_id]
        
        if 'pullpoint_url' not in sub:
            return []
        
        body = '''
        <tev:PullMessages>
            <tev:Timeout>PT30S</tev:Timeout>
            <tev:MessageLimit>10</tev:MessageLimit>
        </tev:PullMessages>
        '''
        
        response = await self._soap_request(
            sub['pullpoint_url'],
            "http://www.onvif.org/ver10/events/wsdl/PullMessages",
            body, sub.get('username'), sub.get('password'),
            session_cookie=sub.get('session_cookie')
        )
        
        events = []
        if response:
            try:
                # Check if we got HTML (login redirect)
                if '<html' in response.lower():
                    logger.warning(f"Session expired for {camera_id}, re-authenticating...")
                    # Try to re-login
                    if 'base_url' in sub:
                        new_cookie = await self._web_login(sub['base_url'], sub['username'], sub['password'])
                        if new_cookie:
                            sub['session_cookie'] = new_cookie
                    return []
                
                root = ET.fromstring(response)
                for msg in root.iter():
                    if 'NotificationMessage' in msg.tag:
                        event = self._parse_event(msg)
                        if event:
                            events.append(event)
            except:
                pass
        
        return events

    def _parse_event(self, msg_element) -> Optional[dict]:
        """Parse notification message"""
        event = {'topic': '', 'data': {}, 'timestamp': datetime.now().isoformat()}
        
        for child in msg_element.iter():
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            
            if tag == 'Topic':
                event['topic'] = child.text or ''
            elif tag == 'SimpleItem':
                name = child.attrib.get('Name', 'unknown')
                value = child.attrib.get('Value', '')
                event['data'][name] = value
        
        return event if event['topic'] or event['data'] else None

    async def renew_subscription(self, camera_id: str) -> bool:
        """Renew subscription before timeout"""
        if camera_id not in self.subscriptions:
            return False
        
        sub = self.subscriptions[camera_id]
        
        if 'pullpoint_url' not in sub:
            return False
        
        body = '<wsnt:Renew xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"><wsnt:TerminationTime>PT60S</wsnt:TerminationTime></wsnt:Renew>'
        
        response = await self._soap_request(
            sub['pullpoint_url'],
            "http://docs.oasis-open.org/wsn/bw-2/Renew",
            body, sub.get('username'), sub.get('password'),
            session_cookie=sub.get('session_cookie')
        )
        
        return response is not None and 'RenewResponse' in response

    async def start_listening(self, camera_id: str, onvif_url: str,
                               username: str, password: str,
                               callback: Callable):
        """Subscribe and start pulling events"""
        pullpoint = await self.create_subscription(camera_id, onvif_url, username, password)
        
        if not pullpoint:
            return False
        
        async def pull_loop():
            renew_counter = 0
            while self.running:
                try:
                    events = await self.pull_messages(camera_id)
                    
                    for event in events:
                        # Check if this is a motion/active event
                        if self._is_motion_event(event):
                            logger.info(f"🚨 Motion event from {camera_id}")
                            await callback(camera_id, event)
                    
                    # Renew subscription periodically
                    renew_counter += 5
                    if renew_counter >= 45:
                        await self.renew_subscription(camera_id)
                        renew_counter = 0
                    
                    await asyncio.sleep(5)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Pull error for {camera_id}: {e}")
                    await asyncio.sleep(5)
        
        self._tasks[camera_id] = asyncio.create_task(pull_loop())
        return True

    def _is_motion_event(self, event: dict) -> bool:
        """Check if event indicates motion/activity"""
        topic = event.get('topic', '').lower()
        data = event.get('data', {})
        
        # Check topic for motion-related keywords
        motion_keywords = ['motion', 'videomotion', 'cellmotion', 'tamper', 
                          'linecross', 'intrusion', 'field', 'crossing']
        
        if any(kw in topic for kw in motion_keywords):
            # Check if state is active
            state = str(data.get('IsMotion', data.get('State', data.get('value', '')))).lower()
            return state in ['true', '1', 'active', 'yes', '']
        
        # Generic active state
        state = str(data.get('State', data.get('value', ''))).lower()
        return state in ['active', 'true', '1']

    async def start(self):
        """Start the listener"""
        self.running = True
        logger.info("ONVIF Event Listener started")

    async def stop(self):
        """Stop all subscriptions"""
        self.running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        self.subscriptions.clear()
        logger.info("ONVIF Event Listener stopped")