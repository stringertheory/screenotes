"""The menu bar item on macOS: an icon that opens a popover of recent screenshots, like Screenotate's.

The popover holds a web view of the server's /menu page, which draws the list and the search. The page asks for
anything outside itself, like opening a screenshot in the browser, through a WebKit message handler, so its requests
reach this process directly, never as HTTP a web page could also send.
"""
from urllib.parse import quote

from server.library import IMAGE_ID

SIZE = (360, 520)
HANDLER = 'screenotes'
# Screenotate's own item is a camera, so this one is told apart by the text below the picture.
SYMBOL = 'text.below.photo'
SHOWN = "window.dispatchEvent(new Event('screenotes:shown'))"


def action(message, url: str):
    """What a message from the menu page asks for, as (kind, value): ('browse', address), ('quit', None), or None
    for a message that isn't understood. Messages are {'action': name, 'value': ..., 'mode': ...} with string values
    only, which cross from JavaScript the same on every macOS. A search is of text unless its mode says appearance."""
    if not isinstance(message, dict):
        return None
    name, value = message.get('action'), message.get('value')
    value = value.strip() if isinstance(value, str) else ''
    if name == 'open' and IMAGE_ID.fullmatch(value):
        return 'browse', f'{url}/?image={value}'
    if name == 'search' and value:
        mode = 'visual' if message.get('mode') == 'visual' else 'name'
        return 'browse', f'{url}/?mode={mode}&q={quote(value[:1000])}'
    if name == 'home':
        return 'browse', url
    if name == 'quit':
        return 'quit', None
    return None


def run(name: str, url: str):
    """Show the item and run the app's event loop on this thread, the main one, until Quit. There is no Dock icon."""
    import AppKit
    import Foundation
    import objc
    from PyObjCTools import AppHelper
    import WebKit

    class Controller(Foundation.NSObject, protocols=[objc.protocolNamed('WKScriptMessageHandler')]):
        def prepare(self):
            self.popover = AppKit.NSPopover.alloc().init()
            self.popover.setBehavior_(AppKit.NSPopoverBehaviorTransient)
            self.popover.setAnimates_(True)
            configuration = WebKit.WKWebViewConfiguration.alloc().init()
            configuration.userContentController().addScriptMessageHandler_name_(self, HANDLER)
            frame = Foundation.NSMakeRect(0, 0, *SIZE)
            self.view = WebKit.WKWebView.alloc().initWithFrame_configuration_(frame, configuration)
            # The page leaves its background clear, so the popover's own material shows through, as in native menus.
            self.view.setValue_forKey_(False, 'drawsBackground')
            self.view.loadRequest_(Foundation.NSURLRequest.requestWithURL_(Foundation.NSURL.URLWithString_(f'{url}/menu')))
            content = AppKit.NSViewController.alloc().init()
            content.setView_(self.view)
            self.popover.setContentViewController_(content)
            self.popover.setContentSize_(Foundation.NSMakeSize(*SIZE))
            self.item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSVariableStatusItemLength)
            icon = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(SYMBOL, name)
            icon.setTemplate_(True)
            button = self.item.button()
            button.setImage_(icon)
            button.setToolTip_(name)
            button.setTarget_(self)
            button.setAction_('toggle:')
            return self

        def toggle_(self, sender):
            if self.popover.isShown():
                self.popover.performClose_(sender)
                return
            button = self.item.button()
            self.popover.showRelativeToRect_ofView_preferredEdge_(button.bounds(), button, AppKit.NSMinYEdge)
            # An app without a Dock icon has to come forward itself, or the search field can't take typing.
            AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            self.view.window().makeFirstResponder_(self.view)
            self.view.evaluateJavaScript_completionHandler_(SHOWN, None)

        def userContentController_didReceiveScriptMessage_(self, controller, message):
            body = message.body()
            wanted = action({str(key): str(item) for key, item in body.items()} if isinstance(body, Foundation.NSDictionary) else None, url)
            if wanted is None:
                return
            kind, value = wanted
            if kind == 'quit':
                AppKit.NSApplication.sharedApplication().terminate_(None)
                return
            self.popover.performClose_(None)
            AppKit.NSWorkspace.sharedWorkspace().openURL_(Foundation.NSURL.URLWithString_(value))

    application = AppKit.NSApplication.sharedApplication()
    application.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    # Held for as long as the loop runs, since the status item and popover go when it does.
    _controller = Controller.alloc().init().prepare()
    AppHelper.runEventLoop(installInterrupt=True)
