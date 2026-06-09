// sysaudio-rec: native macOS system-audio recorder.
//
// Captures what the Mac is playing using ScreenCaptureKit (the same engine
// behind the Cmd+Shift+5 system-audio recording), converts it to mono 16 kHz
// 16-bit PCM, and writes a WAV to the path given as the first argument. This
// captures system audio ONLY (the call's far side), never the microphone, and
// it does not reroute the output device, so the speakers and volume keys keep
// working with nothing to configure.
//
// It records until it receives SIGINT or SIGTERM, then finalizes the WAV header
// and exits 0. Any startup failure (including a denied Screen/System-Audio
// Recording permission) is printed to stderr and exits non-zero, so the Python
// caller can surface it.
//
// Build:
//   swiftc -O -o helper/sysaudio-rec helper/sysaudio-rec.swift
//
// Output format is mono / 16000 Hz / 16-bit signed PCM WAV, which is exactly
// what transcribe.py + whisper.cpp already consume.

import Foundation
import AVFoundation
import ScreenCaptureKit

final class Recorder: NSObject, SCStreamOutput, SCStreamDelegate {
    private let outputURL: URL
    private var stream: SCStream?
    private var audioFile: AVAudioFile?
    private var converter: AVAudioConverter?
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16,
                                          sampleRate: 16000, channels: 1,
                                          interleaved: true)!
    // All file/converter access happens on this serial queue so the audio
    // callbacks and the stop() finalize never race.
    private let queue = DispatchQueue(label: "sysaudio-rec.audio")

    init(outputURL: URL) {
        self.outputURL = outputURL
    }

    func start() async throws {
        // Asking for shareable content is what triggers the one-time
        // Screen/System-Audio Recording permission prompt. If denied, this
        // throws and we report it.
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            throw NSError(domain: "sysaudio-rec", code: 1, userInfo: [
                NSLocalizedDescriptionKey:
                    "No display available to attach audio capture to."])
        }

        // Audio-only capture still needs a content filter with a display and a
        // (minimal) video config; we just ignore the video frames.
        let filter = SCContentFilter(display: display, excludingWindows: [])

        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1) // ~1 fps, cheap
        config.queueDepth = 6
        // Request mono 16 kHz; we still convert defensively in case the system
        // delivers a different format.
        config.sampleRate = 16000
        config.channelCount = 1

        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue)
        // Some macOS versions stall the stream if no screen output is attached,
        // so we attach one and discard the frames.
        try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
        try await stream.startCapture()
        self.stream = stream
        log("capturing system audio to \(outputURL.path)")
    }

    func stop() {
        let sema = DispatchSemaphore(value: 0)
        stream?.stopCapture { _ in sema.signal() }
        _ = sema.wait(timeout: .now() + 3)
        // Finalize on the audio queue so any in-flight write completes first.
        // Dropping the AVAudioFile writes the final WAV header.
        queue.sync {
            self.audioFile = nil
            self.converter = nil
        }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio, CMSampleBufferDataIsReady(sampleBuffer) else { return }
        guard let pcm = Recorder.pcmBuffer(from: sampleBuffer) else { return }
        write(pcm)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log("stream stopped with error: \(error.localizedDescription)")
    }

    private func write(_ input: AVAudioPCMBuffer) {
        do {
            if audioFile == nil {
                audioFile = try AVAudioFile(forWriting: outputURL,
                                            settings: outFormat.settings,
                                            commonFormat: .pcmFormatInt16,
                                            interleaved: true)
            }
            if converter == nil {
                converter = AVAudioConverter(from: input.format, to: outFormat)
            }
            guard let converter = converter, let file = audioFile else { return }

            let ratio = outFormat.sampleRate / input.format.sampleRate
            let cap = AVAudioFrameCount(Double(input.frameLength) * ratio + 1024)
            guard let out = AVAudioPCMBuffer(pcmFormat: outFormat,
                                             frameCapacity: cap) else { return }

            var err: NSError?
            var fed = false
            let status = converter.convert(to: out, error: &err) { _, inStatus in
                if fed { inStatus.pointee = .noDataNow; return nil }
                fed = true
                inStatus.pointee = .haveData
                return input
            }
            if status == .error {
                if let err = err { log("convert error: \(err.localizedDescription)") }
                return
            }
            if out.frameLength > 0 { try file.write(from: out) }
        } catch {
            log("write error: \(error.localizedDescription)")
        }
    }

    private static func pcmBuffer(from sampleBuffer: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard let fmtDesc = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmtDesc)
        else { return nil }
        guard let format = AVAudioFormat(streamDescription: asbd) else { return nil }
        let frames = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        guard frames > 0,
              let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames)
        else { return nil }
        pcm.frameLength = frames
        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer, at: 0, frameCount: Int32(frames),
            into: pcm.mutableAudioBufferList)
        return status == noErr ? pcm : nil
    }

    private func log(_ msg: String) {
        FileHandle.standardError.write(Data("sysaudio-rec: \(msg)\n".utf8))
    }
}

// ---- entry point ----

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write(Data("usage: sysaudio-rec <output.wav>\n".utf8))
    exit(2)
}

let recorder = Recorder(outputURL: URL(fileURLWithPath: args[1]))

// Clean stop on SIGINT/SIGTERM: finalize the WAV, then exit.
signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let sigint = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
let sigterm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
let onSignal: () -> Void = {
    recorder.stop()
    exit(0)
}
sigint.setEventHandler(handler: onSignal)
sigterm.setEventHandler(handler: onSignal)
sigint.resume()
sigterm.resume()

Task {
    do {
        try await recorder.start()
    } catch {
        FileHandle.standardError.write(
            Data("sysaudio-rec: failed to start: \(error.localizedDescription)\n".utf8))
        exit(1)
    }
}

dispatchMain()
