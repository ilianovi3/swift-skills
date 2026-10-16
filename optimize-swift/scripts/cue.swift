// cue "<text with optional %d>" <seconds> — a dark label in the top-right corner of the main screen for N seconds;
// %d becomes a live countdown (N…1). Separate process: takes no focus, ignores the mouse, shows on every Space, does
// not disturb measurements of the app under test. Long text shrinks 20→13 pt, then wraps and the panel grows down.
// Build: swiftc -O cue.swift -o cue
import AppKit
let a = CommandLine.arguments
let text = a[1], total = Int(a[2]) ?? 3
let inner: CGFloat = 340, pad: CGFloat = 14
func font(_ size: CGFloat) -> NSFont { .systemFont(ofSize: size, weight: .semibold) }
// Measure the widest countdown value so the font size does not jump every second.
let probe = text.replacingOccurrences(of: "%d", with: "\(total)") as NSString
var size: CGFloat = 20
while size > 13, probe.size(withAttributes: [.font: font(size)]).width > inner { size -= 0.5 }
let textHeight = ceil(probe.boundingRect(with: NSSize(width: inner, height: .greatestFiniteMagnitude),
                                         options: [.usesLineFragmentOrigin, .usesFontLeading],
                                         attributes: [.font: font(size)]).height)
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: inner + 2 * 10, height: textHeight + 2 * pad),
                    styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: false)
panel.level = .statusBar
panel.isOpaque = false
panel.backgroundColor = NSColor.black.withAlphaComponent(0.82)
panel.ignoresMouseEvents = true
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
let label = NSTextField(wrappingLabelWithString: "")
label.font = font(size)
label.textColor = .white
label.alignment = .center
label.maximumNumberOfLines = 0
label.preferredMaxLayoutWidth = inner
label.frame = NSRect(x: 10, y: pad, width: inner, height: textHeight)
panel.contentView?.addSubview(label)
if let s = NSScreen.main?.visibleFrame {
    panel.setFrameOrigin(NSPoint(x: s.maxX - panel.frame.width - 16, y: s.maxY - panel.frame.height - 16))
}
var left = total
label.stringValue = text.replacingOccurrences(of: "%d", with: "\(left)")
panel.orderFrontRegardless()
Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
    left -= 1
    if left <= 0 { app.terminate(nil) }
    label.stringValue = text.replacingOccurrences(of: "%d", with: "\(left)")
}
app.run()
