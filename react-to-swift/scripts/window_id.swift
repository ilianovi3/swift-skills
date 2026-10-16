// window_id PID — prints the CGWindowID of the widest normal-layer on-screen window of the process (0 if none).
import CoreGraphics
import Foundation

let pid = Int32(CommandLine.arguments[1]) ?? 0
let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] ?? []
let width: ([String: Any]) -> CGFloat = { ($0[kCGWindowBounds as String] as? [String: CGFloat])?["Width"] ?? 0 }
let window = list
    .filter { ($0[kCGWindowOwnerPID as String] as? Int32) == pid && ($0[kCGWindowLayer as String] as? Int) == 0 }
    .max { width($0) < width($1) }
print(window?[kCGWindowNumber as String] as? Int ?? 0)
