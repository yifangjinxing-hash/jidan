import CoreGraphics
import Foundation
import ImageIO

private let sampleWidth = 72
private let sampleHeight = 156

private func pixels(at path: String) -> [UInt8] {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        fatalError("Cannot load screenshot: \(path)")
    }

    var bytes = [UInt8](repeating: 0, count: sampleWidth * sampleHeight * 4)
    bytes.withUnsafeMutableBytes { storage in
        guard let context = CGContext(
            data: storage.baseAddress,
            width: sampleWidth,
            height: sampleHeight,
            bitsPerComponent: 8,
            bytesPerRow: sampleWidth * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else {
            fatalError("Cannot create screenshot comparison context")
        }
        context.interpolationQuality = .medium
        context.draw(image, in: CGRect(x: 0, y: 0, width: sampleWidth, height: sampleHeight))
    }
    return bytes
}

private func meanRGBDifference(_ left: [UInt8], _ right: [UInt8]) -> Double {
    precondition(left.count == right.count)
    var total = 0
    for index in stride(from: 0, to: left.count, by: 4) {
        total += abs(Int(left[index]) - Int(right[index]))
        total += abs(Int(left[index + 1]) - Int(right[index + 1]))
        total += abs(Int(left[index + 2]) - Int(right[index + 2]))
    }
    return Double(total) / Double((left.count / 4) * 3)
}

private func changedPixelFraction(_ left: [UInt8], _ right: [UInt8], threshold: Int = 8) -> Double {
    precondition(left.count == right.count)
    var changed = 0
    for index in stride(from: 0, to: left.count, by: 4) {
        let redDifference = abs(Int(left[index]) - Int(right[index]))
        let greenDifference = abs(Int(left[index + 1]) - Int(right[index + 1]))
        let blueDifference = abs(Int(left[index + 2]) - Int(right[index + 2]))
        let maximumChannelDifference = max(redDifference, max(greenDifference, blueDifference))
        if maximumChannelDifference > threshold {
            changed += 1
        }
    }
    return Double(changed) / Double(left.count / 4)
}

guard CommandLine.arguments.count == 4 else {
    fatalError("usage: verify_screenshots.swift HOME SETTINGS ALIPAY")
}

let home = pixels(at: CommandLine.arguments[1])
let settings = pixels(at: CommandLine.arguments[2])
let alipay = pixels(at: CommandLine.arguments[3])
let settingsDifference = meanRGBDifference(home, settings)
let alipayDifference = meanRGBDifference(home, alipay)
let settingsChangedFraction = changedPixelFraction(home, settings)
let alipayChangedFraction = changedPixelFraction(home, alipay)
let settingsAlipayChangedFraction = changedPixelFraction(settings, alipay)

print(String(format: "home_to_settings_mean_rgb_difference=%.3f", settingsDifference))
print(String(format: "home_to_alipay_mean_rgb_difference=%.3f", alipayDifference))
print(String(format: "home_to_settings_changed_pixel_fraction=%.5f", settingsChangedFraction))
print(String(format: "home_to_alipay_changed_pixel_fraction=%.5f", alipayChangedFraction))
print(String(format: "settings_to_alipay_changed_pixel_fraction=%.5f", settingsAlipayChangedFraction))

guard settingsDifference >= 8, settingsChangedFraction >= 0.01 else {
    fatalError("Settings screenshot still looks like Jidan home")
}
guard alipayDifference >= 0.3, alipayChangedFraction >= 0.01 else {
    fatalError("Alipay-unavailable screenshot still looks like Jidan home")
}
guard settingsAlipayChangedFraction >= 0.01 else {
    fatalError("Settings and Alipay-unavailable screenshots look alike")
}
