# ARISE — Desktop Automation Architecture

## Overview

This document specifies the desktop automation architecture for ARISE, implementing a hybrid approach combining Windows UI Automation (UIA) for native applications and Playwright for web-based/Electron applications. The system provides reliable, observable, and policy-gated desktop control.

---

## 1. Automation Architecture Principles

| Principle | Implementation |
|-----------|----------------|
| **Hybrid Backend** | UIA for native Win32/WinForms/WPF/UWP; Playwright for Chromium/Firefox/WebKit/Electron |
| **Perception Hierarchy** | UIA tree (primary) → Accessibility (fallback) → Computer Vision/OCR (last resort) |
| **Policy-Gated** | Every action checked against capability grants before execution |
| **Observable** | Full tracing, screenshots, before/after state capture for evidence |
| **Resilient** | Retry with backoff, fallback strategies, element re-resolution |
| **Idempotent Where Possible** | Operations designed to be safely retryable |
| **Cross-App Coordination** | Window management, focus handling, multi-monitor support |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DESKTOP AUTOMATION ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         DESKTOP UI AGENT (Orchestrator)                      │
│  • Receives high-level objectives                                           │
│  • Plans automation sequences                                               │
│  • Selects appropriate backend (UIA vs Playwright)                         │
│  • Handles cross-app workflows                                              │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│   WINDOWS UIA       │ │   PLAYWRIGHT        │ │   COMPUTER VISION   │
│   ADAPTER           │ │   ADAPTER           │ │   / OCR FALLBACK    │
│  (uiautomation-new) │ │  (CDP + Playwright) │ │  (Tesseract/ONNX)   │
└─────────┬───────────┘ └─────────┬───────────┘ └─────────┬───────────┘
          │                       │                       │
    ┌─────┴─────┐           ┌─────┴─────┐           ┌─────┴─────┐
    ▼           ▼           ▼           ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Native  │ │  UWP/   │ │Electron │ │ Web     │ │ Legacy  │ │  Image  │
│ Win32   │ │  WinUI  │ │ Apps    │ │ Apps    │ │ Apps    │ │  Based  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

---

## 3. Windows UIA Adapter (Primary)

### 3.1 Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Low-level UIA | `uiautomation` (Python wrapper for UIA COM) | Element tree, patterns, events |
| High-level | `pywinauto` (backend="uia") | Application launch, window management, convenient APIs |
| Interop | `comtypes` / `ctypes` | Direct COM access for advanced scenarios |
| Accessibility | `UIA` built-in patterns | Invoke, Value, Text, Scroll, Selection, etc. |

### 3.2 UIA Adapter Implementation

```python
# src/arise/adapters/windows_uia.py
import uiautomation as auto
import pywinauto
from pywinauto import Desktop, Application
from .ports import DesktopAdapterPort, AdapterCapability
from typing import Dict, List, Any, Optional
import asyncio
import threading
import time

class WindowsUIAAdapter(DesktopAdapterPort):
    """Hybrid UIA adapter: uiautomation-new (low-level) + pywinauto (high-level)"""
    
    name = "windows_uia"
    
    def __init__(self, config: UIAConfig = None):
        self.config = config or UIAConfig()
        self._uia_initialized = False
        self._lock = threading.Lock()
        self._element_cache: Dict[str, auto.Control] = {}
        self._cache_ttl = 5  # seconds
    
    @property
    def capabilities(self) -> List[AdapterCapability]:
        return [
            AdapterCapability("launch_app", "Launch Windows application", "R1", ["system.launch"]),
            AdapterCapability("find_window", "Find window by title/class", "R0", ["ui.read"]),
            AdapterCapability("click_element", "Click UI element", "R1", ["ui.click"]),
            AdapterCapability("type_text", "Type text into element", "R1", ["ui.type"]),
            AdapterCapability("get_window_state", "Get window state/position", "R0", ["ui.read"]),
            AdapterCapability("list_windows", "List all top-level windows", "R0", ["ui.read"]),
            AdapterCapability("get_element_tree", "Get full UIA tree", "R0", ["ui.read"]),
            AdapterCapability("wait_for_element", "Wait for element to appear", "R0", ["ui.read"]),
            AdapterCapability("send_keys", "Send keyboard shortcuts", "R1", ["ui.type"]),
            AdapterCapability("get_text", "Read text from element", "R0", ["ui.read"]),
            AdapterCapability("set_focus", "Set focus to window/element", "R1", ["ui.write"]),
            AdapterCapability("maximize_minimize", "Window state control", "R1", ["ui.write"]),
        ]
    
    def _ensure_uia_init(self):
        """Initialize UIA for current thread (thread-safe)"""
        with self._lock:
            if not self._uia_initialized:
                auto.InitializeUIAutomationInCurrentThread()
                self._uia_initialized = True
    
    async def health_check(self) -> bool:
        try:
            self._ensure_uia_init()
            root = auto.GetRootControl()
            return root is not None
        except Exception:
            return False
    
    async def close(self):
        if self._uia_initialized:
            auto.UninitializeUIAutomationInCurrentThread()
            self._uia_initialized = False
            self._element_cache.clear()
    
    # ===== APPLICATION LAUNCH =====
    
    async def launch_app(self, app_name: str, args: List[str] = None) -> Dict:
        """Launch app using pywinauto (handles process management)"""
        self._ensure_uia_init()
        
        # Common app mappings
        exe_map = {
            "chrome": "chrome.exe", "edge": "msedge.exe", "firefox": "firefox.exe",
            "notepad": "notepad.exe", "explorer": "explorer.exe", "cmd": "cmd.exe",
            "powershell": "powershell.exe", "vscode": "code.exe", "terminal": "wt.exe",
            "calculator": "calculator.exe", "settings": "ms-settings:",
            "word": "WINWORD.EXE", "excel": "EXCEL.EXE", "powerpoint": "POWERPNT.EXE",
            "outlook": "OUTLOOK.EXE", "teams": "Teams.exe", "slack": "Slack.exe",
        }
        
        exe = exe_map.get(app_name.lower(), app_name)
        cmd = [exe] + (args or [])
        
        try:
            app = Application(backend="uia").start(" ".join(cmd))
            main_window = app.window()
            main_window.wait("visible", timeout=10)
            
            return {
                "success": True,
                "process_id": app.process,
                "window_handle": main_window.handle,
                "title": main_window.window_text(),
                "class_name": main_window.class_name(),
            }
        except Exception as e:
            # Fallback: try ShellExecute
            try:
                import win32api
                win32api.ShellExecute(0, "open", exe, " ".join(args or []), None, 1)
                await asyncio.sleep(2)
                return await self.find_window(title=app_name)
            except Exception as e2:
                return {"success": False, "error": f"{e}; fallback: {e2}"}
    
    # ===== WINDOW MANAGEMENT =====
    
    async def find_window(self, title: str = None, class_name: str = None, 
                          process_id: int = None, handle: int = None) -> Dict:
        """Find window using multiple strategies"""
        self._ensure_uia_init()
        
        window = None
        
        if handle:
            window = auto.ControlFromHandle(handle)
        elif process_id:
            desktop = auto.GetRootControl()
            for win in desktop.GetChildren():
                if win.ControlType == auto.ControlType.WindowControl and win.ProcessId == process_id:
                    window = win
                    break
        elif title:
            # Exact match first
            window = auto.WindowControl(Name=title, searchDepth=1)
            if not window.Exists(0):
                # Partial match
                desktop = auto.GetRootControl()
                for win in desktop.GetChildren():
                    if win.ControlType == auto.ControlType.WindowControl:
                        if title.lower() in win.Name.lower():
                            window = win
                            break
        
        if window and window.Exists(0):
            rect = window.BoundingRectangle
            return {
                "found": True,
                "handle": window.NativeWindowHandle,
                "title": window.Name,
                "class_name": window.ClassName,
                "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                "width": rect.width(), "height": rect.height(),
                "process_id": window.ProcessId,
                "is_visible": window.IsVisible,
                "is_enabled": window.IsEnabled,
                "has_focus": window.HasFocus,
            }
        return {"found": False}
    
    async def list_windows(self, visible_only: bool = True) -> List[Dict]:
        """List all top-level windows"""
        self._ensure_uia_init()
        
        desktop = auto.GetRootControl()
        windows = []
        for win in desktop.GetChildren():
            if win.ControlType == auto.ControlType.WindowControl:
                if visible_only and not win.IsVisible:
                    continue
                rect = win.BoundingRectangle
                windows.append({
                    "handle": win.NativeWindowHandle,
                    "title": win.Name,
                    "class_name": win.ClassName,
                    "process_id": win.ProcessId,
                    "visible": win.IsVisible,
                    "enabled": win.IsEnabled,
                    "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                })
        return windows
    
    async def set_focus(self, window_id: str) -> Dict:
        """Set focus to window"""
        self._ensure_uia_init()
        window = auto.ControlFromHandle(int(window_id))
        if window and window.Exists(0):
            window.SetFocus()
            return {"success": True}
        return {"success": False, "error": "Window not found"}
    
    async def maximize_minimize(self, window_id: str, action: str) -> Dict:
        """Maximize, minimize, or restore window"""
        self._ensure_uia_init()
        window = auto.ControlFromHandle(int(window_id))
        if not window or not window.Exists(0):
            return {"success": False, "error": "Window not found"}
        
        try:
            if action == "maximize":
                window.Maximize()
            elif action == "minimize":
                window.Minimize()
            elif action == "restore":
                window.Restore()
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== ELEMENT INTERACTION =====
    
    async def click_element(self, selector: Dict) -> Dict:
        """Click UI element using UIA patterns"""
        self._ensure_uia_init()
        
        element = await self._resolve_element(selector)
        if not element:
            return {"success": False, "error": "Element not found"}
        
        # Capture before state
        before_rect = element.BoundingRectangle
        before_screenshot = await self._capture_element_screenshot(element)
        
        try:
            # Try InvokePattern (standard click)
            try:
                invoke = element.GetInvokePattern()
                invoke.Invoke()
                return {"success": True, "method": "invoke_pattern"}
            except Exception:
                pass
            
            # Try LegacyIAccessiblePattern (click)
            try:
                legacy = element.GetLegacyIAccessiblePattern()
                legacy.DoDefaultAction()
                return {"success": True, "method": "legacy_accessible"}
            except Exception:
                pass
            
            # Fallback: Mouse click at center
            rect = element.BoundingRectangle
            center_x = rect.left + rect.width() // 2
            center_y = rect.top + rect.height() // 2
            await self._mouse_click(center_x, center_y)
            return {"success": True, "method": "mouse_click"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def type_text(self, selector: Dict, text: str, clear_first: bool = True) -> Dict:
        """Type text into element"""
        self._ensure_uia_init()
        
        element = await self._resolve_element(selector)
        if not element:
            return {"success": False, "error": "Element not found"}
        
        try:
            # Focus first
            element.SetFocus()
            await asyncio.sleep(0.1)
            
            # Clear if requested
            if clear_first:
                await self._clear_element(element)
            
            # Try ValuePattern (direct text set)
            try:
                value_pattern = element.GetValuePattern()
                value_pattern.SetValue(text)
                return {"success": True, "method": "value_pattern"}
            except Exception:
                pass
            
            # Try TextPattern (for rich text)
            try:
                text_pattern = element.GetTextPattern()
                # TextPattern doesn't support direct set, use SendKeys
                pass
            except Exception:
                pass
            
            # Fallback: SendKeys via pyautogui
            import pyautogui
            pyautogui.write(text, interval=0.01)
            return {"success": True, "method": "send_keys"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_text(self, selector: Dict) -> Dict:
        """Get text from element"""
        self._ensure_uia_init()
        
        element = await self._resolve_element(selector)
        if not element:
            return {"success": False, "error": "Element not found"}
        
        try:
            # Try ValuePattern
            try:
                value_pattern = element.GetValuePattern()
                return {"success": True, "text": value_pattern.Value}
            except Exception:
                pass
            
            # Try TextPattern
            try:
                text_pattern = element.GetTextPattern()
                return {"success": True, "text": text_pattern.DocumentRange.GetText(-1)}
            except Exception:
                pass
            
            # Try LegacyIAccessible
            try:
                legacy = element.GetLegacyIAccessiblePattern()
                return {"success": True, "text": legacy.Value}
            except Exception:
                pass
            
            # Fallback: Name property
            return {"success": True, "text": element.Name}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def send_keys(self, keys: str, window_id: str = None) -> Dict:
        """Send keyboard shortcuts"""
        self._ensure_uia_init()
        
        if window_id:
            await self.set_focus(window_id)
            await asyncio.sleep(0.1)
        
        try:
            import pyautogui
            # Parse special keys: {ENTER}, {TAB}, {CTRL}, {ALT}, {SHIFT}, etc.
            pyautogui.hotkey(*self._parse_hotkey(keys))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== ELEMENT RESOLUTION =====
    
    async def _resolve_element(self, selector: Dict) -> Optional[auto.Control]:
        """Resolve UIA element from selector dict"""
        # Selector can contain:
        # - name, automation_id, class_name, control_type, regex_name
        # - depth, parent_handle, index
        # - path (list of selectors for hierarchy)
        
        search_props = {}
        if "name" in selector:
            search_props["Name"] = selector["name"]
        if "automation_id" in selector:
            search_props["AutomationId"] = selector["automation_id"]
        if "class_name" in selector:
            search_props["ClassName"] = selector["class_name"]
        if "control_type" in selector:
            ct = getattr(auto.ControlType, selector["control_type"], None)
            if ct:
                search_props["ControlType"] = ct
        if "regex_name" in selector:
            search_props["RegexName"] = selector["regex_name"]
        
        # Handle hierarchical path
        if "path" in selector:
            return await self._resolve_path(selector["path"])
        
        # Start from parent or root
        if "parent_handle" in selector:
            parent = auto.ControlFromHandle(int(selector["parent_handle"]))
        else:
            parent = auto.GetRootControl()
        
        # Search
        depth = selector.get("depth", 10)
        element = parent.FindFirst(**search_props, maxDepth=depth)
        
        # Handle index for multiple matches
        if "index" in selector and element:
            elements = parent.FindAll(**search_props, maxDepth=depth)
            idx = selector["index"]
            if 0 <= idx < len(elements):
                return elements[idx]
        
        if element and element.Exists(0):
            return element
        return None
    
    async def _resolve_path(self, path: List[Dict]) -> Optional[auto.Control]:
        """Resolve element by hierarchical path"""
        current = auto.GetRootControl()
        for step in path:
            current = await self._resolve_element({**step, "parent_handle": current.NativeWindowHandle})
            if not current:
                return None
        return current
    
    # ===== WAIT & STATE =====
    
    async def wait_for_element(self, selector: Dict, timeout: float = 10, 
                               interval: float = 0.5) -> Dict:
        """Wait for element to appear"""
        start = time.time()
        while time.time() - start < timeout:
            element = await self._resolve_element(selector)
            if element and element.Exists(0):
                return {"success": True, "found": True}
            await asyncio.sleep(interval)
        return {"success": False, "error": "Timeout waiting for element"}
    
    async def get_window_state(self, window_id: str) -> Dict:
        """Get window state"""
        return await self.find_window(handle=window_id)
    
    async def get_element_tree(self, window_id: str = None, max_depth: int = 5) -> Dict:
        """Get UIA tree for debugging/analysis"""
        self._ensure_uia_init()
        
        if window_id:
            root = auto.ControlFromHandle(int(window_id))
        else:
            root = auto.GetRootControl()
        
        def serialize_element(el, depth=0):
            if depth > max_depth:
                return None
            rect = el.BoundingRectangle
            children = []
            for child in el.GetChildren():
                serialized = serialize_element(child, depth + 1)
                if serialized:
                    children.append(serialized)
            return {
                "name": el.Name,
                "automation_id": el.AutomationId,
                "class_name": el.ClassName,
                "control_type": el.ControlTypeName,
                "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                "visible": el.IsVisible,
                "enabled": el.IsEnabled,
                "handle": el.NativeWindowHandle,
                "children": children,
            }
        
        return {"tree": serialize_element(root)}
    
    # ===== HELPERS =====
    
    async def _clear_element(self, element):
        """Clear element content"""
        try:
            element.SetFocus()
            import pyautogui
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('delete')
        except Exception:
            pass
    
    async def _mouse_click(self, x: int, y: int):
        """Mouse click at coordinates"""
        import pyautogui
        pyautogui.click(x, y)
    
    def _parse_hotkey(self, keys: str) -> List[str]:
        """Parse hotkey string like 'ctrl+c' -> ['ctrl', 'c']"""
        # Handle {KEY} notation
        keys = keys.replace("{", "").replace("}", "")
        return [k.strip().lower() for k in keys.split("+")]
    
    async def _capture_element_screenshot(self, element) -> bytes:
        """Capture screenshot of element bounding box"""
        rect = element.BoundingRectangle
        return await self._capture_region(rect.left, rect.top, rect.width(), rect.height())
    
    async def _capture_region(self, x: int, y: int, w: int, h: int) -> bytes:
        """Capture screen region"""
        import mss
        with mss.mss() as sct:
            monitor = {"left": x, "top": y, "width": w, "height": h}
            img = sct.grab(monitor)
            return bytes(img.rgb)
```

### 3.3 UIA Configuration

```python
@dataclass
class UIAConfig:
    # Search defaults
    default_search_depth: int = 10
    default_wait_timeout: float = 10.0
    default_wait_interval: float = 0.5
    
    # Interaction
    click_method_priority: List[str] = ["invoke", "legacy", "mouse"]
    type_method_priority: List[str] = ["value_pattern", "send_keys"]
    focus_before_action: bool = True
    
    # Coordinates
    use_physical_coordinates: bool = True  # vs logical
    dpi_aware: bool = True
    
    # Caching
    element_cache_ttl: float = 5.0
    enable_caching: bool = True
    
    # Screenshots
    capture_before_after: bool = True
    screenshot_format: str = "png"
    
    # Retry
    max_retries: int = 3
    retry_backoff: float = 0.5
```

---

## 4. Playwright Adapter (Web/Electron)

### 4.1 Architecture

```python
# src/arise/adapters/browser_playwright.py
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from .ports import BrowserAdapterPort, AdapterCapability
from typing import Dict, List, Any, Optional
import asyncio
import base64

class PlaywrightBrowserAdapter(BrowserAdapterPort):
    """Browser automation via Playwright with CDP attach to existing profiles"""
    
    name = "playwright"
    
    def __init__(self, config: PlaywrightConfig = None):
        self.config = config or PlaywrightConfig()
        self.playwright = None
        self.browsers: Dict[str, Browser] = {}
        self.contexts: Dict[str, BrowserContext] = {}
        self.pages: Dict[str, Page] = {}
        self.console_logs: Dict[str, List[Dict]] = defaultdict(list)
        self.network_logs: Dict[str, List[Dict]] = defaultdict(list)
    
    @property
    def capabilities(self) -> List[AdapterCapability]:
        return [
            AdapterCapability("attach_to_profile", "Attach to existing browser profile", "R1", ["browser.attach"]),
            AdapterCapability("launch_browser", "Launch new browser instance", "R1", ["browser.launch"]),
            AdapterCapability("navigate", "Navigate to URL", "R1", ["browser.navigate"]),
            AdapterCapability("click", "Click element", "R1", ["browser.click"]),
            AdapterCapability("type", "Type text", "R1", ["browser.type"]),
            AdapterCapability("extract", "Extract content", "R0", ["browser.read"]),
            AdapterCapability("screenshot", "Take screenshot", "R0", ["browser.read"]),
            AdapterCapability("evaluate", "Execute JavaScript", "R1", ["browser.script"]),
            AdapterCapability("get_console_logs", "Get console logs", "R0", ["browser.read"]),
            AdapterCapability("get_network_logs", "Get network logs", "R0", ["browser.read"]),
            AdapterCapability("wait_for_selector", "Wait for element", "R0", ["browser.read"]),
            AdapterCapability("trace_start", "Start trace recording", "R0", ["browser.trace"]),
            AdapterCapability("trace_stop", "Stop trace recording", "R0", ["browser.trace"]),
            AdapterCapability("download", "Handle file downloads", "R1", ["browser.download"]),
            AdapterCapability("upload", "Handle file uploads", "R1", ["browser.upload"]),
            AdapterCapability("iframe", "Interact with iframes", "R1", ["browser.navigate"]),
            AdapterCapability("shadow_dom", "Pierce shadow DOM", "R1", ["browser.script"]),
        ]
    
    async def health_check(self) -> bool:
        try:
            if not self.playwright:
                self.playwright = await async_playwright().start()
            browser = await self.playwright.chromium.launch(headless=True)
            await browser.close()
            return True
        except Exception:
            return False
    
    async def close(self):
        for context in self.contexts.values():
            await context.close()
        for browser in self.browsers.values():
            await browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    # ===== BROWSER/CONTEXT MANAGEMENT =====
    
    async def attach_to_profile(
        self,
        browser: str = "chromium",
        profile_path: str = None,
        channel: str = None,
        headless: bool = False,
        context_id: str = "default",
        viewport: Dict = None,
    ) -> Dict:
        """Attach to existing browser profile via persistent context"""
        
        if context_id in self.contexts:
            return {"success": True, "context_id": context_id, "reused": True}
        
        pw = self.playwright or await async_playwright().start()
        self.playwright = pw
        
        launch_args = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--force-renderer-accessibility",
                "--disable-web-security",  # For cross-origin iframes
                "--disable-site-isolation-trials",
            ],
        }
        
        if channel:
            launch_args["channel"] = channel
        
        if viewport:
            launch_args["viewport"] = viewport
        
        try:
            if profile_path:
                # Persistent context with existing profile
                context = await pw[browser].launch_persistent_context(
                    user_data_dir=profile_path,
                    **launch_args,
                )
            else:
                # Temporary context
                browser_instance = await pw[browser].launch(**launch_args)
                context = await browser_instance.new_context(**launch_args)
                self.browsers[context_id] = browser_instance
            
            self.contexts[context_id] = context
            
            # Set up event listeners
            self._setup_listeners(context, context_id)
            
            # Enable tracing for evidence
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            
            return {
                "success": True,
                "context_id": context_id,
                "browser": browser,
                "pages": len(context.pages),
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _setup_listeners(self, context: BrowserContext, context_id: str):
        """Set up console and network log capture"""
        self.console_logs[context_id] = []
        self.network_logs[context_id] = []
        
        context.on("console", lambda msg: self.console_logs[context_id].append({
            "type": msg.type,
            "text": msg.text,
            "location": msg.location,
            "timestamp": datetime.utcnow().isoformat(),
        }))
        
        context.on("request", lambda req: self.network_logs[context_id].append({
            "type": "request",
            "url": req.url,
            "method": req.method,
            "headers": req.headers,
            "timestamp": datetime.utcnow().isoformat(),
        }))
        
        context.on("response", lambda resp: self.network_logs[context_id].append({
            "type": "response",
            "url": resp.url,
            "status": resp.status,
            "headers": resp.headers,
            "timestamp": datetime.utcnow().isoformat(),
        }))
    
    # ===== NAVIGATION =====
    
    async def navigate(
        self,
        url: str,
        wait_until: str = "networkidle",
        timeout: int = 30000,
        context_id: str = "default",
    ) -> Dict:
        context = self.contexts.get(context_id)
        if not context:
            return {"success": False, "error": "Context not found"}
        
        page = context.pages[0] if context.pages else await context.new_page()
        self.pages[context_id] = page
        
        try:
            response = await page.goto(url, wait_until=wait_until, timeout=timeout)
            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
                "status": response.status if response else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== ELEMENT INTERACTION =====
    
    async def click(self, selector: str, context_id: str = "default", 
                    force: bool = False, timeout: int = 10000) -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.click(selector, force=force, timeout=timeout)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def type(self, selector: str, text: str, context_id: str = "default",
                   delay: int = 0, clear: bool = True) -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            if clear:
                await page.fill(selector, "", timeout=5000)
            await page.type(selector, text, delay=delay, timeout=10000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def fill(self, selector: str, text: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.fill(selector, text, timeout=10000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def select_option(self, selector: str, value: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.select_option(selector, value=value, timeout=10000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def hover(self, selector: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.hover(selector, timeout=5000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def drag_and_drop(self, source: str, target: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.drag_and_drop(source, target, timeout=10000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== EXTRACTION =====
    
    async def extract(self, selector: str, attribute: str = "text", 
                      context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
            if attribute == "text":
                value = await element.text_content()
            elif attribute == "html":
                value = await element.inner_html()
            elif attribute == "outer_html":
                value = await element.evaluate("el => el.outerHTML")
            else:
                value = await element.get_attribute(attribute)
            return {"success": True, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def extract_table(self, selector: str, context_id: str = "default") -> Dict:
        """Extract HTML table as structured data"""
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            data = await page.evaluate(f"""
                () => {{
                    const table = document.querySelector('{selector}');
                    if (!table) return null;
                    const rows = Array.from(table.querySelectorAll('tr'));
                    return rows.map(row => 
                        Array.from(row.querySelectorAll('th, td')).map(cell => cell.textContent.trim())
                    );
                }}
            """)
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, script: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            result = await page.evaluate(script)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== VISUAL EVIDENCE =====
    
    async def screenshot(self, full_page: bool = False, context_id: str = "default",
                         path: str = None) -> bytes:
        page = self.pages.get(context_id)
        if not page:
            raise ValueError("No active page")
        
        return await page.screenshot(full_page=full_page, path=path, type="png")
    
    async def screenshot_element(self, selector: str, context_id: str = "default") -> bytes:
        page = self.pages.get(context_id)
        if not page:
            raise ValueError("No active page")
        
        element = await page.wait_for_selector(selector, timeout=5000)
        return await element.screenshot(type="png")
    
    # ===== WAIT STRATEGIES =====
    
    async def wait_for_selector(self, selector: str, context_id: str = "default",
                                state: str = "visible", timeout: int = 10000) -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.wait_for_selector(selector, state=state, timeout=timeout)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def wait_for_navigation(self, context_id: str = "default",
                                  wait_until: str = "networkidle", timeout: int = 30000) -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.wait_for_load_state(wait_until, timeout=timeout)
            return {"success": True, "url": page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== TRACING =====
    
    async def trace_start(self, context_id: str = "default", 
                          screenshots: bool = True, snapshots: bool = True) -> Dict:
        context = self.contexts.get(context_id)
        if not context:
            return {"success": False, "error": "Context not found"}
        
        await context.tracing.start(screenshots=screenshots, snapshots=snapshots, sources=True)
        return {"success": True}
    
    async def trace_stop(self, path: str, context_id: str = "default") -> Dict:
        context = self.contexts.get(context_id)
        if not context:
            return {"success": False, "error": "Context not found"}
        
        await context.tracing.stop(path=path)
        return {"success": True, "trace_path": path}
    
    # ===== DOWNLOAD/UPLOAD =====
    
    async def download_file(self, url: str, save_path: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            async with page.expect_download() as download_info:
                await page.goto(url)
            download = await download_info.value
            await download.save_as(save_path)
            return {"success": True, "path": save_path}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def upload_file(self, selector: str, file_path: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.set_input_files(selector, file_path, timeout=10000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== IFRAME/SHADOW DOM =====
    
    async def iframe_selector(self, frame_selector: str, element_selector: str,
                              context_id: str = "default") -> Dict:
        """Get element within iframe"""
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            frame = page.frame_locator(frame_selector)
            element = frame.locator(element_selector)
            return {"success": True, "element": element}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def shadow_dom_eval(self, selector: str, script: str, context_id: str = "default") -> Dict:
        """Execute script in shadow DOM context"""
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            result = await page.evaluate(f"""
                () => {{
                    const host = document.querySelector('{selector}');
                    if (!host || !host.shadowRoot) return null;
                    return (function() {{ {script} }})();
                }}
            """)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ===== LOGS =====
    
    async def get_console_logs(self, context_id: str = "default") -> List[Dict]:
        return self.console_logs.get(context_id, [])
    
    async def get_network_logs(self, context_id: str = "default") -> List[Dict]:
        return self.network_logs.get(context_id, [])
```

### 4.2 Playwright Configuration

```python
@dataclass
class PlaywrightConfig:
    # Browser defaults
    default_browser: str = "chromium"
    default_channel: str = None  # "chrome", "msedge"
    headless: bool = False
    
    # Viewport
    viewport: Dict = field(default_factory=lambda: {"width": 1920, "height": 1080})
    
    # Timeouts
    navigation_timeout: int = 30000
    action_timeout: int = 10000
    
    # Tracing
    trace_screenshots: bool = True
    trace_snapshots: bool = True
    trace_sources: bool = True
    
    # Permissions
    auto_grant_permissions: List[str] = field(default_factory=lambda: [
        "geolocation", "notifications", "camera", "microphone"
    ])
    
    # Downloads
    download_dir: str = "data/downloads"
    accept_downloads: bool = True
    
    # Stealth
    stealth_mode: bool = True
    user_agent: str = None  # Auto
```

---

## 5. Computer Vision / OCR Fallback

### 5.1 When CV/OCR is Used

| Scenario | Primary Method | Fallback |
|----------|----------------|----------|
| Element not in UIA tree | UIA → Accessibility | CV/OCR |
| Custom-drawn controls (games, CAD) | N/A | CV/OCR |
| Remote desktop / VM | UIA (if accessible) | CV/OCR |
| Image-based verification | N/A | CV/OCR |
| Text in images/PDFs | N/A | OCR |

### 5.2 CV/OCR Implementation

```python
# src/arise/adapters/computer_vision.py
import cv2
import numpy as np
import pytesseract
from PIL import Image
import mss
from typing import Dict, List, Any, Optional
from .ports import AdapterPort, AdapterCapability

class ComputerVisionAdapter(AdapterPort):
    """Computer Vision and OCR fallback for desktop automation"""
    
    name = "computer_vision"
    
    def __init__(self, config: CVConfig = None):
        self.config = config or CVConfig()
        self.tesseract_cmd = config.tesseract_path or "tesseract"
    
    @property
    def capabilities(self) -> List[AdapterCapability]:
        return [
            AdapterCapability("find_image", "Find image on screen", "R0", ["cv.read"]),
            AdapterCapability("find_text", "Find text on screen (OCR)", "R0", ["cv.read"]),
            AdapterCapability("click_image", "Click at image location", "R1", ["cv.click"]),
            AdapterCapability("click_text", "Click at text location", "R1", ["cv.click"]),
            AdapterCapability("capture_screen", "Capture screen region", "R0", ["cv.read"]),
            AdapterCapability("compare_images", "Compare two images", "R0", ["cv.read"]),
            AdapterCapability("wait_for_image", "Wait for image to appear", "R0", ["cv.read"]),
            AdapterCapability("wait_for_text", "Wait for text to appear", "R0", ["cv.read"]),
        ]
    
    async def health_check(self) -> bool:
        try:
            # Test Tesseract
            import pytesseract
            pytesseract.get_tesseract_version()
            # Test screen capture
            with mss.mss() as sct:
                sct.grab(sct.monitors[0])
            return True
        except Exception:
            return False
    
    async def close(self):
        pass
    
    # ===== SCREEN CAPTURE =====
    
    async def capture_screen(self, region: Dict = None) -> bytes:
        """Capture screen or region"""
        with mss.mss() as sct:
            if region:
                monitor = {
                    "left": region["x"],
                    "top": region["y"],
                    "width": region["width"],
                    "height": region["height"],
                }
            else:
                monitor = sct.monitors[0]  # Full screen
            img = sct.grab(monitor)
            return bytes(img.rgb)
    
    async def capture_window(self, window_handle: int) -> bytes:
        """Capture specific window"""
        import win32gui
        import win32ui
        import win32con
        
        try:
            # Get window rect
            rect = win32gui.GetWindowRect(window_handle)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            
            # Capture
            hwndDC = win32gui.GetWindowDC(window_handle)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
            saveDC.SelectObject(saveBitMap)
            saveDC.BitBlt((0, 0), (w, h), mfcDC, (0, 0), win32con.SRCCOPY)
            
            # Convert to bytes
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )
            
            # Cleanup
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(window_handle, hwndDC)
            
            return img.tobytes()
        except Exception as e:
            raise CVError(f"Window capture failed: {e}")
    
    # ===== TEMPLATE MATCHING =====
    
    async def find_image(self, template_bytes: bytes, threshold: float = 0.8,
                         region: Dict = None) -> Dict:
        """Find template image on screen"""
        screen_bytes = await self.capture_screen(region)
        
        # Convert to OpenCV
        screen = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
        template = cv2.imdecode(np.frombuffer(template_bytes, np.uint8), cv2.IMREAD_COLOR)
        
        if screen is None or template is None:
            return {"found": False, "error": "Image decode failed"}
        
        # Match template
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            h, w = template.shape[:2]
            x, y = max_loc
            if region:
                x += region["x"]
                y += region["y"]
            return {
                "found": True,
                "confidence": float(max_val),
                "location": {"x": x, "y": y, "width": w, "height": h},
                "center": {"x": x + w//2, "y": y + h//2},
            }
        return {"found": False, "confidence": float(max_val)}
    
    async def find_text(self, text: str, region: Dict = None, 
                        lang: str = "eng") -> Dict:
        """Find text on screen using OCR"""
        screen_bytes = await self.capture_screen(region)
        
        # Convert to PIL for Tesseract
        screen = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
        pil_img = Image.fromarray(cv2.cvtColor(screen, cv2.COLOR_BGR2RGB))
        
        # OCR with bounding boxes
        data = pytesseract.image_to_data(pil_img, lang=lang, output_type=pytesseract.Output.DICT)
        
        matches = []
        for i, detected in enumerate(data['text']):
            if text.lower() in detected.lower() and int(data['conf'][i]) > 30:
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                if region:
                    x += region["x"]
                    y += region["y"]
                matches.append({
                    "text": detected,
                    "confidence": data['conf'][i] / 100.0,
                    "location": {"x": x, "y": y, "width": w, "height": h},
                    "center": {"x": x + w//2, "y": y + h//2},
                })
        
        if matches:
            return {"found": True, "matches": matches}
        return {"found": False, "matches": []}
    
    # ===== CLICK ACTIONS =====
    
    async def click_image(self, template_bytes: bytes, threshold: float = 0.8,
                          region: Dict = None, button: str = "left") -> Dict:
        """Find and click image"""
        result = await self.find_image(template_bytes, threshold, region)
        if result["found"]:
            await self._click_at(result["center"]["x"], result["center"]["y"], button)
            return {"success": True, "location": result["location"]}
        return {"success": False, "error": "Image not found"}
    
    async def click_text(self, text: str, region: Dict = None, 
                         lang: str = "eng", button: str = "left") -> Dict:
        """Find and click text"""
        result = await self.find_text(text, region, lang)
        if result["found"]:
            # Click first match
            match = result["matches"][0]
            await self._click_at(match["center"]["x"], match["center"]["y"], button)
            return {"success": True, "location": match["location"]}
        return {"success": False, "error": "Text not found"}
    
    async def _click_at(self, x: int, y: int, button: str = "left"):
        import pyautogui
        pyautogui.click(x, y, button=button)
    
    # ===== WAIT =====
    
    async def wait_for_image(self, template_bytes: bytes, threshold: float = 0.8,
                             timeout: float = 10, interval: float = 0.5) -> Dict:
        import time
        start = time.time()
        while time.time() - start < timeout:
            result = await self.find_image(template_bytes, threshold)
            if result["found"]:
                return result
            await asyncio.sleep(interval)
        return {"found": False, "error": "Timeout"}
    
    async def wait_for_text(self, text: str, timeout: float = 10,
                            interval: float = 0.5, lang: str = "eng") -> Dict:
        import time
        start = time.time()
        while time.time() - start < timeout:
            result = await self.find_text(text, lang=lang)
            if result["found"]:
                return result
            await asyncio.sleep(interval)
        return {"found": False, "error": "Timeout"}
    
    # ===== IMAGE COMPARISON =====
    
    async def compare_images(self, img1_bytes: bytes, img2_bytes: bytes) -> Dict:
        """Compare two images, return similarity"""
        img1 = cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR)
        img2 = cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR)
        
        if img1 is None or img2 is None:
            return {"similarity": 0, "error": "Decode failed"}
        
        # Resize to same size
        if img1.shape != img2.shape:
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
        
        # Structural Similarity Index (SSIM)
        from skimage.metrics import structural_similarity as ssim
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        similarity = ssim(gray1, gray2)
        
        return {"similarity": float(similarity), "identical": similarity > 0.99}
```

---

## 6. Perception Hierarchy & Fallback Chain

### 6.1 Resolution Strategy

```python
class PerceptionResolver:
    """Resolves UI elements through perception hierarchy"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.uia = runtime.adapters.get("windows_uia")
        self.playwright = runtime.adapters.get("playwright")
        self.cv = runtime.adapters.get("computer_vision")
    
    async def resolve_element(self, selector: Dict) -> ElementResolution:
        """Try each perception method in order"""
        
        # 1. Try UIA (native apps)
        if selector.get("backend") in [None, "uia", "auto"]:
            result = await self._try_uia(selector)
            if result.success:
                return result
        
        # 2. Try Playwright (web/Electron)
        if selector.get("backend") in [None, "playwright", "auto"]:
            result = await self._try_playwright(selector)
            if result.success:
                return result
        
        # 3. Try Accessibility (fallback for UIA)
        result = await self._try_accessibility(selector)
        if result.success:
            return result
        
        # 4. Try Computer Vision (last resort)
        if selector.get("image_template") or selector.get("text"):
            result = await self._try_cv(selector)
            if result.success:
                return result
        
        return ElementResolution(success=False, error="All perception methods failed")
    
    async def _try_uia(self, selector: Dict) -> ElementResolution:
        try:
            element = await self.uia._resolve_element(selector)
            if element and element.Exists(0):
                return ElementResolution(
                    success=True,
                    backend="uia",
                    element_ref=element,
                    metadata={"rect": element.BoundingRectangle}
                )
        except Exception as e:
            pass
        return ElementResolution(success=False, error="UIA resolution failed")
    
    async def _try_playwright(self, selector: Dict) -> ElementResolution:
        try:
            context_id = selector.get("context_id", "default")
            page = self.playwright.pages.get(context_id)
            if page:
                element = await page.wait_for_selector(selector["css"], timeout=2000)
                if element:
                    box = await element.bounding_box()
                    return ElementResolution(
                        success=True,
                        backend="playwright",
                        element_ref=element,
                        metadata={"box": box}
                    )
        except Exception:
            pass
        return ElementResolution(success=False, error="Playwright resolution failed")
    
    async def _try_accessibility(self, selector: Dict) -> ElementResolution:
        # Use UIA with different search strategies
        try:
            # Try by name only
            search_props = {"Name": selector.get("name", "")}
            element = auto.GetRootControl().FindFirst(**search_props)
            if element and element.Exists(0):
                return ElementResolution(
                    success=True,
                    backend="accessibility",
                    element_ref=element,
                )
        except Exception:
            pass
        return ElementResolution(success=False, error="Accessibility resolution failed")
    
    async def _try_cv(self, selector: Dict) -> ElementResolution:
        try:
            if "image_template" in selector:
                result = await self.cv.find_image(selector["image_template"])
            elif "text" in selector:
                result = await self.cv.find_text(selector["text"])
            else:
                return ElementResolution(success=False, error="No CV selector")
            
            if result["found"]:
                return ElementResolution(
                    success=True,
                    backend="computer_vision",
                    metadata=result,
                )
        except Exception as e:
            pass
        return ElementResolution(success=False, error="CV resolution failed")
```

---

## 7. Evidence & Observability

### 7.1 Evidence Capture

```python
class AutomationEvidence:
    """Captures evidence for automation actions"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.evidence_dir = runtime.settings.data_dir / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
    
    async def capture_action_evidence(
        self,
        task_id: str,
        step_id: str,
        action: str,
        backend: str,
        before_state: Dict,
        after_state: Dict,
        selector: Dict,
        result: Dict,
    ) -> EvidenceRecord:
        """Capture comprehensive evidence for an automation action"""
        
        evidence_id = f"ev_{uuid4().hex[:12]}"
        timestamp = datetime.utcnow()
        
        # Screenshots
        before_screenshot = before_state.get("screenshot")
        after_screenshot = after_state.get("screenshot")
        
        # Save screenshots
        before_path = None
        after_path = None
        if before_screenshot:
            before_path = await self._save_screenshot(before_screenshot, f"{evidence_id}_before.png")
        if after_screenshot:
            after_path = await self._save_screenshot(after_screenshot, f"{evidence_id}_after.png")
        
        # Create evidence record
        record = EvidenceRecord(
            id=evidence_id,
            task_id=task_id,
            step_id=step_id,
            type=EvidenceType.ACTION,
            source=backend,
            content=f"{action} via {backend}: {json.dumps(selector)}",
            data_ref=after_path or before_path,
            metadata={
                "action": action,
                "backend": backend,
                "selector": selector,
                "result": result,
                "before_state": before_state,
                "after_state": after_state,
                "before_screenshot": before_path,
                "after_screenshot": after_path,
            },
            timestamp=timestamp,
            hash=self._compute_hash(evidence_id, action, selector, result),
        )
        
        # Store
        await self.runtime.evidence_store.add(record)
        
        return record
    
    async def _save_screenshot(self, image_bytes: bytes, filename: str) -> str:
        path = self.evidence_dir / filename
        path.write_bytes(image_bytes)
        return str(path)
```

---

## 8. Cross-App Coordination

### 8.1 Multi-Window Workflows

```python
class CrossAppCoordinator:
    """Coordinates automation across multiple applications"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.uia = runtime.adapters.get("windows_uia")
        self.playwright = runtime.adapters.get("playwright")
    
    async def copy_paste_between_apps(
        self,
        source_selector: Dict,
        target_selector: Dict,
        source_backend: str = "uia",
        target_backend: str = "uia",
    ) -> Dict:
        """Copy from one app, paste to another"""
        
        # Get text from source
        if source_backend == "uia":
            source_result = await self.uia.get_text(source_selector)
        else:
            source_result = await self.playwright.extract(source_selector.get("css"), "text")
        
        if not source_result.get("success"):
            return {"success": False, "error": "Failed to copy from source"}
        
        text = source_result.get("text", "")
        
        # Paste to target
        if target_backend == "uia":
            target_result = await self.uia.type_text(target_selector, text)
        else:
            target_result = await self.playwright.type(target_selector.get("css"), text)
        
        return {"success": target_result.get("success"), "text_length": len(text)}
    
    async def drag_drop_between_windows(
        self,
        source_window: str,
        source_selector: Dict,
        target_window: str,
        target_selector: Dict,
    ) -> Dict:
        """Drag from one window, drop to another"""
        
        # Focus source window
        await self.uia.set_focus(source_window)
        await asyncio.sleep(0.2)
        
        # Get source element position
        source_element = await self.uia._resolve_element(source_selector)
        if not source_element:
            return {"success": False, "error": "Source element not found"}
        
        source_rect = source_element.BoundingRectangle
        source_center = (source_rect.left + source_rect.width() // 2, 
                         source_rect.top + source_rect.height() // 2)
        
        # Focus target window
        await self.uia.set_focus(target_window)
        await asyncio.sleep(0.2)
        
        # Get target position
        target_element = await self.uia._resolve_element(target_selector)
        if not target_element:
            return {"success": False, "error": "Target element not found"}
        
        target_rect = target_element.BoundingRectangle
        target_center = (target_rect.left + target_rect.width() // 2,
                         target_rect.top + target_rect.height() // 2)
        
        # Perform drag-drop
        import pyautogui
        pyautogui.moveTo(source_center[0], source_center[1])
        pyautogui.mouseDown()
        pyautogui.moveTo(target_center[0], target_center[1], duration=0.5)
        pyautogui.mouseUp()
        
        return {"success": True}
```

---

## 9. Configuration

```toml
# config/desktop_automation.toml

[uia]
default_search_depth = 10
default_wait_timeout = 10.0
click_method_priority = ["invoke", "legacy", "mouse"]
type_method_priority = ["value_pattern", "send_keys"]
capture_before_after = true
element_cache_ttl = 5.0
max_retries = 3
retry_backoff = 0.5

[playwright]
default_browser = "chromium"
headless = false
viewport = {width = 1920, height = 1080}
navigation_timeout = 30000
action_timeout = 10000
trace_screenshots = true
trace_snapshots = true
stealth_mode = true

[computer_vision]
tesseract_path = "tesseract"
ocr_languages = ["eng", "tel"]
template_match_threshold = 0.8
ocr_confidence_threshold = 30

[perception_hierarchy]
order = ["uia", "playwright", "accessibility", "computer_vision"]
fallback_on_failure = true
log_fallbacks = true

[evidence]
capture_screenshots = true
screenshot_format = "png"
capture_before_after = true
store_console_logs = true
store_network_logs = true
retention_days = 90

[cross_app]
clipboard_sync_delay = 0.2
window_focus_delay = 0.2
drag_drop_duration = 0.5
```

---

## 10. Testing Strategy

### 10.1 Unit Tests

```python
# tests/desktop/test_uia_adapter.py

async def test_uia_launch_notepad(uia_adapter):
    result = await uia_adapter.launch_app("notepad")
    assert result["success"]
    assert "process_id" in result
    assert "window_handle" in result
    
    # Cleanup
    await uia_adapter.send_keys("ctrl+w")  # Close notepad

async def test_uia_find_window(uia_adapter):
    await uia_adapter.launch_app("notepad")
    await asyncio.sleep(1)
    
    result = await uia_adapter.find_window(title="Notepad")
    assert result["found"]
    assert result["title"] == "Notepad"
    assert "handle" in result

async def test_uia_click_button(uia_adapter):
    # Test with a known dialog (e.g., Notepad save dialog)
    await uia_adapter.launch_app("notepad")
    await uia_adapter.type_text({"name": "Text Editor"}, "Test content")
    
    # Trigger save dialog
    await uia_adapter.send_keys("ctrl+s")
    await asyncio.sleep(0.5)
    
    # Click Save button
    result = await uia_adapter.click_element({
        "name": "Save",
        "control_type": "ButtonControl"
    })
    assert result["success"]

async def test_uia_type_text(uia_adapter):
    await uia_adapter.launch_app("notepad")
    await asyncio.sleep(0.5)
    
    result = await uia_adapter.type_text(
        {"name": "Text Editor", "control_type": "EditControl"},
        "Hello, ARISE!"
    )
    assert result["success"]
    
    # Verify
    text_result = await uia_adapter.get_text({"name": "Text Editor"})
    assert "Hello, ARISE!" in text_result.get("text", "")
```

### 10.2 Integration Tests

| Test | Scenario | Validation |
|------|----------|------------|
| `test_notepad_full_flow` | Launch → Type → Save → Close | File exists with content |
| `test_chrome_automation` | Launch Chrome → Navigate → Extract | Page title, content extracted |
| `test_cross_app_copy_paste` | Notepad → Chrome | Text transferred |
| `test_fallback_chain` | Element not in UIA → Playwright → CV | Action succeeds |
| `test_evidence_capture` | Every action | Screenshots, logs saved |

---

## 11. Open Desktop Automation Decisions

| Decision | Options | Considerations |
|----------|---------|----------------|
| UIA library | `uiautomation` / `comtypes` direct / `pywinauto` only | `uiautomation` is more Pythonic, `comtypes` more control |
| Playwright mode | Persistent context / CDP attach / New context | Persistent: keeps login; CDP: attaches to running |
| CV engine | OpenCV+Tesseract / ONNX models / Windows ML | OpenCV: mature; ONNX: faster; Windows ML: native |
| Coordinate system | Physical pixels / Logical / DPI-aware | DPI-aware for multi-monitor |
| Element caching | None / TTL / Invalidation on action | TTL simpler, invalidation more accurate |
| Screenshot storage | Files / Database / Compressed | Files simpler, DB queryable |
| Multi-monitor | Primary only / All / Specific | All monitors for flexibility |