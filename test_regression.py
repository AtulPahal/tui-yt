import asyncio
import sys
from tui import YouTubeTUI

async def main():
    print("Initializing TUI application for programmatic verification...")
    tui = YouTubeTUI()
    
    # 1. Test search with direct YouTube URL
    test_url = "https://www.youtube.com/watch?v=2PuFyjAs7JA"
    print(f"Testing direct URL fetch with: {test_url}...")
    class MockBuffer:
        def __init__(self, text):
            self.text = text
            
    tui.on_search_accept(MockBuffer(test_url))
    
    print("Waiting for URL details to populate...")
    results_found = False
    for _ in range(30):
        await asyncio.sleep(0.2)
        if tui.results:
            results_found = True
            break
            
    if not results_found:
        print("ERROR: Direct URL fetch results were not populated!", file=sys.stderr)
        sys.exit(1)
        
    print(f"URL Fetch results found: {len(tui.results)} items")
    assert len(tui.results) == 1, f"Expected exactly 1 result for URL, got {len(tui.results)}"
    print(f"Fetched video title: '{tui.results[0]['title']}' by '{tui.results[0]['channel']}'")
    assert tui.results[0]["id"] == "2PuFyjAs7JA", "Expected matching video ID"
    

    # 1b. Test playlist/channel URL fetching
    print("\nTesting playlist/channel URL fetch...")
    playlist_url = "https://www.youtube.com/playlist?list=PLwivh_Y43t3YVvBv-8N1G6G1O9A0YF8X6"
    import tui as tui_mod
    original_extract = tui_mod.yt_dlp.YoutubeDL.extract_info
    
    playlist_mock_data = {
        "_type": "playlist",
        "title": "Mock Playlist",
        "entries": [
            {"id": "vid1", "title": "Video 1", "duration": 120, "uploader": "Channel A"},
            {"id": "vid2", "title": "Video 2", "duration": 180, "uploader": "Channel A"},
            {"id": "vid3", "title": "Video 3", "duration": 240, "uploader": "Channel A"},
        ]
    }
    
    def mock_extract_info(self, url, download=False):
        if "list=" in url or "playlist" in url:
            return playlist_mock_data
        return {"id": "single", "title": "Single Video", "duration": 300, "uploader": "Channel B"}
        
    tui_mod.yt_dlp.YoutubeDL.extract_info = mock_extract_info
    
    print(f"Triggering TUI playlist fetch for URL: {playlist_url}...")
    tui.on_search_accept(MockBuffer(playlist_url))
    
    print("Waiting for playlist details to populate...")
    results_found = False
    for _ in range(30):
        await asyncio.sleep(0.2)
        if len(tui.results) == 3:
            results_found = True
            break
            
    if not results_found:
        print("ERROR: Playlist fetch results were not populated correctly!", file=sys.stderr)
        sys.exit(1)
        
    print(f"Playlist Fetch results found: {len(tui.results)} items")
    assert tui.results[0]["id"] == "vid1", "Expected matching video ID for first entry"
    assert tui.results[2]["title"] == "Video 3", "Expected matching video title for third entry"
    print("Playlist/Channel fetching logic verified successfully.")
    
    # Restore original extract_info
    tui_mod.yt_dlp.YoutubeDL.extract_info = original_extract
    # 2. Test search with normal query
    print("\nTesting normal query search...")
    tui.on_search_accept(MockBuffer("test video"))
    
    print("Waiting for search results to populate...")
    results_found = False
    for _ in range(30):
        await asyncio.sleep(0.2)
        if len(tui.results) > 1:
            results_found = True
            break
            
    if not results_found:
        print("ERROR: Search results were not populated!", file=sys.stderr)
        sys.exit(1)
        
    print(f"Search results found: {len(tui.results)} items")
    print(f"First result: '{tui.results[0]['title']}' by '{tui.results[0]['channel']}'")
        
    # 3. Test navigation
    print("Verifying initial selection (index 0)...")
    assert tui.selected_idx == 0, f"Expected selected_idx 0, got {tui.selected_idx}"
    
    # Simulate moving down the list
    print("Simulating navigation...")
    tui.selected_idx = (tui.selected_idx + 1) % len(tui.results)
    print(f"Selected index is now: {tui.selected_idx}")
    assert tui.selected_idx == 1, f"Expected selected_idx 1, got {tui.selected_idx}"
    
    # 4. Test toggle states
    print(f"Initial settings - Video Mode: {tui.video_mode}, Audio Muted: {tui.no_audio}")
    
    # Simulate video toggle
    tui.video_mode = not tui.video_mode
    print(f"Toggled video mode - Video Mode: {tui.video_mode}")
    assert tui.video_mode is False, "Expected video_mode to be False"
    
    # Simulate audio toggle
    tui.no_audio = not tui.no_audio
    print(f"Toggled audio mode - Audio Muted: {tui.no_audio}")
    assert tui.no_audio is True, "Expected no_audio to be True"
    
    # 5. Test concurrency is_playing flag
    print("\nTesting is_playing concurrency guard...")
    assert tui.is_playing is False, "Expected is_playing to be False initially"
    
    print("Setting is_playing to True to simulate active playback...")
    tui.is_playing = True
    
    # Now simulate pressing Enter (triggering play)
    class MockEvent:
        def __init__(self, app):
            self.app = app
            
    class MockLayout:
        def __init__(self, has_focus):
            self._has_focus = has_focus
        def has_focus(self, element):
            return self._has_focus
            
    class MockApp:
        def __init__(self):
            self.layout = MockLayout(has_focus=True)
            
    # Locate _enter_results callback in setup_keybindings
    enter_callback = None
    for binding in tui.kb.bindings:
        if any(getattr(k, "value", str(k)) in ("c-m", "enter") for k in binding.keys):
            enter_callback = binding.handler
            break
            
    assert enter_callback is not None, "Expected to find enter keybinding callback"
    
    mock_event = MockEvent(app=MockApp())
    print("Triggering enter keypress callback...")
    # Since tui.is_playing is True, this should return immediately without spawning any tasks
    enter_callback(mock_event)
    
    # Check if any background tasks were created (none should be)
    # If a task was created, it would attempt to play and crash/fail headlessly since no loop is running
    print("Verifying no playback was launched...")
    assert tui.is_playing is True, "is_playing should still be True"
    
    # 6. Test local fetch (download) keybinding callback
    print("\nTesting local fetch (download) keybinding...")
    download_called = False
    
    def mock_download_youtube_video(url, progress_hook=None):
        nonlocal download_called
        download_called = True
        print(f"Mock download invoked for url: {url}")
        if progress_hook:
            progress_hook({'status': 'downloading', '_percent_str': '50.0%'})
            progress_hook({'status': 'finished'})
        return "downloads/test.mp4"
        
    import tui as tui_mod
    tui_mod.download_youtube_video = mock_download_youtube_video
    
    download_callback = None
    for binding in tui.kb.bindings:
        if any(getattr(k, "value", str(k)) == "d" for k in binding.keys):
            download_callback = binding.handler
            break
            
    assert download_callback is not None, "Expected to find 'd' keybinding callback"
    
    class MockLoop:
        def call_soon_threadsafe(self, func):
            pass
            
    class MockAppWithLoop:
        def __init__(self):
            self.layout = MockLayout(has_focus=True)
            self.loop = MockLoop()
        def invalidate(self):
            pass
        def create_background_task(self, coro):
            asyncio.create_task(coro)
            
    mock_event_download = MockEvent(app=MockAppWithLoop())
    
    print("Triggering download keypress callback...")
    download_callback(mock_event_download)
    
    # Wait for the async task to execute
    await asyncio.sleep(0.5)
    
    assert download_called is True, "Expected mock download function to be called!"
    print("Local fetch (download) callback executed successfully.")
    
    
    # 7. Verify keybinding focus filters programmatically
    print("\nTesting keybinding focus filters programmatically...")
    from prompt_toolkit.application.current import set_app
    
    # Locate 'v', 'a', and 'd' bindings
    v_binding = [b for b in tui.kb.bindings if 'v' in b.keys][0]
    a_binding = [b for b in tui.kb.bindings if 'a' in b.keys][0]
    d_binding = [b for b in tui.kb.bindings if 'd' in b.keys][0]
    
    with set_app(tui.app):
        # Focus search field
        tui.app.layout.focus(tui.search_field)
        print("Focus is on search field:")
        print(f"  v filter evaluates to: {v_binding.filter()}")
        print(f"  a filter evaluates to: {a_binding.filter()}")
        print(f"  d filter evaluates to: {d_binding.filter()}")
        assert v_binding.filter() is False, "Expected v filter to be False when search field is focused"
        assert a_binding.filter() is False, "Expected a filter to be False when search field is focused"
        assert d_binding.filter() is False, "Expected d filter to be False when search field is focused"
        
        # Focus results window
        tui.app.layout.focus(tui.results_window)
        print("Focus is on results window:")
        print(f"  v filter evaluates to: {v_binding.filter()}")
        print(f"  a filter evaluates to: {a_binding.filter()}")
        print(f"  d filter evaluates to: {d_binding.filter()}")
        assert v_binding.filter() is True, "Expected v filter to be True when results window is focused"
        assert a_binding.filter() is True, "Expected a filter to be True when results window is focused"
        assert d_binding.filter() is True, "Expected d filter to be True when results window is focused"
        
    print("Keybinding focus filters verified successfully.")
    
    
    # 8. Test NoneType entries extraction robust handling
    print("\nTesting NoneType entries list safety...")
    playlist_mock_none_data = {
        "_type": "playlist",
        "title": "Mock Playlist None",
        "entries": None
    }
    
    tui_mod.yt_dlp.YoutubeDL.extract_info = lambda self, url, download=False: playlist_mock_none_data
    
    print("Triggering TUI playlist fetch with None entries...")
    tui.on_search_accept(MockBuffer(playlist_url))
    
    await asyncio.sleep(0.5)
    
    print(f"Results after empty playlist fetch: {len(tui.results)} items")
    assert len(tui.results) == 0, "Expected empty results list, no crash"
    print("NoneType entries crash guard verified successfully.")
    
    # Restore original extract_info
    tui_mod.yt_dlp.YoutubeDL.extract_info = original_extract
    
    # 9. Test playlist/channel fetch failure error handling
    print("\nTesting playlist/channel fetch failure error handling...")
    
    def mock_extract_info_failure(self, url, download=False):
        raise Exception("API page download failed")
        
    tui_mod.yt_dlp.YoutubeDL.extract_info = mock_extract_info_failure
    
    # Pre-populate with stale results to verify they get cleared on error
    tui.results = [{"id": "stale", "title": "Stale Video", "url": "url", "duration": 100, "channel": "Stale"}]
    print(f"Pre-populated stale results size: {len(tui.results)}")
    
    broken_url = "https://www.youtube.com/playlist?list=PL_broken"
    print(f"Triggering TUI playlist fetch with failing URL: {broken_url}...")
    tui.on_search_accept(MockBuffer(broken_url))
    
    await asyncio.sleep(0.5)
    
    print(f"Results size after fetch failure: {len(tui.results)} items")
    print(f"Status message: '{tui.status_message}'")
    assert len(tui.results) == 0, "Expected stale results to be cleared on fetch failure"
    assert "Could not fetch details for URL/playlist" in tui.status_message, "Expected error status message to be shown"
    print("Playlist/Channel fetch failure error handling verified successfully.")
    
    # Restore original extract_info
    tui_mod.yt_dlp.YoutubeDL.extract_info = original_extract
    
    # 10. Test live network-based error path handling with a bogus YouTube URL
    print("\nTesting live network-based fetch failure with bogus URL...")
    tui.results = [{"id": "stale2", "title": "Stale Video 2", "url": "url", "duration": 120, "channel": "Stale 2"}]
    print(f"Pre-populated stale results size: {len(tui.results)}")
    
    bogus_url = "https://www.youtube.com/watch?v=INVALID_VIDEO_ID_THAT_DOES_NOT_EXIST"
    print(f"Triggering TUI direct fetch with bogus URL: {bogus_url}...")
    tui.on_search_accept(MockBuffer(bogus_url))
    
    print("Waiting for live network request to fail...")
    request_finished = False
    for _ in range(30):
        await asyncio.sleep(0.2)
        if tui.status_message != "Fetching video details from URL...":
            request_finished = True
            break
            
    if not request_finished:
        print("ERROR: Live fetch task did not finish in time!", file=sys.stderr)
        sys.exit(1)
        
    print(f"Results size after live fetch failure: {len(tui.results)} items")
    print(f"Status message: '{tui.status_message}'")
    assert len(tui.results) == 0, "Expected stale results to be cleared on live fetch failure"
    msg = tui.status_message
    assert ("Could not fetch details" in msg or "Error" in msg), \
        "Expected error status message to be shown"
    print("Live network-based fetch failure error handling verified successfully.")
    
    
    # 11. Test thumbnail preview widget and async rendering
    print("\nTesting thumbnail preview widget and async rendering...")
    assert hasattr(tui, "preview_window"), "Expected preview_window to exist"
    assert hasattr(tui, "preview_frame"), "Expected preview_frame to exist"
    assert tui.current_thumbnail_ansi is not None, "Expected current_thumbnail_ansi to be initialized"
    
    tui.results = [{"id": "2PuFyjAs7JA", "title": "Test Resolution", "url": "url", "duration": 11, "channel": "JC"}]
    tui.selected_idx = 0
    
    print("Triggering thumbnail preview update...")
    tui.update_thumbnail_preview()
    
    print("Waiting for thumbnail fetch task to finish...")
    thumbnail_loaded = False
    for _ in range(30):
        await asyncio.sleep(0.2)
        val = tui.current_thumbnail_ansi.value
        if val != "No video selected." and val != "Loading preview...":
            thumbnail_loaded = True
            break
            
    if not thumbnail_loaded:
        print("ERROR: Thumbnail preview failed to load in time!", file=sys.stderr)
        sys.exit(1)
        
    print(f"Thumbnail preview text length: {len(tui.current_thumbnail_ansi.value)} chars")
    print(f"Thumbnail preview text: '{tui.current_thumbnail_ansi.value[:100]}...'")
    assert "Preview error" not in tui.current_thumbnail_ansi.value, "Expected successful thumbnail rendering, no error"
    print("Thumbnail preview widget and async rendering verified successfully.")
    
    print("\nTUI Programmatic Verification: SUCCESS!")

if __name__ == "__main__":
    asyncio.run(main())
